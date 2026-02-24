#!/usr/bin/env python3
"""
Unit tests for Marvin Cache Layer
Phase 1: Test cache_get, cache_set, TTL, invalidation
"""

import pytest
import time
import tempfile
import os
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from cache.cache import CacheLayer
from cache.key_generator import CacheKeyGenerator


class TestCacheLayer:
    """Test SQLite cache CRUD operations."""
    
    @pytest.fixture
    def cache(self):
        """Create temporary cache for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        cache = CacheLayer(db_path)
        yield cache
        cache.close()
        
        # Cleanup
        try:
            os.unlink(db_path)
        except:
            pass
    
    def test_cache_write_and_read(self, cache):
        """Test: write entry, read it back."""
        response = {"status": "ok", "version": "1.0"}
        
        # Write
        key = cache.put(
            intent="status_check",
            project="TestApp",
            response=response,
            tokens_saved=100,
        )
        
        assert key is not None
        
        # Read
        result = cache.get(intent="status_check", project="TestApp")
        assert result is not None
        assert result["value"] == response
        assert result["tokens_saved"] == 100
        assert result["hit_count"] == 1
    
    def test_cache_hit_increments_counter(self, cache):
        """Test: repeated reads increment hit_count."""
        response = {"data": "test"}
        
        cache.put("how_to", response, project="Dev")
        
        # First hit
        result1 = cache.get("how_to", project="Dev")
        assert result1["hit_count"] == 1
        
        # Second hit
        result2 = cache.get("how_to", project="Dev")
        assert result2["hit_count"] == 2
        
        # Stats updated
        stats = cache.get_stats()
        assert stats["hits"] == 2
    
    def test_cache_miss_tracked(self, cache):
        """Test: cache misses are tracked in stats."""
        cache.get("nonexistent", project="Nope")
        
        stats = cache.get_stats()
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 0.0
    
    def test_cache_expiration(self, cache):
        """Test: entries expire after TTL."""
        response = {"expired": True}
        
        # Write with very short TTL
        cache.put("status_check", response, project="Test")
        
        # Immediately readable
        result = cache.get("status_check", project="Test")
        assert result is not None
        
        # Wait past TTL (status_check TTL = 60s in default config)
        # For testing, we'll manually manipulate the database
        now = int(time.time())
        cursor = cache.conn.cursor()
        cursor.execute(
            "UPDATE cache_entries SET expires_at = ? WHERE intent = ?",
            (now - 1, "status_check")  # Expired 1 second ago
        )
        cache.conn.commit()
        
        # Now it should miss
        result = cache.get("status_check", project="Test")
        assert result is None
    
    def test_clear_expired(self, cache):
        """Test: clear_expired() removes expired entries."""
        response1 = {"id": 1}
        response2 = {"id": 2}
        
        cache.put("status_check", response1, project="Test1")
        cache.put("how_to", response2, project="Test2")
        
        # Expire first entry
        now = int(time.time())
        cursor = cache.conn.cursor()
        cursor.execute(
            "UPDATE cache_entries SET expires_at = ? WHERE intent = ?",
            (now - 1, "status_check")
        )
        cache.conn.commit()
        
        # Clear
        cleared = cache.clear_expired()
        assert cleared == 1
        
        # First gone, second still there
        assert cache.get("status_check", project="Test1") is None
        assert cache.get("how_to", project="Test2") is not None
    
    def test_clear_by_project(self, cache):
        """Test: clear_by_project() removes all entries for project."""
        cache.put("status_check", {"a": 1}, project="App1")
        cache.put("how_to", {"b": 2}, project="App1")
        cache.put("status_check", {"c": 3}, project="App2")
        
        # Clear App1
        cleared = cache.clear_by_project("App1")
        assert cleared == 2
        
        # App1 gone, App2 intact
        assert cache.get("status_check", project="App1") is None
        assert cache.get("how_to", project="App1") is None
        assert cache.get("status_check", project="App2") is not None
    
    def test_uncacheable_intents_skipped(self, cache):
        """Test: intents with TTL=None are not cached."""
        response = {"error": "debugging"}
        
        # debugging has TTL=None
        key = cache.put("debugging", response, project="Test")
        assert key is None  # Not cached
        
        # Reading returns None
        result = cache.get("debugging", project="Test")
        assert result is None
    
    def test_stats_accuracy(self, cache):
        """Test: stats accurately reflect cache operations."""
        cache.put("status_check", {"a": 1}, tokens_saved=100)
        cache.put("how_to", {"b": 2}, tokens_saved=200)
        
        cache.get("status_check")  # Hit
        cache.get("status_check")  # Hit
        cache.get("how_to")         # Hit
        cache.get("nonexistent")    # Miss
        
        stats = cache.get_stats()
        assert stats["writes"] == 2
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 75.0
        assert stats["tokens_saved"] == 300


class TestCacheKeyGenerator:
    """Test cache key generation and state detection."""
    
    @pytest.fixture
    def keygen(self):
        """Create key generator."""
        return CacheKeyGenerator()
    
    def test_deterministic_keys(self, keygen):
        """Test: same inputs → same key."""
        key1 = keygen.generate_cache_key("status_check", "App", "state123")
        key2 = keygen.generate_cache_key("status_check", "App", "state123")
        
        assert key1 == key2
    
    def test_different_state_different_key(self, keygen):
        """Test: different state → different key."""
        key1 = keygen.generate_cache_key("status_check", "App", "state123")
        key2 = keygen.generate_cache_key("status_check", "App", "state456")
        
        assert key1 != key2
    
    def test_different_intent_different_key(self, keygen):
        """Test: different intent → different key."""
        key1 = keygen.generate_cache_key("status_check", "App", "state123")
        key2 = keygen.generate_cache_key("how_to", "App", "state123")
        
        assert key1 != key2
    
    def test_state_signature_stability(self, keygen):
        """Test: state signature stable when project unchanged."""
        # Get current directory state (assuming we're in a git repo)
        sig1 = keygen.get_project_state_sig(".")
        time.sleep(0.1)
        sig2 = keygen.get_project_state_sig(".")
        
        # Should be same (unless we just committed)
        assert sig1 == sig2
    
    def test_state_cache_memory(self, keygen):
        """Test: state cache prevents repeated git calls."""
        keygen.get_project_state(".")
        
        # State should be in cache
        assert "." in keygen.state_cache
        
        # Clear it
        keygen.invalidate_project(".")
        assert "." not in keygen.state_cache


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])

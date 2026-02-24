#!/usr/bin/env python3
"""
Marvin Cache Layer
Phase 1: Exact Match Caching with SQLite + TTL Management

Implements:
- cache_get(key) → response | None
- cache_set(key, response, intent, project, ttl)
- cache_invalidate(project=None, intent=None)
- cache_clear_expired()
- cache_stats() → {hits, misses, entries, tokens_saved}
"""

import sqlite3
import json
import hashlib
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


class CacheLayer:
    """
    SQLite-backed cache with TTL, metrics, and invalidation.
    
    Design principles:
    - Fast queries: <5ms for cache_get
    - Metrics obsessed: every operation logged
    - Graceful degradation: cache miss = forward, not error
    - Project-aware: invalidate by git state
    """
    
    def __init__(self, db_path: str = None):
        """Initialize cache with SQLite backend."""
        if db_path is None:
            db_path = os.path.expanduser("~/.openclaw/workspace/cache/responses.db")
        
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Use check_same_thread=False for async operations
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        
        self._init_schema()
        self._init_ttl_map()
        
        self.stats = {
            "hits": 0,
            "misses": 0,
            "tokens_saved": 0,
            "writes": 0,
            "evictions": 0,
            "start_time": time.time(),
        }
        
        logger.info(f"CacheLayer initialized at {db_path}")
    
    def _init_schema(self):
        """Create tables if they don't exist."""
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            with open(schema_path) as f:
                self.conn.executescript(f.read())
            self.conn.commit()
            logger.debug("Schema initialized from schema.sql")
        else:
            logger.warning("schema.sql not found, using in-memory fallback")
            self._create_inline_schema()
    
    def _create_inline_schema(self):
        """Fallback: create schema inline if schema.sql not available."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                id INTEGER PRIMARY KEY,
                cache_key TEXT UNIQUE NOT NULL,
                intent TEXT NOT NULL,
                project TEXT,
                response TEXT NOT NULL,
                state_signature TEXT,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                hit_count INTEGER DEFAULT 0,
                tokens_saved INTEGER DEFAULT 0,
                tier TEXT DEFAULT 'exact_match',
                metadata TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_metrics (
                id INTEGER PRIMARY KEY,
                timestamp INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                intent TEXT,
                project TEXT,
                tier TEXT,
                tokens_saved INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_key ON cache_entries(cache_key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_entries(expires_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON cache_metrics(timestamp)")
        
        self.conn.commit()
        logger.debug("Inline schema created")
    
    def _init_ttl_map(self):
        """Initialize TTL map for different intent types."""
        self.ttl_map = {
            # Status checks: frequent changes, short TTL
            "status_check": 60,        # 1 minute
            "health_check": 60,
            "uptime": 60,
            
            # How-to / Reference: stable, longer TTL
            "how_to": 3600,            # 1 hour
            "reference": 3600,
            "command": 3600,
            
            # Trivial questions: generic, longer TTL
            "trivial": 86400,          # 24 hours
            "greeting": 86400,
            
            # Code/debugging: context-specific, no cache
            "code_review": None,
            "debugging": None,
            "error_fix": None,
            
            # Feature work: new, no cache
            "feature_work": None,
            "task": None,
            
            # Default
            "unknown": 3600,
        }
    
    def _make_cache_key(self, intent: str, project: str = None, state_sig: str = "") -> str:
        """Generate deterministic cache key from intent + project + state."""
        key_data = f"{intent}:{project or 'global'}:{state_sig}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:12]
    
    def get(self, intent: str, project: str = None, state_sig: str = "") -> Optional[Dict[str, Any]]:
        """
        Retrieve from cache if exists and not expired.
        
        Args:
            intent: Classification of the request
            project: Project context
            state_sig: State signature (e.g., last commit hash)
        
        Returns:
            {value, metadata, age_seconds, hit_count} or None
        """
        key = self._make_cache_key(intent, project, state_sig)
        now = int(time.time())
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, response, metadata, hit_count, tokens_saved, created_at
                FROM cache_entries 
                WHERE cache_key = ? AND expires_at > ?
                LIMIT 1
            """, (key, now))
            
            row = cursor.fetchone()
            
            if row:
                # Update hit count and last_hit_at
                entry_id = row["id"]
                cursor.execute("""
                    UPDATE cache_entries 
                    SET hit_count = hit_count + 1, last_hit_at = ?
                    WHERE id = ?
                """, (now, entry_id))
                self.conn.commit()
                
                # Update stats
                self.stats["hits"] += 1
                tokens = row["tokens_saved"] or 0
                self.stats["tokens_saved"] += tokens
                
                # Log metric
                self._log_metric("cache_hit", intent, project, "exact_match", tokens)
                
                return {
                    "value": json.loads(row["response"]),
                    "metadata": json.loads(row["metadata"] or "{}"),
                    "hit_count": row["hit_count"],
                    "age_seconds": now - row["created_at"],
                    "tokens_saved": tokens,
                }
            
            # Miss
            self.stats["misses"] += 1
            self._log_metric("cache_miss", intent, project, "exact_match", 0)
            return None
            
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def put(self, intent: str, response: Dict[str, Any], project: str = None, 
            state_sig: str = "", tokens_saved: int = 0, tier: str = "exact_match") -> Optional[str]:
        """
        Write response to cache with TTL.
        
        Args:
            intent: Classification of the request
            response: Response to cache (will be JSON serialized)
            project: Project context
            state_sig: State signature
            tokens_saved: Estimated tokens saved by caching this
            tier: Cache tier (exact_match, pattern_match, primer)
        
        Returns:
            cache_key on success, None on failure
        """
        key = self._make_cache_key(intent, project, state_sig)
        now = int(time.time())
        ttl = self.ttl_map.get(intent, 3600)  # Default 1 hour
        
        if ttl is None:
            # This intent shouldn't be cached
            logger.debug(f"Skipping cache write for {intent} (not cacheable)")
            return None
        
        expires_at = now + ttl
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO cache_entries 
                (cache_key, intent, project, response, state_signature, 
                 created_at, expires_at, tokens_saved, tier, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key,
                intent,
                project,
                json.dumps(response),
                state_sig,
                now,
                expires_at,
                tokens_saved,
                tier,
                json.dumps({"ttl": ttl, "tier": tier}),
            ))
            self.conn.commit()
            
            self.stats["writes"] += 1
            self.stats["tokens_saved"] += tokens_saved
            self._log_metric("cache_write", intent, project, tier, tokens_saved)
            
            logger.debug(f"Cached {intent} (key={key}, ttl={ttl}s, tokens_saved={tokens_saved})")
            return key
            
        except Exception as e:
            logger.error(f"Cache write error: {e}")
            return None
    
    def clear_expired(self) -> int:
        """Remove all expired entries. Should be called periodically."""
        now = int(time.time())
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM cache_entries WHERE expires_at < ?", (now,))
            cleared = cursor.rowcount
            self.conn.commit()
            
            if cleared > 0:
                self._log_invalidation("ttl_expiry", None, None, cleared)
                self.stats["evictions"] += cleared
                logger.info(f"Cleared {cleared} expired cache entries")
            
            return cleared
            
        except Exception as e:
            logger.error(f"Clear expired error: {e}")
            return 0
    
    def clear_by_project(self, project: str, reason: str = "project_change") -> int:
        """Clear all cache entries for a project (e.g., after git commit)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM cache_entries WHERE project = ?", (project,))
            cleared = cursor.rowcount
            self.conn.commit()
            
            if cleared > 0:
                self._log_invalidation(reason, None, project, cleared)
                self.stats["evictions"] += cleared
                logger.info(f"Cleared {cleared} cache entries for project {project} ({reason})")
            
            return cleared
            
        except Exception as e:
            logger.error(f"Clear by project error: {e}")
            return 0
    
    def clear_by_intent(self, intent: str, reason: str = "intent_clear") -> int:
        """Clear all entries for an intent type."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM cache_entries WHERE intent = ?", (intent,))
            cleared = cursor.rowcount
            self.conn.commit()
            
            if cleared > 0:
                self._log_invalidation(reason, intent, None, cleared)
                self.stats["evictions"] += cleared
                logger.info(f"Cleared {cleared} cache entries for intent {intent} ({reason})")
            
            return cleared
            
        except Exception as e:
            logger.error(f"Clear by intent error: {e}")
            return 0
    
    def _log_metric(self, event_type: str, intent: str = None, project: str = None, 
                    tier: str = None, tokens: int = 0):
        """Log cache metric."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO cache_metrics 
                (timestamp, event_type, intent, project, tier, tokens_saved)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (int(time.time()), event_type, intent, project, tier, tokens))
            self.conn.commit()
        except Exception as e:
            logger.warning(f"Metric log error: {e}")
    
    def _log_invalidation(self, reason: str, intent: str = None, project: str = None, count: int = 0):
        """Log invalidation event."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO invalidation_log 
                (timestamp, reason, target_type, target_value, keys_cleared)
                VALUES (?, ?, ?, ?, ?)
            """, (
                int(time.time()),
                reason,
                "intent" if intent else "project" if project else "all",
                intent or project or "all",
                count
            ))
            self.conn.commit()
        except Exception as e:
            logger.warning(f"Invalidation log error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM cache_entries")
            cache_entries = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM cache_entries WHERE expires_at < ?", (int(time.time()),))
            expired_entries = cursor.fetchone()["count"]
        except:
            cache_entries = expired_entries = 0
        
        uptime = time.time() - self.stats["start_time"]
        
        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_rate_percent": round(hit_rate, 1),
            "total_requests": total_requests,
            "tokens_saved": self.stats["tokens_saved"],
            "cache_entries": cache_entries,
            "expired_entries": expired_entries,
            "writes": self.stats["writes"],
            "evictions": self.stats["evictions"],
            "uptime_seconds": int(uptime),
        }
    
    def print_report(self):
        """Print cache statistics report."""
        stats = self.get_stats()
        
        print("\n" + "="*60)
        print("📊 MARVIN CACHE LAYER REPORT")
        print("="*60)
        print(f"Hit Rate: {stats['hit_rate_percent']}% ({stats['hits']}/{stats['total_requests']})")
        print(f"Tokens Saved: {stats['tokens_saved']:,}")
        print(f"Cache Size: {stats['cache_entries']} entries ({stats['expired_entries']} expired)")
        print(f"Writes: {stats['writes']} | Evictions: {stats['evictions']}")
        print(f"Uptime: {stats['uptime_seconds']}s")
        print("="*60 + "\n")
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("CacheLayer closed")


if __name__ == "__main__":
    # Test
    cache = CacheLayer("/tmp/marvin_test.db")
    
    # Write
    cache.put(
        intent="status_check",
        project="BetApp",
        response={"status": "running", "health": "ok"},
        tokens_saved=250,
    )
    
    # Read
    result = cache.get(intent="status_check", project="BetApp")
    if result:
        print(f"✅ Cache hit: {result['value']}")
    else:
        print("❌ Cache miss")
    
    # Stats
    cache.print_report()
    cache.close()

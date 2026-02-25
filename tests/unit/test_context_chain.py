#!/usr/bin/env python3
"""
Unit tests for Constitutional Recovery Chain
"""

import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vps.context_chain import ContextChain, ChainLink, CHAIN


# ── Chain Structure Tests ────────────────────────────────────────

class TestChainStructure:

    def test_chain_has_documents(self):
        assert len(CHAIN) > 0

    def test_chain_is_ordered(self):
        for i, link in enumerate(CHAIN):
            assert link.order == i

    def test_chain_links_connected(self):
        """Every doc except first has prev, every doc except last has next."""
        for i, link in enumerate(CHAIN):
            if i > 0:
                assert link.prev_doc == CHAIN[i - 1].doc_id
            else:
                assert link.prev_doc is None

            if i < len(CHAIN) - 1:
                assert link.next_doc == CHAIN[i + 1].doc_id
            else:
                assert link.next_doc is None

    def test_chain_starts_with_constitution(self):
        assert CHAIN[0].doc_id == "constitution"
        assert CHAIN[0].category == "constitution"

    def test_chain_ends_with_build_plan(self):
        assert CHAIN[-1].doc_id == "build_plan"

    def test_all_doc_ids_unique(self):
        ids = [link.doc_id for link in CHAIN]
        assert len(ids) == len(set(ids))

    def test_chain_link_to_dict(self):
        link = CHAIN[0]
        d = link.to_dict()
        assert d["doc_id"] == "constitution"
        assert d["order"] == 0
        assert "summary" in d


# ── ContextChain Class Tests ────────────────────────────────────

class TestContextChain:

    @pytest.fixture
    def chain(self):
        # Point to the actual project root
        root = str(Path(__file__).parent.parent.parent)
        return ContextChain(project_root=root)

    def test_init(self, chain):
        assert len(chain) > 0

    def test_repr(self, chain):
        r = repr(chain)
        assert "ContextChain" in r
        assert "docs=" in r

    def test_get_full_chain(self, chain):
        full = chain.get_full_chain()
        assert len(full) == len(CHAIN)
        assert full[0]["doc_id"] == "constitution"

    def test_get_link(self, chain):
        link = chain.get_link("departments")
        assert link is not None
        assert link["title"] == "Department Heads (Ralph, Ira, Tess)"

    def test_get_link_not_found(self, chain):
        assert chain.get_link("nonexistent") is None


# ── Agent-Specific Recovery Tests ────────────────────────────────

class TestRecoverySequence:

    @pytest.fixture
    def chain(self):
        root = str(Path(__file__).parent.parent.parent)
        return ContextChain(project_root=root)

    def test_ira_recovery(self, chain):
        seq = chain.get_recovery_sequence("ira")

        # Constitution first
        assert seq[0]["category"] == "constitution"

        # Should include cache_layer and rate_limiter (tagged for ira)
        doc_ids = [l["doc_id"] for l in seq]
        assert "cache_layer" in doc_ids
        assert "rate_limiter" in doc_ids

    def test_ralph_recovery(self, chain):
        seq = chain.get_recovery_sequence("ralph")
        doc_ids = [l["doc_id"] for l in seq]

        # Ralph needs lobby and receptionist
        assert "lobby" in doc_ids
        assert "receptionist" in doc_ids

    def test_tess_recovery(self, chain):
        seq = chain.get_recovery_sequence("tess")
        doc_ids = [l["doc_id"] for l in seq]

        # Tess needs cache_layer
        assert "cache_layer" in doc_ids

    def test_all_agents_get_constitution(self, chain):
        for agent in ["ira", "ralph", "tess"]:
            seq = chain.get_recovery_sequence(agent)
            # First docs should be constitution category
            constitution_docs = [l for l in seq if l["category"] == "constitution"]
            assert len(constitution_docs) >= 2

    def test_recovery_covers_all_docs(self, chain):
        """Every doc in the chain appears in every agent's recovery."""
        for agent in ["ira", "ralph", "tess"]:
            seq = chain.get_recovery_sequence(agent)
            seq_ids = {l["doc_id"] for l in seq}
            chain_ids = {l.doc_id for l in CHAIN}
            assert seq_ids == chain_ids


# ── Bootstrap Tests ──────────────────────────────────────────────

class TestBootstrap:

    @pytest.fixture
    def chain(self):
        root = str(Path(__file__).parent.parent.parent)
        return ContextChain(project_root=root)

    def test_bootstrap_all(self, chain):
        boot = chain.get_bootstrap()
        assert boot["agent"] == "all"
        assert boot["doc_count"] == len(CHAIN)
        assert boot["estimated_tokens"] > 0
        assert len(boot["primer"]) > 0
        assert len(boot["reading_order"]) == len(CHAIN)
        assert boot["first_doc"] is not None

    def test_bootstrap_agent(self, chain):
        boot = chain.get_bootstrap("ira")
        assert boot["agent"] == "ira"
        assert boot["doc_count"] == len(CHAIN)  # All docs, just reordered
        assert "primer" in boot

    def test_primer_contains_summaries(self, chain):
        boot = chain.get_bootstrap()
        # Should contain key phrases from summaries
        assert "Cache First" in boot["primer"]
        assert "envelope" in boot["primer"].lower()


# ── Document Reading Tests ───────────────────────────────────────

class TestDocReading:

    @pytest.fixture
    def chain(self):
        root = str(Path(__file__).parent.parent.parent)
        return ContextChain(project_root=root)

    def test_read_existing_doc(self, chain):
        content = chain.read_doc("constitution")
        assert content is not None
        assert "Constitutional Principles" in content

    def test_read_nonexistent_doc_id(self, chain):
        assert chain.read_doc("nonexistent") is None

    def test_read_next(self, chain):
        next_doc = chain.read_next("constitution")
        assert next_doc is not None
        assert next_doc["doc_id"] == "cost_vs_performance"
        assert len(next_doc["content"]) > 0

    def test_read_next_last_doc(self, chain):
        """Last doc in chain has no next."""
        assert chain.read_next("build_plan") is None


# ── Chain Health Tests ───────────────────────────────────────────

class TestChainHealth:

    @pytest.fixture
    def chain(self):
        root = str(Path(__file__).parent.parent.parent)
        return ContextChain(project_root=root)

    def test_verify_chain(self, chain):
        health = chain.verify_chain()
        assert health["total"] == len(CHAIN)
        assert health["found"] > 0
        assert isinstance(health["docs"], list)

    def test_verify_reports_missing(self):
        """Chain pointed at empty dir should report missing docs."""
        chain = ContextChain(project_root="/tmp")
        health = chain.verify_chain()
        assert health["missing"] == len(CHAIN)
        assert health["healthy"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

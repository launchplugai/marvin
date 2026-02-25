#!/usr/bin/env python3
"""
Constitutional Recovery Chain — Marvin's Long-Term Scaffolding

If an agent loses context — new session, crash, model swap — this module
rebuilds it from first principles. Every document in the chain points to
the next. You start at link 0, read through, and by the end you have
full situational awareness.

The chain is NOT the documents themselves. It's a manifest that:
1. Orders them (read THIS first, THEN this, THEN this)
2. Summarizes each (so you can skip if you remember)
3. Tags relevance per agent (Ralph doesn't need infra docs first)
4. Provides a bootstrap sequence (minimal context in fewest tokens)

Usage:
    chain = ContextChain()
    chain.get_bootstrap(agent="ira")       # Ira's minimal context
    chain.get_full_chain()                  # All docs in order
    chain.get_recovery_sequence(agent="tess")  # Tess's reading list
"""

import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


@dataclass
class ChainLink:
    """A single document in the recovery chain."""
    order: int
    doc_id: str
    title: str
    path: str
    summary: str
    agents: List[str]          # Which agents need this (empty = all)
    category: str              # constitution, architecture, operations
    tokens_estimate: int       # Rough token count for budgeting
    next_doc: Optional[str] = None
    prev_doc: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── The Chain ────────────────────────────────────────────────────
# Order matters. Each doc builds on the previous.
# An agent reading these in order goes from zero to full context.

CHAIN: List[ChainLink] = [
    ChainLink(
        order=0,
        doc_id="constitution",
        title="Constitutional Principles",
        path="docs/ADRs/001-constitutional-principles.md",
        summary=(
            "8 inviolable rules: Cache First, Free Tier Primary, "
            "Transparent Fallback, Graceful Degradation, Metrics Obsessed, "
            "Production Ready, Autonomous Specialization, Semantic Versioning of Prompts. "
            "All decisions trace back to these."
        ),
        agents=[],  # Everyone
        category="constitution",
        tokens_estimate=600,
    ),
    ChainLink(
        order=1,
        doc_id="cost_vs_performance",
        title="Cost vs Performance Trade-offs",
        path="docs/ADRs/002-cost-vs-performance.md",
        summary=(
            "When speed and cost conflict, cost wins unless it's an emergency. "
            "Free tier first, paid models only when justified. "
            "Every paid API call logged with cost."
        ),
        agents=[],
        category="constitution",
        tokens_estimate=400,
    ),
    ChainLink(
        order=2,
        doc_id="fallback_hierarchy",
        title="Rate Limit Fallback Hierarchy",
        path="docs/ADRs/003-rate-limit-fallback-hierarchy.md",
        summary=(
            "Execution waterfall: Cache → Claude CLI → Groq pool (7 models) → "
            "Kimi 2.5 → Opus API (emergency). Each level has specific triggers "
            "and fallback conditions."
        ),
        agents=[],
        category="constitution",
        tokens_estimate=500,
    ),
    ChainLink(
        order=3,
        doc_id="transmission",
        title="The Transmission (Request Envelope)",
        path="docs/designs/01-transmission.md",
        summary=(
            "Every request travels in a JSON envelope. Each layer stamps it "
            "but never removes previous stamps. Contains: original message, "
            "classification, cache result, routing, context primer, execution chain, "
            "rate limit state. This IS the handoff format."
        ),
        agents=[],
        category="architecture",
        tokens_estimate=800,
    ),
    ChainLink(
        order=4,
        doc_id="cache_layer",
        title="Cache Layer (Filing Cabinet)",
        path="docs/designs/02-cache-layer.md",
        summary=(
            "3-tier cache: Tier 1 exact match (<5ms), Tier 2 embedding similarity, "
            "Tier 3 context primers. SQLite-backed. TTLs per intent type. "
            "Auto-invalidation on git commits. Target: >20% hit rate."
        ),
        agents=["ira", "tess"],
        category="architecture",
        tokens_estimate=700,
    ),
    ChainLink(
        order=5,
        doc_id="lobby",
        title="Lobby Router (Intent Classifier)",
        path="docs/designs/03-lobby.md",
        summary=(
            "First stop for every message. Groq Llama 8B classifies intent "
            "(status, how_to, debugging, feature_work, trivial). "
            "3-phase: keyword match → LLM → fallback. Output starts the envelope."
        ),
        agents=["ralph"],
        category="architecture",
        tokens_estimate=600,
    ),
    ChainLink(
        order=6,
        doc_id="receptionist",
        title="Receptionist (Haiku Dispatcher)",
        path="docs/designs/04-receptionist.md",
        summary=(
            "After lobby classifies, Haiku routes to the right department. "
            "Self-handles trivials (zero downstream cost). Routes based on "
            "intent x complexity → department. Manages buffer activation."
        ),
        agents=["ralph"],
        category="architecture",
        tokens_estimate=600,
    ),
    ChainLink(
        order=7,
        doc_id="departments",
        title="Department Heads (Ralph, Ira, Tess)",
        path="docs/designs/05-departments.md",
        summary=(
            "Three specialized agents. Ralph: Scrum Master (planning, sprints). "
            "Ira: Infrastructure Guardian (VPS, deploy, monitoring). "
            "Tess: Test Engineer (tests, coverage, quality gates). "
            "Each has primary model (Kimi 2.5) + buffer (Groq). "
            "90%+ autonomous within domain."
        ),
        agents=[],
        category="operations",
        tokens_estimate=1200,
    ),
    ChainLink(
        order=8,
        doc_id="rate_limiter",
        title="Rate Limit Tracker",
        path="docs/designs/06-rate-limiter.md",
        summary=(
            "Reads rate limit headers from every API response. Zero extra cost. "
            "Green/yellow/red health per provider. Yellow = divert low-priority "
            "to buffer. Red = switch to fallback. Triggers cascade automatically."
        ),
        agents=["ira"],
        category="architecture",
        tokens_estimate=600,
    ),
    ChainLink(
        order=9,
        doc_id="boss_emergency",
        title="Boss + Emergency Escalation",
        path="docs/designs/07-boss-emergency.md",
        summary=(
            "Boss handles cross-domain conflicts (Ralph vs Tess, budget decisions). "
            "Max 10% daily Kimi tokens. Emergency tier: Claude Opus as absolute "
            "last resort. Emergency responses always cached. >5 boss calls/day = "
            "architecture smell."
        ),
        agents=["ralph"],
        category="operations",
        tokens_estimate=700,
    ),
    ChainLink(
        order=10,
        doc_id="build_plan",
        title="Build Plan (4-Phase Timeline)",
        path="docs/designs/08-build-plan.md",
        summary=(
            "Phase 1: Cache + Lobby + Rate Tracker (done). "
            "Phase 2: Receptionist + Dispatch (routing). "
            "Phase 3: Department Heads operational. "
            "Phase 4: Boss + Emergency + Hardening. "
            "Each phase stands alone. File map included."
        ),
        agents=[],
        category="operations",
        tokens_estimate=1000,
    ),
]

# Wire up next/prev pointers
for i, link in enumerate(CHAIN):
    if i > 0:
        link.prev_doc = CHAIN[i - 1].doc_id
    if i < len(CHAIN) - 1:
        link.next_doc = CHAIN[i + 1].doc_id


class ContextChain:
    """
    Constitutional recovery chain for Marvin agents.

    Provides ordered reading lists, agent-specific context primers,
    and bootstrap sequences for rebuilding awareness from scratch.
    """

    def __init__(self, project_root: str = None):
        self.project_root = project_root or self._find_project_root()
        self.chain = CHAIN
        logger.info(f"ContextChain initialized ({len(self.chain)} docs, root={self.project_root})")

    @staticmethod
    def _find_project_root() -> str:
        """Find the project root by looking for docs/ directory."""
        candidates = [
            os.environ.get("MARVIN_ROOT", ""),
            os.getcwd(),
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ]
        for c in candidates:
            if c and os.path.isdir(os.path.join(c, "docs")):
                return c
        return os.getcwd()

    # ── Full Chain ───────────────────────────────────────────────

    def get_full_chain(self) -> List[Dict[str, Any]]:
        """Get the complete chain in reading order."""
        return [link.to_dict() for link in self.chain]

    def get_link(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific link by doc_id."""
        for link in self.chain:
            if link.doc_id == doc_id:
                return link.to_dict()
        return None

    # ── Agent-Specific Recovery ──────────────────────────────────

    def get_recovery_sequence(self, agent: str) -> List[Dict[str, Any]]:
        """
        Get the reading order for a specific agent recovering context.

        Constitutional docs come first (everyone needs them),
        then agent-relevant docs, then general docs.
        """
        # Phase 1: Constitution (everyone reads these)
        constitution = [l for l in self.chain if l.category == "constitution"]

        # Phase 2: Agent-relevant docs
        relevant = [
            l for l in self.chain
            if l.category != "constitution" and (not l.agents or agent in l.agents)
        ]

        # Phase 3: Remaining docs (lower priority)
        remaining = [
            l for l in self.chain
            if l.category != "constitution" and l.agents and agent not in l.agents
        ]

        sequence = constitution + relevant + remaining
        return [l.to_dict() for l in sequence]

    def get_bootstrap(self, agent: str = None) -> Dict[str, Any]:
        """
        Minimal context primer — the absolute minimum to start working.

        Returns summaries only (no full docs), ordered by priority.
        Designed to fit in ~2000 tokens.
        """
        if agent:
            sequence = self.get_recovery_sequence(agent)
        else:
            sequence = self.get_full_chain()

        # Build compact primer
        primer_lines = []
        total_tokens = 0
        for link in sequence:
            primer_lines.append(f"[{link['doc_id']}] {link['title']}: {link['summary']}")
            total_tokens += link.get("tokens_estimate", 100)

        return {
            "agent": agent or "all",
            "doc_count": len(sequence),
            "estimated_tokens": total_tokens,
            "primer": "\n\n".join(primer_lines),
            "reading_order": [l["doc_id"] for l in sequence],
            "first_doc": sequence[0]["path"] if sequence else None,
        }

    # ── Document Reading ─────────────────────────────────────────

    def read_doc(self, doc_id: str) -> Optional[str]:
        """
        Read the full content of a document in the chain.
        Returns None if the file doesn't exist.
        """
        link = self.get_link(doc_id)
        if not link:
            return None

        full_path = os.path.join(self.project_root, link["path"])
        try:
            with open(full_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"Document not found: {full_path}")
            return None
        except Exception as e:
            logger.error(f"Error reading {full_path}: {e}")
            return None

    def read_next(self, current_doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Read the next document in the chain after the given one.
        Returns {"doc_id": ..., "title": ..., "content": ...} or None.
        """
        link = self.get_link(current_doc_id)
        if not link or not link.get("next_doc"):
            return None

        next_id = link["next_doc"]
        content = self.read_doc(next_id)
        next_link = self.get_link(next_id)

        if content and next_link:
            return {
                "doc_id": next_id,
                "title": next_link["title"],
                "content": content,
                "next_doc": next_link.get("next_doc"),
            }
        return None

    # ── Chain Health ─────────────────────────────────────────────

    def verify_chain(self) -> Dict[str, Any]:
        """
        Verify all documents in the chain exist and are readable.
        Returns health report.
        """
        results = []
        missing = 0

        for link in self.chain:
            full_path = os.path.join(self.project_root, link.path)
            exists = os.path.isfile(full_path)
            if not exists:
                missing += 1
            results.append({
                "doc_id": link.doc_id,
                "title": link.title,
                "path": link.path,
                "exists": exists,
            })

        return {
            "total": len(self.chain),
            "found": len(self.chain) - missing,
            "missing": missing,
            "healthy": missing == 0,
            "docs": results,
        }

    # ── Convenience ──────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.chain)

    def __repr__(self) -> str:
        return f"ContextChain(docs={len(self.chain)}, root={self.project_root})"

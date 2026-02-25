#!/usr/bin/env python3
"""
Unit tests for Mission Control State Engine
"""

import os
import sys
import time
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vps.state import StateEngine, Event, AgentSnapshot


@pytest.fixture
def engine():
    """Create a StateEngine with a temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    eng = StateEngine(db_path=db_path)
    yield eng
    eng.close()
    os.unlink(db_path)


# ── Event Log Tests ──────────────────────────────────────────────

class TestEventLog:

    def test_log_event_returns_id(self, engine):
        eid = engine.log("ira", "action", "deploy", target="redis")
        assert eid >= 1

    def test_log_and_retrieve(self, engine):
        engine.log("ira", "action", "deploy", target="redis", detail="v7")
        engine.log("tess", "action", "test_run", target="unit_tests", success=False)

        events = engine.get_events()
        assert len(events) == 2
        # Most recent first
        assert events[0]["agent"] == "tess"
        assert events[0]["success"] == 0
        assert events[1]["agent"] == "ira"

    def test_filter_by_agent(self, engine):
        engine.log("ira", "action", "deploy")
        engine.log("tess", "action", "test_run")
        engine.log("ira", "action", "reboot")

        events = engine.get_events(agent="ira")
        assert len(events) == 2
        assert all(e["agent"] == "ira" for e in events)

    def test_filter_by_category(self, engine):
        engine.log("ira", "action", "deploy")
        engine.log("ira", "error", "timeout")
        engine.log("ira", "action", "restart")

        events = engine.get_events(category="error")
        assert len(events) == 1
        assert events[0]["action"] == "timeout"

    def test_filter_by_time(self, engine):
        engine.log("ira", "action", "old_event")
        cutoff = time.time()
        time.sleep(0.01)
        engine.log("ira", "action", "new_event")

        events = engine.get_events(since=cutoff)
        assert len(events) == 1
        assert events[0]["action"] == "new_event"

    def test_limit(self, engine):
        for i in range(10):
            engine.log("ira", "action", f"event_{i}")

        events = engine.get_events(limit=3)
        assert len(events) == 3

    def test_get_recent(self, engine):
        for i in range(5):
            engine.log("ira", "action", f"event_{i}")

        recent = engine.get_recent(limit=3)
        assert len(recent) == 3

    def test_context_json_stored(self, engine):
        engine.log("ira", "action", "deploy", context={"version": "2.1", "port": 8080})

        events = engine.get_events()
        assert events[0]["context"]["version"] == "2.1"
        assert events[0]["context"]["port"] == 8080

    def test_session_id_filter(self, engine):
        engine.log("ira", "action", "a", session_id="sess-1")
        engine.log("ira", "action", "b", session_id="sess-2")
        engine.log("ira", "action", "c", session_id="sess-1")

        events = engine.get_events()
        sess1 = [e for e in events if e["session_id"] == "sess-1"]
        assert len(sess1) == 2


# ── Agent State Tests ────────────────────────────────────────────

class TestAgentState:

    def test_auto_created_on_log(self, engine):
        engine.log("ralph", "action", "plan_sprint")

        state = engine.get_agent_state("ralph")
        assert state is not None
        assert state["agent"] == "ralph"
        assert state["last_action"] == "plan_sprint"
        assert state["total_actions"] == 1

    def test_action_count_increments(self, engine):
        engine.log("ira", "action", "deploy")
        engine.log("ira", "action", "restart")
        engine.log("ira", "action", "snapshot")

        state = engine.get_agent_state("ira")
        assert state["total_actions"] == 3

    def test_error_count_increments(self, engine):
        engine.log("ira", "action", "deploy", success=True)
        engine.log("ira", "error", "timeout", success=False)
        engine.log("ira", "error", "crash", success=False)

        state = engine.get_agent_state("ira")
        assert state["total_actions"] == 3
        assert state["total_errors"] == 2

    def test_set_agent_status(self, engine):
        engine.log("tess", "action", "init")
        engine.set_agent_status("tess", "working", current_task="running tests",
                                 notes="coverage check", energy=85)

        state = engine.get_agent_state("tess")
        assert state["status"] == "working"
        assert state["current_task"] == "running tests"
        assert state["notes"] == "coverage check"
        assert state["energy"] == 85

    def test_get_all_agents(self, engine):
        engine.log("ira", "action", "deploy")
        engine.log("ralph", "action", "plan")
        engine.log("tess", "action", "test")

        agents = engine.get_all_agents()
        assert len(agents) == 3
        names = {a["agent"] for a in agents}
        assert names == {"ira", "ralph", "tess"}

    def test_unknown_agent_returns_none(self, engine):
        assert engine.get_agent_state("nonexistent") is None


# ── Progress Tracking Tests ──────────────────────────────────────

class TestProgress:

    def test_add_task(self, engine):
        tid = engine.add_task("phase_1", "Implement cache layer", owner="ira")
        assert tid >= 1

    def test_get_progress(self, engine):
        engine.add_task("phase_1", "Cache layer", owner="ira")
        engine.add_task("phase_1", "Lobby router", owner="ralph")
        engine.add_task("phase_2", "Receptionist", owner="ralph")

        tasks = engine.get_progress("phase_1")
        assert len(tasks) == 2

        all_tasks = engine.get_progress()
        assert len(all_tasks) == 3

    def test_update_task(self, engine):
        tid = engine.add_task("phase_1", "Cache layer")
        engine.update_task(tid, "in_progress", "Working on SQLite schema")

        tasks = engine.get_progress("phase_1")
        assert tasks[0]["status"] == "in_progress"
        assert tasks[0]["detail"] == "Working on SQLite schema"

    def test_complete_task(self, engine):
        tid = engine.add_task("phase_1", "Cache layer")
        engine.update_task(tid, "done")

        tasks = engine.get_progress("phase_1")
        assert tasks[0]["status"] == "done"
        assert tasks[0]["completed_at"] is not None

    def test_progress_summary(self, engine):
        t1 = engine.add_task("phase_1", "Task A")
        t2 = engine.add_task("phase_1", "Task B")
        t3 = engine.add_task("phase_2", "Task C")
        engine.update_task(t1, "done")
        engine.update_task(t2, "in_progress")

        summary = engine.get_progress_summary()
        assert summary["total_tasks"] == 3
        assert summary["completed"] == 1
        assert len(summary["phases"]) == 2


# ── Decision Records Tests ───────────────────────────────────────

class TestDecisions:

    def test_record_decision(self, engine):
        did = engine.record_decision(
            agent="ira",
            title="Use SQLite for state",
            context="Need persistent storage with zero infrastructure",
            choice="SQLite with WAL mode",
            alternatives="PostgreSQL, Redis",
            rationale="Zero setup, portable, backup-friendly",
        )
        assert did >= 1

    def test_get_decisions(self, engine):
        engine.record_decision("ira", "Decision A", "ctx", "choice A")
        engine.record_decision("ralph", "Decision B", "ctx", "choice B")

        decisions = engine.get_decisions()
        assert len(decisions) == 2
        assert decisions[0]["agent"] == "ralph"  # Most recent first


# ── Diagnostics Tests ────────────────────────────────────────────

class TestDiagnostics:

    def test_log_model_usage(self, engine):
        engine.log_model_usage(
            model="llama-8b", provider="groq", action="classify",
            tokens_in=100, tokens_out=50, latency_ms=120,
        )
        engine.log_model_usage(
            model="kimi-2.5", provider="moonshot", action="generate",
            tokens_in=500, tokens_out=200, latency_ms=1500,
            cost_usd=0.003,
        )

        diag = engine.get_diagnostics(hours=1)
        assert len(diag["models"]) == 2
        assert diag["totals"]["total_calls"] == 2

    def test_diagnostics_error_tracking(self, engine):
        engine.log_model_usage("llama-8b", "groq", success=True)
        engine.log_model_usage("llama-8b", "groq", success=False, error="timeout")

        diag = engine.get_diagnostics(hours=1)
        model = diag["models"][0]
        assert model["errors"] == 1
        assert model["calls"] == 2

    def test_diagnostics_cost_tracking(self, engine):
        engine.log_model_usage("opus", "anthropic", cost_usd=0.05)
        engine.log_model_usage("opus", "anthropic", cost_usd=0.03)

        diag = engine.get_diagnostics(hours=1)
        assert abs(diag["totals"]["total_cost"] - 0.08) < 0.001


# ── Context Primer Tests ─────────────────────────────────────────

class TestContextPrimer:

    def test_context_for_agent(self, engine):
        engine.log("ira", "action", "deploy", target="redis")
        engine.log("ira", "action", "snapshot")
        engine.log("ralph", "action", "plan_sprint")
        engine.add_task("phase_1", "Deploy cache", owner="ira")

        ctx = engine.get_context_for_agent("ira")

        assert ctx["agent"] == "ira"
        assert ctx["state"] is not None
        assert len(ctx["own_recent_events"]) == 2
        assert len(ctx["system_recent_events"]) >= 2
        assert len(ctx["active_tasks"]) >= 1

    def test_context_includes_decisions(self, engine):
        engine.record_decision("ira", "Use Redis", "caching", "Redis")

        ctx = engine.get_context_for_agent("ira")
        assert len(ctx["recent_decisions"]) >= 1


# ── Stats & Dataclass Tests ──────────────────────────────────────

class TestStats:

    def test_get_stats(self, engine):
        engine.log("ira", "action", "deploy")
        engine.add_task("phase_1", "task")
        engine.record_decision("ira", "d", "c", "ch")

        stats = engine.get_stats()
        assert stats["events"] == 1
        assert stats["tasks"] == 1
        assert stats["decisions"] == 1
        assert stats["agents"] == 1

    def test_event_dataclass(self):
        e = Event(agent="ira", category="action", action="deploy")
        d = e.to_dict()
        assert d["agent"] == "ira"
        assert "id" not in d

    def test_agent_snapshot_dataclass(self):
        a = AgentSnapshot(agent="tess", status="working", energy=80)
        d = a.to_dict()
        assert d["agent"] == "tess"
        assert d["energy"] == 80


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

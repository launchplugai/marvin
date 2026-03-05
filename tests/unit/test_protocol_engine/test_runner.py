"""Tests for ProtocolRunner."""

import json
import tempfile
from pathlib import Path

import pytest
from protocol_engine.models import (
    Impact,
    ImpactType,
    ProtocolSignal,
    Tier,
)
from protocol_engine.runner import ProtocolRunner


def _make_pdc_dir(pdc_data):
    """Create a temp dir with a pdc.json and return the path."""
    tmpdir = tempfile.mkdtemp()
    pdc_file = Path(tmpdir) / "pdc.json"
    pdc_file.write_text(json.dumps(pdc_data))
    return Path(tmpdir)


def _mock_evaluator(protocol_id, triggered=True, impact_value=-0.05):
    """Return a mock evaluator function."""
    def evaluate(context, thresholds):
        return ProtocolSignal(
            protocol_id=protocol_id,
            triggered=triggered,
            confidence=0.85,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=impact_value),
            evidence_data={"mock": True},
        )
    return evaluate


@pytest.fixture
def pdc_data():
    return {
        "catalogVersion": "1.0.0",
        "dnaContractVersion": "dna_contract_v1",
        "generatedAt": "2026-03-05T00:00:00Z",
        "defaults": {
            "enabled": True,
            "tier": "PRO",
            "confidence": {"minTriggerConfidence": 0.60, "minEmitConfidence": 0.50},
        },
        "protocols": [
            {
                "protocolId": "proto_a_v1",
                "name": "Proto A",
                "sport": ["NBA"],
                "category": "physical_state",
                "enabled": True,
                "tier": "PRO",
                "inputs": {"required": ["schedule"], "optional": []},
                "evaluator": {"type": "python", "module": "mock_mod", "entrypoint": "evaluate"},
                "thresholds": {"x": 1},
                "weights": {"riskWeight": 0.10},
                "impactModel": {"type": "stability_modifier", "mode": "additive", "clamp": {"min": -0.12, "max": 0.0}},
                "artifactMapping": {
                    "evidence": {"summaryTemplate": "A triggered.", "fields": ["mock"]},
                    "weight": {"target": "stabilityModifier", "deltaPath": "impact.value"},
                    "auditNote": {"noteTemplate": "Applied A."},
                },
                "explainTemplates": {"title": "Proto A"},
            },
            {
                "protocolId": "proto_b_v1",
                "name": "Proto B",
                "sport": ["NBA"],
                "category": "volatility",
                "enabled": True,
                "tier": "FREE",
                "inputs": {"required": ["team_metrics"], "optional": []},
                "evaluator": {"type": "python", "module": "mock_mod", "entrypoint": "evaluate"},
                "thresholds": {},
                "weights": {"riskWeight": 0.08},
                "impactModel": {"type": "fragility_delta", "mode": "additive", "clamp": {"min": 0.0, "max": 0.12}},
                "artifactMapping": {
                    "evidence": {"summaryTemplate": "B triggered.", "fields": ["mock"]},
                    "weight": {"target": "fragilityDelta", "deltaPath": "impact.value"},
                    "auditNote": {"noteTemplate": "Applied B."},
                },
                "explainTemplates": {"title": "Proto B"},
            },
        ],
    }


class TestProtocolRunner:
    def test_run_with_overrides(self, pdc_data):
        pdc_dir = _make_pdc_dir(pdc_data)
        runner = ProtocolRunner(
            pdc_path=pdc_dir,
            evaluator_overrides={
                "proto_a_v1": _mock_evaluator("proto_a_v1", triggered=True, impact_value=-0.06),
                "proto_b_v1": _mock_evaluator("proto_b_v1", triggered=False, impact_value=0.0),
            },
        )
        context = {"schedule": {}, "team_metrics": {}}
        output = runner.run(context, sport="NBA", user_tier=Tier.PRO)

        assert len(output.results) == 2
        assert "proto_a_v1" in output.triggered_protocol_ids
        assert "proto_b_v1" not in output.triggered_protocol_ids
        assert output.aggregate_stability_modifier == pytest.approx(-0.06)

    def test_tier_gating(self, pdc_data):
        pdc_dir = _make_pdc_dir(pdc_data)
        runner = ProtocolRunner(
            pdc_path=pdc_dir,
            evaluator_overrides={
                "proto_b_v1": _mock_evaluator("proto_b_v1", triggered=True, impact_value=0.05),
            },
        )
        context = {"team_metrics": {}}
        output = runner.run(context, sport="NBA", user_tier=Tier.FREE)

        # Only proto_b (FREE tier) should run
        assert len(output.results) == 1
        assert output.results[0].protocol_id == "proto_b_v1"

    def test_missing_inputs_skipped(self, pdc_data):
        pdc_dir = _make_pdc_dir(pdc_data)
        runner = ProtocolRunner(
            pdc_path=pdc_dir,
            evaluator_overrides={
                "proto_a_v1": _mock_evaluator("proto_a_v1"),
                "proto_b_v1": _mock_evaluator("proto_b_v1"),
            },
        )
        # Missing "schedule" required by proto_a
        context = {"team_metrics": {}}
        output = runner.run(context, sport="NBA", user_tier=Tier.PRO)

        run_ids = {r.protocol_id for r in output.results}
        assert "proto_a_v1" not in run_ids
        assert "proto_b_v1" in run_ids
        assert any("missing inputs" in e for e in output.errors)

    def test_shadow_mode_no_aggregation(self, pdc_data):
        pdc_dir = _make_pdc_dir(pdc_data)
        runner = ProtocolRunner(
            pdc_path=pdc_dir,
            evaluator_overrides={
                "proto_a_v1": _mock_evaluator("proto_a_v1", triggered=True, impact_value=-0.08),
                "proto_b_v1": _mock_evaluator("proto_b_v1", triggered=True, impact_value=0.04),
            },
        )
        context = {"schedule": {}, "team_metrics": {}}
        output = runner.run(context, sport="NBA", user_tier=Tier.PRO, shadow_mode=True)

        assert len(output.triggered_protocol_ids) == 2
        assert output.aggregate_stability_modifier == 0.0  # shadow = no aggregation
        assert output.aggregate_fragility_delta == 0.0

    def test_response_section_format(self, pdc_data):
        pdc_dir = _make_pdc_dir(pdc_data)
        runner = ProtocolRunner(
            pdc_path=pdc_dir,
            evaluator_overrides={
                "proto_a_v1": _mock_evaluator("proto_a_v1", triggered=True, impact_value=-0.06),
                "proto_b_v1": _mock_evaluator("proto_b_v1", triggered=False, impact_value=0.0),
            },
        )
        context = {"schedule": {}, "team_metrics": {}}
        output = runner.run(context, sport="NBA", user_tier=Tier.PRO)
        section = output.to_response_section()

        assert "triggeredProtocols" in section
        assert "stabilityModifier" in section
        assert "fragilityDelta" in section
        assert "artifacts" in section
        assert "protocolCount" in section
        assert section["protocolCount"] == 2
        assert section["triggeredCount"] == 1

    def test_wrong_sport_no_protocols(self, pdc_data):
        pdc_dir = _make_pdc_dir(pdc_data)
        runner = ProtocolRunner(
            pdc_path=pdc_dir,
            evaluator_overrides={},
        )
        context = {"schedule": {}, "team_metrics": {}}
        output = runner.run(context, sport="NFL", user_tier=Tier.PRO)
        assert len(output.results) == 0

    def test_evaluator_exception_captured(self, pdc_data):
        def bad_evaluator(context, thresholds):
            raise RuntimeError("evaluator exploded")

        pdc_dir = _make_pdc_dir(pdc_data)
        runner = ProtocolRunner(
            pdc_path=pdc_dir,
            evaluator_overrides={
                "proto_a_v1": bad_evaluator,
                "proto_b_v1": _mock_evaluator("proto_b_v1", triggered=False),
            },
        )
        context = {"schedule": {}, "team_metrics": {}}
        output = runner.run(context, sport="NBA", user_tier=Tier.PRO)

        assert any("exploded" in e for e in output.errors)
        assert len(output.results) == 1  # proto_b still ran


class TestRunnerWithRealEvaluators:
    """Integration test using the actual PDC and evaluators."""

    def test_real_pdc_full_run(self):
        pdc_path = Path(__file__).parents[3] / "protocols"
        if not (pdc_path / "pdc.json").exists():
            pytest.skip("protocols/pdc.json not found")

        runner = ProtocolRunner(pdc_path=pdc_path)
        context = {
            "schedule": {"played_last_night": True, "rest_hours": 16},
            "travel": {"miles": 900},
            "team_metrics": {
                "pace": 108.0,
                "pace_rank": 2,
                "starter_changes": 3,
                "minutes_disrupted_pct": 0.35,
            },
            "opponent_metrics": {"pace": 95.0, "pace_rank": 27},
            "injuries": {"count": 4, "key_players_out": ["Star A", "Star B"]},
        }
        output = runner.run(context, sport="NBA", user_tier=Tier.PRO)

        # All 3 protocols should trigger with this context
        assert len(output.triggered_protocol_ids) == 3
        assert output.aggregate_stability_modifier < 0
        assert output.aggregate_fragility_delta > 0
        assert len(output.all_artifacts) == 3

        section = output.to_response_section()
        assert section["triggeredCount"] == 3

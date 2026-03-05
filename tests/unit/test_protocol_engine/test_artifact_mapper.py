"""Tests for ArtifactMapper."""

import pytest
from protocol_engine.artifact_mapper import (
    artifacts_to_dict,
    map_artifacts,
    validate_artifacts,
)
from protocol_engine.models import (
    Category,
    Impact,
    ImpactType,
    ProtocolDefinition,
    ProtocolSignal,
    Tier,
)


@pytest.fixture
def proto_def():
    return ProtocolDefinition(
        protocol_id="test_v1",
        name="Test",
        sport=["NBA"],
        category=Category.PHYSICAL_STATE,
        enabled=True,
        tier=Tier.PRO,
        inputs={"required": ["schedule"]},
        evaluator={"type": "python", "module": "test", "entrypoint": "evaluate"},
        thresholds={},
        weights={"riskWeight": 0.10},
        impact_model={"type": "stability_modifier", "mode": "additive", "clamp": {"min": -0.12, "max": 0.0}},
        artifact_mapping={
            "evidence": {
                "summaryTemplate": "Test evidence summary.",
                "fields": ["field_a", "field_b"],
            },
            "weight": {
                "target": "stabilityModifier",
                "deltaPath": "impact.value",
            },
            "auditNote": {
                "noteTemplate": "Applied test protocol.",
            },
        },
        explain_templates={"title": "Test"},
    )


class TestMapArtifacts:
    def test_triggered_produces_evidence_and_audit(self, proto_def):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=True,
            confidence=0.80,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=-0.05),
            evidence_data={"field_a": 1, "field_b": 2, "field_c": 3},
        )
        artifacts = map_artifacts(signal, proto_def)
        assert artifacts.evidence is not None
        assert artifacts.evidence.summary == "Test evidence summary."
        assert artifacts.audit_note is not None
        assert artifacts.audit_note.note == "Applied test protocol."

    def test_triggered_with_impact_produces_weight(self, proto_def):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=True,
            confidence=0.80,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=-0.05),
            evidence_data={"field_a": 1, "field_b": 2},
        )
        artifacts = map_artifacts(signal, proto_def)
        assert artifacts.weight is not None
        assert artifacts.weight.target == "stabilityModifier"
        assert artifacts.weight.delta == -0.05

    def test_triggered_zero_impact_no_weight(self, proto_def):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=True,
            confidence=0.80,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=0.0),
            evidence_data={"field_a": 1},
        )
        artifacts = map_artifacts(signal, proto_def)
        assert artifacts.weight is None

    def test_not_triggered_empty_artifacts(self, proto_def):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=False,
            confidence=0.90,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=0.0),
        )
        artifacts = map_artifacts(signal, proto_def)
        assert artifacts.evidence is None
        assert artifacts.weight is None
        assert artifacts.audit_note is None

    def test_evidence_filters_fields(self, proto_def):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=True,
            confidence=0.80,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=-0.01),
            evidence_data={"field_a": 1, "field_b": 2, "secret_field": "nope"},
        )
        artifacts = map_artifacts(signal, proto_def)
        assert "field_a" in artifacts.evidence.fields
        assert "field_b" in artifacts.evidence.fields
        assert "secret_field" not in artifacts.evidence.fields


class TestValidateArtifacts:
    def test_valid_triggered(self, proto_def):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=True,
            confidence=0.80,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=-0.05),
            evidence_data={"field_a": 1},
        )
        artifacts = map_artifacts(signal, proto_def)
        errors = validate_artifacts(signal, artifacts)
        assert errors == []

    def test_triggered_missing_evidence(self, proto_def):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=True,
            confidence=0.80,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=0.0),
            evidence_data={},
        )
        from protocol_engine.models import ProtocolArtifacts
        artifacts = ProtocolArtifacts()  # empty
        errors = validate_artifacts(signal, artifacts)
        assert any("evidence" in e for e in errors)
        assert any("audit_note" in e for e in errors)


class TestArtifactsToDict:
    def test_full_serialization(self, proto_def):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=True,
            confidence=0.80,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=-0.05),
            evidence_data={"field_a": 1, "field_b": 2},
        )
        artifacts = map_artifacts(signal, proto_def)
        d = artifacts_to_dict(artifacts)
        assert "evidence" in d
        assert "weight" in d
        assert "auditNote" in d
        assert d["weight"]["delta"] == -0.05

    def test_empty_serialization(self, proto_def):
        from protocol_engine.models import ProtocolArtifacts
        d = artifacts_to_dict(ProtocolArtifacts())
        assert d == {}

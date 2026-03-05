"""Tests for protocol engine data models."""

import pytest
from protocol_engine.models import (
    AuditNoteArtifact,
    Category,
    EvidenceArtifact,
    Impact,
    ImpactType,
    PDCatalog,
    ProtocolArtifacts,
    ProtocolDefinition,
    ProtocolSignal,
    Tier,
    WeightArtifact,
)


class TestProtocolSignal:
    def test_valid_signal(self):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=True,
            confidence=0.85,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=-0.05),
        )
        assert signal.triggered is True
        assert signal.confidence == 0.85

    def test_confidence_out_of_range(self):
        with pytest.raises(ValueError, match="confidence must be"):
            ProtocolSignal(
                protocol_id="test_v1",
                triggered=True,
                confidence=1.5,
                impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=0),
            )

    def test_confidence_negative(self):
        with pytest.raises(ValueError, match="confidence must be"):
            ProtocolSignal(
                protocol_id="test_v1",
                triggered=False,
                confidence=-0.1,
                impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=0),
            )

    def test_evidence_data_default(self):
        signal = ProtocolSignal(
            protocol_id="test_v1",
            triggered=False,
            confidence=0.5,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=0),
        )
        assert signal.evidence_data == {}


class TestImpact:
    def test_clamp_within_bounds(self):
        value, clamped = Impact.clamp_value(-0.05, -0.12, 0.0)
        assert value == -0.05
        assert clamped is False

    def test_clamp_below_min(self):
        value, clamped = Impact.clamp_value(-0.20, -0.12, 0.0)
        assert value == -0.12
        assert clamped is True

    def test_clamp_above_max(self):
        value, clamped = Impact.clamp_value(0.05, -0.12, 0.0)
        assert value == 0.0
        assert clamped is True


class TestPDCatalog:
    @pytest.fixture
    def catalog(self):
        return PDCatalog(
            catalog_version="1.0.0",
            dna_contract_version="dna_contract_v1",
            generated_at="2026-03-05",
            defaults={},
            protocols=[
                ProtocolDefinition(
                    protocol_id="fatigue_b2b_v1",
                    name="Fatigue",
                    sport=["NBA"],
                    category=Category.PHYSICAL_STATE,
                    enabled=True,
                    tier=Tier.PRO,
                    inputs={"required": ["schedule"]},
                    evaluator={"type": "python", "module": "test", "entrypoint": "evaluate"},
                    thresholds={},
                    weights={"riskWeight": 0.12},
                    impact_model={},
                    artifact_mapping={"evidence": {}, "auditNote": {}},
                    explain_templates={"title": "Test"},
                ),
                ProtocolDefinition(
                    protocol_id="lineup_instability_v1",
                    name="Lineup",
                    sport=["NBA"],
                    category=Category.VOLATILITY,
                    enabled=True,
                    tier=Tier.FREE,
                    inputs={"required": ["team_metrics"]},
                    evaluator={"type": "python", "module": "test", "entrypoint": "evaluate"},
                    thresholds={},
                    weights={"riskWeight": 0.14},
                    impact_model={},
                    artifact_mapping={"evidence": {}, "auditNote": {}},
                    explain_templates={"title": "Test"},
                ),
                ProtocolDefinition(
                    protocol_id="disabled_v1",
                    name="Disabled",
                    sport=["NBA"],
                    category=Category.PSYCHOLOGY,
                    enabled=False,
                    tier=Tier.PRO,
                    inputs={"required": []},
                    evaluator={"type": "python", "module": "test", "entrypoint": "evaluate"},
                    thresholds={},
                    weights={},
                    impact_model={},
                    artifact_mapping={"evidence": {}, "auditNote": {}},
                    explain_templates={"title": "Test"},
                ),
            ],
        )

    def test_get_protocol(self, catalog):
        p = catalog.get_protocol("fatigue_b2b_v1")
        assert p is not None
        assert p.name == "Fatigue"

    def test_get_protocol_missing(self, catalog):
        assert catalog.get_protocol("nonexistent") is None

    def test_get_protocols_for_sport(self, catalog):
        nba = catalog.get_protocols_for_sport("NBA")
        assert len(nba) == 3

    def test_get_protocols_for_sport_empty(self, catalog):
        nfl = catalog.get_protocols_for_sport("NFL")
        assert len(nfl) == 0

    def test_get_enabled_protocols_pro(self, catalog):
        enabled = catalog.get_enabled_protocols("NBA", Tier.PRO)
        assert len(enabled) == 2
        ids = {p.protocol_id for p in enabled}
        assert "fatigue_b2b_v1" in ids
        assert "lineup_instability_v1" in ids
        assert "disabled_v1" not in ids

    def test_get_enabled_protocols_free(self, catalog):
        enabled = catalog.get_enabled_protocols("NBA", Tier.FREE)
        assert len(enabled) == 1
        assert enabled[0].protocol_id == "lineup_instability_v1"

    def test_tier_gating_internal(self, catalog):
        enabled = catalog.get_enabled_protocols("NBA", Tier.INTERNAL)
        assert len(enabled) == 2  # disabled still excluded


class TestEnums:
    def test_category_values(self):
        assert Category.PHYSICAL_STATE.value == "physical_state"
        assert Category.TACTICAL_MATCHUP.value == "tactical_matchup"

    def test_tier_values(self):
        assert Tier.FREE.value == "FREE"
        assert Tier.ELITE.value == "ELITE"

    def test_impact_type_values(self):
        assert ImpactType.STABILITY_MODIFIER.value == "stability_modifier"
        assert ImpactType.FRAGILITY_DELTA.value == "fragility_delta"

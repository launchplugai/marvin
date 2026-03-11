"""Tests for PDC loader and validator."""

import json
import tempfile
from pathlib import Path

import pytest
from protocol_engine.loader import (
    PDCValidationError,
    _merge_overlay,
    load_pdc,
    validate_pdc,
)
from protocol_engine.models import Category, Tier


@pytest.fixture
def valid_pdc_data():
    return {
        "catalogVersion": "1.0.0",
        "dnaContractVersion": "dna_contract_v1",
        "generatedAt": "2026-03-05T00:00:00Z",
        "defaults": {
            "enabled": True,
            "tier": "PRO",
            "riskWeight": 0.10,
        },
        "protocols": [
            {
                "protocolId": "test_v1",
                "name": "Test Protocol",
                "sport": ["NBA"],
                "category": "physical_state",
                "enabled": True,
                "tier": "PRO",
                "inputs": {"required": ["schedule"], "optional": []},
                "evaluator": {"type": "python", "module": "test_mod", "entrypoint": "evaluate"},
                "thresholds": {"foo": 1},
                "weights": {"riskWeight": 0.10},
                "impactModel": {"type": "stability_modifier", "mode": "additive", "clamp": {"min": -0.12, "max": 0.0}},
                "artifactMapping": {
                    "evidence": {"summaryTemplate": "Test.", "fields": ["a"]},
                    "auditNote": {"noteTemplate": "Test note."},
                },
                "explainTemplates": {"title": "Test title"},
                "tags": ["test"],
            }
        ],
    }


class TestValidatePDC:
    def test_valid_data(self, valid_pdc_data):
        errors = validate_pdc(valid_pdc_data)
        assert errors == []

    def test_missing_catalog_version(self, valid_pdc_data):
        del valid_pdc_data["catalogVersion"]
        errors = validate_pdc(valid_pdc_data)
        assert any("catalogVersion" in e for e in errors)

    def test_missing_dna_contract_version(self, valid_pdc_data):
        del valid_pdc_data["dnaContractVersion"]
        errors = validate_pdc(valid_pdc_data)
        assert any("dnaContractVersion" in e for e in errors)

    def test_missing_protocols(self, valid_pdc_data):
        del valid_pdc_data["protocols"]
        errors = validate_pdc(valid_pdc_data)
        assert any("protocols" in e for e in errors)

    def test_duplicate_protocol_id(self, valid_pdc_data):
        valid_pdc_data["protocols"].append(valid_pdc_data["protocols"][0])
        errors = validate_pdc(valid_pdc_data)
        assert any("Duplicate" in e for e in errors)

    def test_invalid_category(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["category"] = "invalid_cat"
        errors = validate_pdc(valid_pdc_data)
        assert any("invalid category" in e for e in errors)

    def test_invalid_tier(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["tier"] = "PLATINUM"
        errors = validate_pdc(valid_pdc_data)
        assert any("invalid tier" in e for e in errors)

    def test_risk_weight_out_of_range(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["weights"]["riskWeight"] = 1.5
        errors = validate_pdc(valid_pdc_data)
        assert any("riskWeight" in e for e in errors)

    def test_clamp_min_greater_than_max(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["impactModel"]["clamp"] = {"min": 0.5, "max": -0.5}
        errors = validate_pdc(valid_pdc_data)
        assert any("clamp" in e for e in errors)

    def test_invalid_impact_type(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["impactModel"]["type"] = "magic"
        errors = validate_pdc(valid_pdc_data)
        assert any("impactModel.type" in e for e in errors)

    def test_missing_evaluator_module(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["evaluator"] = {"type": "python", "entrypoint": "evaluate"}
        errors = validate_pdc(valid_pdc_data)
        assert any("evaluator.module" in e for e in errors)

    def test_missing_evidence_in_artifact_mapping(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["artifactMapping"] = {"auditNote": {"noteTemplate": "x"}}
        errors = validate_pdc(valid_pdc_data)
        assert any("evidence" in e for e in errors)

    def test_missing_audit_note_in_artifact_mapping(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["artifactMapping"] = {"evidence": {"summaryTemplate": "x"}}
        errors = validate_pdc(valid_pdc_data)
        assert any("auditNote" in e for e in errors)

    def test_sport_must_be_array(self, valid_pdc_data):
        valid_pdc_data["protocols"][0]["sport"] = "NBA"
        errors = validate_pdc(valid_pdc_data)
        assert any("array" in e for e in errors)


class TestLoadPDC:
    def test_load_from_file(self, valid_pdc_data):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdc_file = Path(tmpdir) / "pdc.json"
            pdc_file.write_text(json.dumps(valid_pdc_data))

            catalog = load_pdc(Path(tmpdir))
            assert catalog.catalog_version == "1.0.0"
            assert len(catalog.protocols) == 1
            assert catalog.protocols[0].protocol_id == "test_v1"
            assert catalog.protocols[0].category == Category.PHYSICAL_STATE
            assert catalog.protocols[0].tier == Tier.PRO

    def test_load_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                load_pdc(Path(tmpdir))

    def test_load_invalid_strict(self, valid_pdc_data):
        del valid_pdc_data["catalogVersion"]
        with tempfile.TemporaryDirectory() as tmpdir:
            pdc_file = Path(tmpdir) / "pdc.json"
            pdc_file.write_text(json.dumps(valid_pdc_data))

            with pytest.raises(PDCValidationError):
                load_pdc(Path(tmpdir), strict=True)

    def test_load_real_pdc(self):
        """Test loading the actual protocols/pdc.json from the repo."""
        pdc_path = Path(__file__).parents[3] / "protocols"
        if not (pdc_path / "pdc.json").exists():
            pytest.skip("protocols/pdc.json not found")

        catalog = load_pdc(pdc_path)
        assert catalog.catalog_version == "1.0.0"
        assert len(catalog.protocols) == 3
        ids = {p.protocol_id for p in catalog.protocols}
        assert ids == {"fatigue_b2b_v1", "pace_shock_v1", "lineup_instability_v1"}


class TestMergeOverlay:
    def test_overlay_changes_safe_fields(self):
        base = {
            "defaults": {"enabled": True},
            "protocols": [
                {"protocolId": "test_v1", "enabled": True, "tier": "PRO", "name": "Test"}
            ],
        }
        overlay = {
            "protocols": [
                {"protocolId": "test_v1", "enabled": False, "tier": "ELITE"}
            ],
        }
        result = _merge_overlay(base, overlay)
        assert result["protocols"][0]["enabled"] is False
        assert result["protocols"][0]["tier"] == "ELITE"
        assert result["protocols"][0]["name"] == "Test"  # unchanged

    def test_overlay_cannot_change_id(self):
        base = {
            "protocols": [
                {"protocolId": "test_v1", "name": "Original"}
            ],
        }
        overlay = {
            "protocols": [
                {"protocolId": "test_v1", "name": "Changed"}
            ],
        }
        result = _merge_overlay(base, overlay)
        assert result["protocols"][0]["name"] == "Original"  # name is not a safe field

    def test_overlay_merges_defaults(self):
        base = {"defaults": {"enabled": True, "riskWeight": 0.10}, "protocols": []}
        overlay = {"defaults": {"riskWeight": 0.20}}
        result = _merge_overlay(base, overlay)
        assert result["defaults"]["riskWeight"] == 0.20
        assert result["defaults"]["enabled"] is True

"""PDC Loader — reads, merges overlays, and validates protocol definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from protocol_engine.models import (
    Category,
    PDCatalog,
    ProtocolDefinition,
    Tier,
)


class PDCValidationError(Exception):
    """Raised when PDC fails validation."""
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"PDC validation failed with {len(errors)} error(s):\n" +
                         "\n".join(f"  - {e}" for e in errors))


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_pdc(
    base_path: Path,
    sport: Optional[str] = None,
    env: Optional[str] = None,
    strict: bool = True,
) -> PDCatalog:
    """Load PDC from base file, optionally merging sport and env overlays.

    Args:
        base_path: Path to the protocols/ directory containing pdc.json.
        sport: Optional sport code (e.g. "nba") to load sport-specific overlay.
        env: Optional environment (e.g. "dev", "prod") to load env overlay.
        strict: If True, raise on validation errors. If False, collect and return.

    Returns:
        A validated PDCatalog.

    Raises:
        PDCValidationError: If validation fails and strict=True.
        FileNotFoundError: If base pdc.json doesn't exist.
    """
    base_file = base_path / "pdc.json"
    if not base_file.exists():
        raise FileNotFoundError(f"PDC base file not found: {base_file}")

    with open(base_file) as f:
        data = json.load(f)

    # Merge sport overlay
    if sport:
        sport_file = base_path / f"pdc.{sport.lower()}.json"
        if sport_file.exists():
            with open(sport_file) as f:
                overlay = json.load(f)
            data = _merge_overlay(data, overlay)

    # Merge env overlay
    if env:
        env_file = base_path / f"pdc.{env.lower()}.overlay.json"
        if env_file.exists():
            with open(env_file) as f:
                overlay = json.load(f)
            data = _merge_overlay(data, overlay)

    # Validate
    errors = validate_pdc(data)
    if errors and strict:
        raise PDCValidationError(errors)

    return _parse_catalog(data)


# ---------------------------------------------------------------------------
# Overlay Merge (safe fields only)
# ---------------------------------------------------------------------------

_SAFE_OVERLAY_FIELDS = {"enabled", "weights", "thresholds", "tier"}


def _merge_overlay(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Merge overlay into base. Overlays can only change safe fields on protocols."""
    result = dict(base)

    if "defaults" in overlay:
        result["defaults"] = {**base.get("defaults", {}), **overlay["defaults"]}

    if "protocols" in overlay:
        overlay_map = {p["protocolId"]: p for p in overlay["protocols"]}
        merged_protocols = []
        for proto in result.get("protocols", []):
            pid = proto["protocolId"]
            if pid in overlay_map:
                merged = dict(proto)
                for key in _SAFE_OVERLAY_FIELDS:
                    if key in overlay_map[pid]:
                        merged[key] = overlay_map[pid][key]
                merged_protocols.append(merged)
            else:
                merged_protocols.append(proto)
        result["protocols"] = merged_protocols

    return result


# ---------------------------------------------------------------------------
# Validation (PDC Linter)
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = {c.value for c in Category}
_VALID_TIERS = {t.value for t in Tier}
_VALID_IMPACT_TYPES = {"stability_modifier", "fragility_delta", "constraint_flag", "confidence_adjustment"}
_VALID_IMPACT_MODES = {"additive", "multiplicative"}


def validate_pdc(data: Dict[str, Any]) -> List[str]:
    """Validate PDC data and return list of error strings. Empty = valid."""
    errors: List[str] = []

    # Top-level
    if "catalogVersion" not in data:
        errors.append("Missing top-level 'catalogVersion'")
    if "dnaContractVersion" not in data:
        errors.append("Missing top-level 'dnaContractVersion'")
    if "protocols" not in data or not isinstance(data.get("protocols"), list):
        errors.append("Missing or invalid 'protocols' array")
        return errors

    # Unique IDs
    seen_ids = set()
    for i, proto in enumerate(data["protocols"]):
        pid = proto.get("protocolId", f"<missing at index {i}>")

        if "protocolId" not in proto:
            errors.append(f"Protocol at index {i}: missing 'protocolId'")
            continue

        if pid in seen_ids:
            errors.append(f"Duplicate protocolId: '{pid}'")
        seen_ids.add(pid)

        # Required fields
        for req in ["name", "sport", "category", "enabled", "tier",
                     "inputs", "evaluator", "thresholds", "weights",
                     "impactModel", "artifactMapping", "explainTemplates"]:
            if req not in proto:
                errors.append(f"{pid}: missing required field '{req}'")

        # Category
        cat = proto.get("category")
        if cat and cat not in _VALID_CATEGORIES:
            errors.append(f"{pid}: invalid category '{cat}'. Valid: {_VALID_CATEGORIES}")

        # Tier
        tier = proto.get("tier")
        if tier and tier not in _VALID_TIERS:
            errors.append(f"{pid}: invalid tier '{tier}'. Valid: {_VALID_TIERS}")

        # Sport must be array
        sport = proto.get("sport")
        if sport is not None and not isinstance(sport, list):
            errors.append(f"{pid}: 'sport' must be an array")

        # Weights
        weights = proto.get("weights", {})
        rw = weights.get("riskWeight")
        if rw is not None and not (0.0 <= rw <= 1.0):
            errors.append(f"{pid}: riskWeight must be 0.0–1.0, got {rw}")

        # Impact model
        im = proto.get("impactModel", {})
        if im.get("type") and im["type"] not in _VALID_IMPACT_TYPES:
            errors.append(f"{pid}: invalid impactModel.type '{im['type']}'")
        if im.get("mode") and im["mode"] not in _VALID_IMPACT_MODES:
            errors.append(f"{pid}: invalid impactModel.mode '{im['mode']}'")

        clamp = im.get("clamp", {})
        if "min" in clamp and "max" in clamp:
            if clamp["min"] > clamp["max"]:
                errors.append(f"{pid}: impactModel.clamp.min ({clamp['min']}) > max ({clamp['max']})")

        # Evaluator
        ev = proto.get("evaluator", {})
        if ev and not ev.get("module"):
            errors.append(f"{pid}: evaluator.module is required")
        if ev and not ev.get("entrypoint"):
            errors.append(f"{pid}: evaluator.entrypoint is required")

        # Inputs
        inputs = proto.get("inputs", {})
        if inputs and "required" not in inputs:
            errors.append(f"{pid}: inputs.required is required")

        # Artifact mapping
        am = proto.get("artifactMapping", {})
        if am and "evidence" not in am:
            errors.append(f"{pid}: artifactMapping.evidence is required")
        if am and "auditNote" not in am:
            errors.append(f"{pid}: artifactMapping.auditNote is required")

        # Explain templates
        et = proto.get("explainTemplates", {})
        if et and not et.get("title"):
            errors.append(f"{pid}: explainTemplates.title is required")

    return errors


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_catalog(data: Dict[str, Any]) -> PDCatalog:
    """Parse raw JSON dict into typed PDCatalog."""
    protocols = []
    for p in data.get("protocols", []):
        protocols.append(ProtocolDefinition(
            protocol_id=p["protocolId"],
            name=p["name"],
            sport=p["sport"],
            category=Category(p["category"]),
            enabled=p["enabled"],
            tier=Tier(p["tier"]),
            inputs=p["inputs"],
            evaluator=p["evaluator"],
            thresholds=p["thresholds"],
            weights=p["weights"],
            impact_model=p["impactModel"],
            artifact_mapping=p["artifactMapping"],
            explain_templates=p["explainTemplates"],
            tags=p.get("tags", []),
        ))

    return PDCatalog(
        catalog_version=data["catalogVersion"],
        dna_contract_version=data["dnaContractVersion"],
        generated_at=data["generatedAt"],
        defaults=data["defaults"],
        protocols=protocols,
    )

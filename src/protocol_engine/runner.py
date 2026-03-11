"""ProtocolRunner — orchestrates PDC loading, evaluator dispatch, and artifact aggregation."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from protocol_engine.artifact_mapper import (
    artifacts_to_dict,
    map_artifacts,
    validate_artifacts,
)
from protocol_engine.loader import load_pdc
from protocol_engine.models import (
    PDCatalog,
    ProtocolArtifacts,
    ProtocolDefinition,
    ProtocolSignal,
    Tier,
)

logger = logging.getLogger(__name__)


@dataclass
class ProtocolResult:
    """Result of running a single protocol."""

    protocol_id: str
    signal: ProtocolSignal
    artifacts: ProtocolArtifacts
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class RunnerOutput:
    """Aggregated output from running all applicable protocols."""

    results: List[ProtocolResult] = field(default_factory=list)
    aggregate_stability_modifier: float = 0.0
    aggregate_fragility_delta: float = 0.0
    aggregate_confidence_adjustment: float = 0.0
    triggered_protocol_ids: List[str] = field(default_factory=list)
    all_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_response_section(self) -> Dict[str, Any]:
        """Format for inclusion in API response protocol section."""
        return {
            "triggeredProtocols": self.triggered_protocol_ids,
            "stabilityModifier": round(self.aggregate_stability_modifier, 6),
            "fragilityDelta": round(self.aggregate_fragility_delta, 6),
            "confidenceAdjustment": round(self.aggregate_confidence_adjustment, 6),
            "artifacts": self.all_artifacts,
            "protocolCount": len(self.results),
            "triggeredCount": len(self.triggered_protocol_ids),
        }


class ProtocolRunner:
    """Loads PDC, runs evaluators, aggregates impacts, emits artifacts."""

    def __init__(
        self,
        pdc_path: Path,
        sport: Optional[str] = None,
        env: Optional[str] = None,
        strict: bool = True,
        evaluator_overrides: Optional[Dict[str, Callable]] = None,
    ):
        self.catalog = load_pdc(pdc_path, sport=sport, env=env, strict=strict)
        self._evaluator_overrides = evaluator_overrides or {}
        self._evaluator_cache: Dict[str, Callable] = {}

    def run(
        self,
        context: Dict[str, Any],
        sport: str,
        user_tier: Tier = Tier.PRO,
        shadow_mode: bool = False,
    ) -> RunnerOutput:
        """Run all applicable protocols against the given context.

        Args:
            context: The runtime context dict containing all input data.
            sport: Sport code (e.g. "NBA").
            user_tier: User's subscription tier for gating.
            shadow_mode: If True, run protocols but don't apply impacts (compare mode).

        Returns:
            RunnerOutput with aggregated results.
        """
        protocols = self.catalog.get_enabled_protocols(sport, user_tier)
        output = RunnerOutput()

        for proto_def in protocols:
            # Check required inputs
            missing = self._check_inputs(proto_def, context)
            if missing:
                logger.warning(
                    "Skipping %s: missing required inputs: %s",
                    proto_def.protocol_id, missing,
                )
                output.errors.append(
                    f"{proto_def.protocol_id}: missing inputs {missing}"
                )
                continue

            try:
                result = self._run_single(proto_def, context)
                output.results.append(result)

                if result.signal.triggered:
                    output.triggered_protocol_ids.append(result.protocol_id)

                    # Aggregate impacts (unless shadow mode)
                    if not shadow_mode:
                        self._aggregate_impact(output, result)

                    # Collect artifacts
                    if result.validation_errors:
                        output.errors.extend(result.validation_errors)
                    else:
                        artifact_dict = artifacts_to_dict(result.artifacts)
                        if artifact_dict:
                            output.all_artifacts.append(artifact_dict)

            except Exception as e:
                logger.error("Protocol %s failed: %s", proto_def.protocol_id, e)
                output.errors.append(f"{proto_def.protocol_id}: {e}")

        return output

    def _run_single(
        self,
        proto_def: ProtocolDefinition,
        context: Dict[str, Any],
    ) -> ProtocolResult:
        """Run a single protocol evaluator and map artifacts."""
        evaluator_fn = self._resolve_evaluator(proto_def)
        signal = evaluator_fn(context, proto_def.thresholds)

        min_emit = self.catalog.defaults.get("confidence", {}).get("minEmitConfidence", 0.50)
        artifacts = map_artifacts(signal, proto_def, min_emit_confidence=min_emit)
        validation_errors = validate_artifacts(signal, artifacts)

        return ProtocolResult(
            protocol_id=proto_def.protocol_id,
            signal=signal,
            artifacts=artifacts,
            validation_errors=validation_errors,
        )

    def _resolve_evaluator(self, proto_def: ProtocolDefinition) -> Callable:
        """Resolve evaluator function from PDC evaluator spec."""
        pid = proto_def.protocol_id

        # Check overrides first (for testing)
        if pid in self._evaluator_overrides:
            return self._evaluator_overrides[pid]

        # Check cache
        if pid in self._evaluator_cache:
            return self._evaluator_cache[pid]

        ev = proto_def.evaluator
        module_path = ev["module"]
        entrypoint = ev["entrypoint"]

        module = importlib.import_module(module_path)
        fn = getattr(module, entrypoint)

        self._evaluator_cache[pid] = fn
        return fn

    def _check_inputs(
        self,
        proto_def: ProtocolDefinition,
        context: Dict[str, Any],
    ) -> List[str]:
        """Check that all required inputs are present in context."""
        required = proto_def.inputs.get("required", [])
        return [key for key in required if key not in context]

    def _aggregate_impact(self, output: RunnerOutput, result: ProtocolResult) -> None:
        """Add a protocol's impact to the aggregate totals."""
        impact = result.signal.impact
        impact_type = impact.impact_type.value

        if impact_type == "stability_modifier":
            output.aggregate_stability_modifier += impact.value
        elif impact_type == "fragility_delta":
            output.aggregate_fragility_delta += impact.value
        elif impact_type == "confidence_adjustment":
            output.aggregate_confidence_adjustment += impact.value

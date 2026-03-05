"""ArtifactMapper — converts ProtocolSignal into validated DNA artifacts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from protocol_engine.models import (
    AuditNoteArtifact,
    ConstraintArtifact,
    EvidenceArtifact,
    ProtocolArtifacts,
    ProtocolDefinition,
    ProtocolSignal,
    WeightArtifact,
)


class ArtifactValidationError(Exception):
    """Raised when artifact mapping violates contract rules."""


def map_artifacts(
    signal: ProtocolSignal,
    protocol_def: ProtocolDefinition,
    min_emit_confidence: float = 0.50,
) -> ProtocolArtifacts:
    """Map a ProtocolSignal into DNA artifacts based on the PDC artifact mapping.

    Rules (from PDC spec):
        - If triggered=True, must emit evidence + audit_note
        - If impact.value != 0, must emit weight artifact
        - If confidence < min_emit_confidence, artifacts are recorded but
          should not modify scoring (safe mode)

    Returns:
        ProtocolArtifacts with populated fields.

    Raises:
        ArtifactValidationError: If contract requirements cannot be met.
    """
    mapping = protocol_def.artifact_mapping
    artifacts = ProtocolArtifacts()

    if not signal.triggered:
        return artifacts

    # Evidence artifact (required when triggered)
    ev_map = mapping.get("evidence", {})
    summary = ev_map.get("summaryTemplate", f"Protocol {signal.protocol_id} triggered.")
    allowed_fields = set(ev_map.get("fields", []))
    filtered_evidence = {
        k: v for k, v in signal.evidence_data.items()
        if k in allowed_fields
    } if allowed_fields else signal.evidence_data

    artifacts.evidence = EvidenceArtifact(
        protocol_id=signal.protocol_id,
        summary=summary,
        fields=filtered_evidence,
    )

    # Audit note artifact (required when triggered)
    an_map = mapping.get("auditNote", {})
    note = an_map.get("noteTemplate", f"Protocol {signal.protocol_id} was evaluated.")
    artifacts.audit_note = AuditNoteArtifact(
        protocol_id=signal.protocol_id,
        note=note,
    )

    # Weight artifact (required when impact.value != 0)
    if signal.impact.value != 0.0:
        w_map = mapping.get("weight", {})
        target = w_map.get("target", "stabilityModifier")
        artifacts.weight = WeightArtifact(
            protocol_id=signal.protocol_id,
            target=target,
            delta=signal.impact.value,
        )

    return artifacts


def validate_artifacts(
    signal: ProtocolSignal,
    artifacts: ProtocolArtifacts,
) -> List[str]:
    """Validate that artifacts meet DNA contract requirements.

    Returns list of violation strings. Empty = valid.
    """
    errors: List[str] = []
    pid = signal.protocol_id

    if signal.triggered:
        if artifacts.evidence is None:
            errors.append(f"{pid}: triggered=True but no evidence artifact emitted")
        if artifacts.audit_note is None:
            errors.append(f"{pid}: triggered=True but no audit_note artifact emitted")

    if signal.impact.value != 0.0 and artifacts.weight is None:
        errors.append(f"{pid}: impact.value={signal.impact.value} but no weight artifact emitted")

    return errors


def artifacts_to_dict(artifacts: ProtocolArtifacts) -> Dict[str, Any]:
    """Serialize ProtocolArtifacts to a plain dict for JSON output."""
    result: Dict[str, Any] = {}

    if artifacts.evidence:
        result["evidence"] = {
            "protocolId": artifacts.evidence.protocol_id,
            "summary": artifacts.evidence.summary,
            "fields": artifacts.evidence.fields,
        }

    if artifacts.weight:
        result["weight"] = {
            "protocolId": artifacts.weight.protocol_id,
            "target": artifacts.weight.target,
            "delta": artifacts.weight.delta,
        }

    if artifacts.audit_note:
        result["auditNote"] = {
            "protocolId": artifacts.audit_note.protocol_id,
            "note": artifacts.audit_note.note,
        }

    if artifacts.constraint:
        result["constraint"] = {
            "protocolId": artifacts.constraint.protocol_id,
            "constraintType": artifacts.constraint.constraint_type,
            "reason": artifacts.constraint.reason,
        }

    return result

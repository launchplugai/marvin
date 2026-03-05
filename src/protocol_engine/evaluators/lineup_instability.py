"""Evaluator: Lineup Instability (lineup_instability_v1)

Detects when a team has significant rotation disruption due to
injuries, trades, or unusual lineup changes.
Domain: volatility
"""

from __future__ import annotations

from typing import Any, Dict, List

from protocol_engine.models import Impact, ImpactType, ProtocolSignal


def evaluate(context: Dict[str, Any], thresholds: Dict[str, Any]) -> ProtocolSignal:
    """Evaluate lineup instability.

    Required context keys:
        team_metrics: dict with 'starter_changes' (int), 'minutes_disrupted_pct' (float)
        injuries: dict with 'count' (int), 'key_players_out' (list[str])

    Returns:
        ProtocolSignal with triggered=True if lineup is significantly disrupted.
    """
    team = context.get("team_metrics", {})
    injuries = context.get("injuries", {})

    starter_changes = team.get("starter_changes", 0)
    minutes_pct = team.get("minutes_disrupted_pct", 0.0)
    injury_count = injuries.get("count", 0)
    key_players_out: List[str] = injuries.get("key_players_out", [])

    starter_min = thresholds.get("starterChangesMin", 2)
    minutes_min = thresholds.get("minutesDisruptedPctMin", 0.30)
    injury_min = thresholds.get("injuryCountMin", 3)

    # Trigger if ANY two of three conditions met
    conditions_met = sum([
        starter_changes >= starter_min,
        minutes_pct >= minutes_min,
        injury_count >= injury_min,
    ])
    triggered = conditions_met >= 2

    evidence = {
        "starter_changes": starter_changes,
        "minutes_disrupted_pct": minutes_pct,
        "injury_count": injury_count,
        "key_players_out": key_players_out,
    }

    if not triggered:
        return ProtocolSignal(
            protocol_id="lineup_instability_v1",
            triggered=False,
            confidence=0.80,
            impact=Impact(impact_type=ImpactType.FRAGILITY_DELTA, value=0.0),
            evidence_data=evidence,
        )

    # Severity based on how many conditions and how extreme
    starter_severity = min(1.0, starter_changes / 4.0) if starter_changes >= starter_min else 0
    minutes_severity = min(1.0, minutes_pct / 0.60) if minutes_pct >= minutes_min else 0
    injury_severity = min(1.0, injury_count / 6.0) if injury_count >= injury_min else 0
    severity = max(starter_severity, minutes_severity, injury_severity)

    raw_impact = 0.12 * severity

    value, clamped = Impact.clamp_value(raw_impact, 0.00, 0.12)

    return ProtocolSignal(
        protocol_id="lineup_instability_v1",
        triggered=True,
        confidence=min(0.90, 0.65 + 0.25 * severity),
        impact=Impact(
            impact_type=ImpactType.FRAGILITY_DELTA,
            value=value,
            clamped=clamped,
        ),
        evidence_data=evidence,
    )

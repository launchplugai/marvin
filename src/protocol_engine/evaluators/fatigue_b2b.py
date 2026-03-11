"""Evaluator: Back-to-Back Fatigue (fatigue_b2b_v1)

Detects when a team is playing on short rest with travel strain.
Domain: physical_state
"""

from __future__ import annotations

from typing import Any, Dict

from protocol_engine.models import Impact, ImpactType, ProtocolSignal


def evaluate(context: Dict[str, Any], thresholds: Dict[str, Any]) -> ProtocolSignal:
    """Evaluate back-to-back fatigue risk.

    Required context keys:
        schedule: dict with 'played_last_night' (bool), 'rest_hours' (float)
        travel: dict with 'miles' (float)
        team_metrics: dict with team performance data

    Returns:
        ProtocolSignal with triggered=True if B2B + travel strain detected.
    """
    schedule = context.get("schedule", {})
    travel = context.get("travel", {})

    played_last_night = schedule.get("played_last_night", False)
    rest_hours = schedule.get("rest_hours", 48.0)
    travel_miles = travel.get("miles", 0.0)

    travel_miles_min = thresholds.get("travelMilesMin", 600)
    rest_hours_max = thresholds.get("restHoursMax", 24)

    is_b2b = played_last_night or rest_hours <= rest_hours_max
    has_travel_strain = travel_miles >= travel_miles_min
    triggered = is_b2b and has_travel_strain

    if not triggered:
        return ProtocolSignal(
            protocol_id="fatigue_b2b_v1",
            triggered=False,
            confidence=0.9,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=0.0),
            evidence_data={
                "played_last_night": played_last_night,
                "rest_hours": rest_hours,
                "travel_miles": travel_miles,
            },
        )

    # Severity scales with travel distance and rest deficit
    rest_deficit = max(0, rest_hours_max - rest_hours) / rest_hours_max
    travel_factor = min(1.0, travel_miles / 2000.0)
    severity = 0.5 * rest_deficit + 0.5 * travel_factor
    raw_impact = -0.12 * severity

    value, clamped = Impact.clamp_value(raw_impact, -0.12, 0.00)

    return ProtocolSignal(
        protocol_id="fatigue_b2b_v1",
        triggered=True,
        confidence=min(0.95, 0.70 + 0.25 * severity),
        impact=Impact(
            impact_type=ImpactType.STABILITY_MODIFIER,
            value=value,
            clamped=clamped,
        ),
        evidence_data={
            "played_last_night": played_last_night,
            "rest_hours": rest_hours,
            "travel_miles": travel_miles,
        },
    )

"""Evaluator: Pace Mismatch Shock (pace_shock_v1)

Detects when two teams have vastly different pace of play,
creating scoring volatility.
Domain: tactical_matchup
"""

from __future__ import annotations

from typing import Any, Dict

from protocol_engine.models import Impact, ImpactType, ProtocolSignal


def evaluate(context: Dict[str, Any], thresholds: Dict[str, Any]) -> ProtocolSignal:
    """Evaluate pace mismatch shock.

    Required context keys:
        team_metrics: dict with 'pace' (float), 'pace_rank' (int)
        opponent_metrics: dict with 'pace' (float), 'pace_rank' (int)

    Returns:
        ProtocolSignal with triggered=True if significant pace differential.
    """
    team = context.get("team_metrics", {})
    opponent = context.get("opponent_metrics", {})

    team_pace = team.get("pace", 100.0)
    opp_pace = opponent.get("pace", 100.0)
    team_rank = team.get("pace_rank", 15)
    opp_rank = opponent.get("pace_rank", 15)

    pace_diff = abs(team_pace - opp_pace)
    rank_diff = abs(team_rank - opp_rank)

    pace_diff_min = thresholds.get("paceDiffMin", 4.0)
    rank_diff_min = thresholds.get("paceRankDiffMin", 8)

    triggered = pace_diff >= pace_diff_min and rank_diff >= rank_diff_min

    evidence = {
        "team_pace": team_pace,
        "opponent_pace": opp_pace,
        "pace_diff": pace_diff,
        "pace_rank_diff": rank_diff,
    }

    if not triggered:
        return ProtocolSignal(
            protocol_id="pace_shock_v1",
            triggered=False,
            confidence=0.85,
            impact=Impact(impact_type=ImpactType.STABILITY_MODIFIER, value=0.0),
            evidence_data=evidence,
        )

    # Severity scales with how extreme the mismatch is
    pace_severity = min(1.0, (pace_diff - pace_diff_min) / 6.0)
    rank_severity = min(1.0, (rank_diff - rank_diff_min) / 12.0)
    severity = 0.6 * pace_severity + 0.4 * rank_severity
    raw_impact = -0.10 * severity

    value, clamped = Impact.clamp_value(raw_impact, -0.10, 0.00)

    return ProtocolSignal(
        protocol_id="pace_shock_v1",
        triggered=True,
        confidence=min(0.92, 0.72 + 0.20 * severity),
        impact=Impact(
            impact_type=ImpactType.STABILITY_MODIFIER,
            value=value,
            clamped=clamped,
        ),
        evidence_data=evidence,
    )

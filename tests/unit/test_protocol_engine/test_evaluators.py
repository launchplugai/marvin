"""Tests for protocol evaluators."""

import pytest
from protocol_engine.evaluators.fatigue_b2b import evaluate as fatigue_evaluate
from protocol_engine.evaluators.lineup_instability import evaluate as lineup_evaluate
from protocol_engine.evaluators.pace_shock import evaluate as pace_evaluate
from protocol_engine.models import ImpactType


class TestFatigueB2B:
    THRESHOLDS = {"travelMilesMin": 600, "restHoursMax": 24}

    def test_triggers_on_b2b_with_travel(self):
        context = {
            "schedule": {"played_last_night": True, "rest_hours": 18},
            "travel": {"miles": 800},
            "team_metrics": {},
        }
        signal = fatigue_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is True
        assert signal.impact.impact_type == ImpactType.STABILITY_MODIFIER
        assert signal.impact.value < 0

    def test_no_trigger_without_travel(self):
        context = {
            "schedule": {"played_last_night": True, "rest_hours": 18},
            "travel": {"miles": 100},
            "team_metrics": {},
        }
        signal = fatigue_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is False
        assert signal.impact.value == 0.0

    def test_no_trigger_with_rest(self):
        context = {
            "schedule": {"played_last_night": False, "rest_hours": 48},
            "travel": {"miles": 1000},
            "team_metrics": {},
        }
        signal = fatigue_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is False

    def test_impact_clamped(self):
        context = {
            "schedule": {"played_last_night": True, "rest_hours": 0},
            "travel": {"miles": 3000},
            "team_metrics": {},
        }
        signal = fatigue_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is True
        assert signal.impact.value >= -0.12

    def test_evidence_fields(self):
        context = {
            "schedule": {"played_last_night": True, "rest_hours": 20},
            "travel": {"miles": 700},
            "team_metrics": {},
        }
        signal = fatigue_evaluate(context, self.THRESHOLDS)
        assert "played_last_night" in signal.evidence_data
        assert "rest_hours" in signal.evidence_data
        assert "travel_miles" in signal.evidence_data

    def test_confidence_range(self):
        context = {
            "schedule": {"played_last_night": True, "rest_hours": 10},
            "travel": {"miles": 1500},
            "team_metrics": {},
        }
        signal = fatigue_evaluate(context, self.THRESHOLDS)
        assert 0.0 <= signal.confidence <= 1.0


class TestPaceShock:
    THRESHOLDS = {"paceDiffMin": 4.0, "paceRankDiffMin": 8}

    def test_triggers_on_large_pace_diff(self):
        context = {
            "team_metrics": {"pace": 105.0, "pace_rank": 3},
            "opponent_metrics": {"pace": 95.0, "pace_rank": 25},
        }
        signal = pace_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is True
        assert signal.impact.impact_type == ImpactType.STABILITY_MODIFIER
        assert signal.impact.value < 0

    def test_no_trigger_similar_pace(self):
        context = {
            "team_metrics": {"pace": 100.0, "pace_rank": 14},
            "opponent_metrics": {"pace": 101.0, "pace_rank": 13},
        }
        signal = pace_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is False

    def test_no_trigger_pace_diff_but_close_rank(self):
        context = {
            "team_metrics": {"pace": 105.0, "pace_rank": 10},
            "opponent_metrics": {"pace": 99.0, "pace_rank": 12},
        }
        signal = pace_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is False

    def test_evidence_fields(self):
        context = {
            "team_metrics": {"pace": 108.0, "pace_rank": 1},
            "opponent_metrics": {"pace": 96.0, "pace_rank": 28},
        }
        signal = pace_evaluate(context, self.THRESHOLDS)
        assert "team_pace" in signal.evidence_data
        assert "opponent_pace" in signal.evidence_data
        assert "pace_diff" in signal.evidence_data
        assert signal.evidence_data["pace_diff"] == 12.0


class TestLineupInstability:
    THRESHOLDS = {"starterChangesMin": 2, "minutesDisruptedPctMin": 0.30, "injuryCountMin": 3}

    def test_triggers_two_conditions(self):
        context = {
            "team_metrics": {"starter_changes": 3, "minutes_disrupted_pct": 0.40},
            "injuries": {"count": 4, "key_players_out": ["Player A", "Player B"]},
        }
        signal = lineup_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is True
        assert signal.impact.impact_type == ImpactType.FRAGILITY_DELTA
        assert signal.impact.value > 0

    def test_no_trigger_one_condition(self):
        context = {
            "team_metrics": {"starter_changes": 3, "minutes_disrupted_pct": 0.10},
            "injuries": {"count": 1, "key_players_out": []},
        }
        signal = lineup_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is False

    def test_no_trigger_zero_conditions(self):
        context = {
            "team_metrics": {"starter_changes": 0, "minutes_disrupted_pct": 0.05},
            "injuries": {"count": 0, "key_players_out": []},
        }
        signal = lineup_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is False

    def test_impact_clamped(self):
        context = {
            "team_metrics": {"starter_changes": 5, "minutes_disrupted_pct": 0.80},
            "injuries": {"count": 7, "key_players_out": ["A", "B", "C", "D"]},
        }
        signal = lineup_evaluate(context, self.THRESHOLDS)
        assert signal.triggered is True
        assert signal.impact.value <= 0.12

    def test_evidence_has_key_players(self):
        context = {
            "team_metrics": {"starter_changes": 3, "minutes_disrupted_pct": 0.35},
            "injuries": {"count": 4, "key_players_out": ["Star Player"]},
        }
        signal = lineup_evaluate(context, self.THRESHOLDS)
        assert signal.evidence_data["key_players_out"] == ["Star Player"]

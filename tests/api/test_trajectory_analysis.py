import math

import pytest

from api.trajectory_analysis import albuminuria_category, gfr_category, summarize_trajectory


@pytest.mark.parametrize(
    ("value", "expected"),
    [(90, "G1"), (89.99, "G2"), (60, "G2"), (59.99, "G3a"),
     (45, "G3a"), (44.99, "G3b"), (30, "G3b"), (29.99, "G4"),
     (15, "G4"), (14.99, "G5"), (0, "G5"), (-1, None), (math.nan, None)],
)
def test_gfr_category_boundaries(value, expected):
    assert gfr_category(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "A1"), (29.99, "A1"), (30, "A2"), (300, "A2"), (300.01, "A3"), (-1, None), (math.inf, None)],
)
def test_albuminuria_category_boundaries(value, expected):
    assert albuminuria_category(value) == expected


def test_summary_uses_actual_endpoints_elapsed_time_and_percentages():
    result = summarize_trajectory([
        {"year": 0, "egfr": 80, "uacr": 100},
        {"year": 1, "egfr": 70, "uacr": 150},
        {"year": 2, "egfr": 60, "uacr": 200},
    ])
    assert result["egfr"]["starting"] == 80
    assert result["egfr"]["final"] == 60
    assert result["egfr"]["absolute_change"] == -20
    assert result["egfr"]["percent_change"] == -25
    assert result["egfr"]["average_annualized_change"] == -10
    assert result["egfr"]["elapsed_years"] == 2
    assert result["uacr"]["absolute_change"] == 100
    assert result["uacr"]["percent_change"] == 100


def test_milestones_interpolate_crossing_and_detect_twenty_percent_decline():
    result = summarize_trajectory([
        {"year": 0, "egfr": 100, "uacr": 20},
        {"year": 2, "egfr": 70, "uacr": 35},
    ])
    assert result["egfr"]["thresholds"]["60"] == {"status": "not_crossed", "time_years": None}
    assert result["egfr"]["decline_20_percent"]["status"] == "crossed"
    assert result["egfr"]["decline_20_percent"]["time_years"] == pytest.approx(4 / 3)


def test_threshold_crossing_between_points_and_below_baseline_status():
    result = summarize_trajectory([
        {"year": 0, "egfr": 70, "uacr": 40},
        {"year": 2, "egfr": 50, "uacr": 40},
        {"year": 4, "egfr": 10, "uacr": 40},
    ])
    assert result["egfr"]["thresholds"]["60"] == {"status": "crossed", "time_years": 1}
    assert result["egfr"]["thresholds"]["45"]["status"] == "crossed"
    assert result["egfr"]["thresholds"]["30"]["status"] == "crossed"
    assert result["egfr"]["thresholds"]["15"]["status"] == "crossed"
    already_below = summarize_trajectory([{"year": 0, "egfr": 14, "uacr": 20}, {"year": 1, "egfr": 10, "uacr": 20}])
    assert already_below["egfr"]["thresholds"]["15"]["status"] == "below_at_baseline"


def test_threshold_equal_at_baseline_and_no_crossing_are_explicit():
    result = summarize_trajectory([{"year": 0, "egfr": 60, "uacr": 30}, {"year": 1, "egfr": 61, "uacr": 29}])
    assert result["egfr"]["thresholds"]["60"]["status"] == "at_threshold_at_baseline"
    assert result["egfr"]["thresholds"]["45"]["status"] == "not_crossed"


def test_joint_category_transitions_use_returned_values_and_times():
    result = summarize_trajectory([
        {"year": 0, "egfr": 90, "uacr": 29},
        {"year": 0.5, "egfr": 60, "uacr": 30},
        {"year": 1, "egfr": 45, "uacr": 300},
        {"year": 1.5, "egfr": 44, "uacr": 301},
    ])
    categories = result["categories"]
    assert categories["starting"] == {"gfr": "G1", "albuminuria": "A1"}
    assert categories["final"] == {"gfr": "G3b", "albuminuria": "A3"}
    assert [row["year"] for row in categories["transitions"]] == [0.5, 1, 1.5]
    assert categories["transitions"][0]["gfr_category"] == "G2"


def test_zero_and_invalid_values_never_emit_non_finite_summary():
    result = summarize_trajectory([
        {"year": 0, "egfr": 0, "uacr": 0},
        {"year": 1, "egfr": -4, "uacr": math.nan},
        {"year": 2, "egfr": math.inf, "uacr": 5},
    ])
    assert result["egfr"]["starting"] == 0
    assert result["egfr"]["percent_change"] is None
    assert result["egfr"]["average_annualized_change"] is None
    assert result["uacr"]["starting"] == 0
    assert result["uacr"]["percent_change"] is None
    assert result["egfr"]["decline_20_percent"]["status"] == "unavailable"
    assert result["categories"]["transitions"] == []


def test_insufficient_and_empty_trajectories_are_safe():
    empty = summarize_trajectory([])
    assert empty["egfr"]["status"] == "unavailable"
    assert empty["egfr"]["thresholds"]["60"]["status"] == "unavailable"
    single = summarize_trajectory([{"year": 0, "egfr": 50, "uacr": 15}])
    assert single["egfr"]["status"] == "insufficient_points"
    assert single["egfr"]["thresholds"]["60"]["status"] == "below_at_baseline"

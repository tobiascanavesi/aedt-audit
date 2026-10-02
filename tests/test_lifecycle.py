"""Hand-computed fixtures for the lifecycle diagnostics (margin, drift, triggers)."""

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from aedt_audit import (
    AuditMetadata,
    audit_lifecycle,
    four_fifths,
    selection_rates,
    synthetic_lifecycle,
)


def period_df(male_sel, male_tot, female_sel, female_tot, race="r"):
    """A one-period pool with two sexes and a single (constant) race column."""
    sex = ["male"] * male_tot + ["female"] * female_tot
    selected = (
        [True] * male_sel
        + [False] * (male_tot - male_sel)
        + [True] * female_sel
        + [False] * (female_tot - female_sel)
    )
    return pd.DataFrame({"sex": sex, "race_ethnicity": race, "selected": selected})


def test_boundary_margin_hand_computed():
    # p1: male 5/10=0.50, female 4/10=0.40 -> female ratio 0.40/0.50 = 0.80, margin 0.0
    # p2: male 5/10=0.50, female 2/10=0.20 -> female ratio 0.20/0.50 = 0.40, margin -0.4
    report = audit_lifecycle(
        {"p1": period_df(5, 10, 4, 10), "p2": period_df(5, 10, 2, 10)}, outcome="selected"
    )
    sex = report.series["sex"]
    assert sex[0].worst_group == "female"
    assert sex[0].worst_ratio == pytest.approx(0.8)
    assert sex[0].boundary_margin == pytest.approx(0.0)
    assert sex[0].adverse_impact is False  # 0.8 is not < 0.8
    assert sex[1].worst_ratio == pytest.approx(0.4)
    assert sex[1].boundary_margin == pytest.approx(-0.4)
    assert sex[1].adverse_impact is True


def test_profile_drift_hand_computed():
    # ratios: p1 {male 1.0, female 0.8}, p2 {male 1.0, female 0.4}
    # delta = (0.0, -0.4); drift = ||delta|| / sqrt(2) = 0.4 / sqrt(2)
    report = audit_lifecycle(
        {"p1": period_df(5, 10, 4, 10), "p2": period_df(5, 10, 2, 10)}, outcome="selected"
    )
    sex = report.series["sex"]
    assert sex[0].drift is None  # no prior period at horizon 1
    assert sex[1].drift == pytest.approx(0.4 / math.sqrt(2))


def test_crossed_four_fifths_flips_on_threshold_crossing():
    report = audit_lifecycle(
        {"p1": period_df(5, 10, 4, 10), "p2": period_df(5, 10, 2, 10)}, outcome="selected"
    )
    sex = report.series["sex"]
    assert sex[0].crossed_four_fifths is False  # first period, nothing to cross from
    assert sex[1].crossed_four_fifths is True  # False -> True adverse impact


def test_horizon_greater_than_one_leaves_leading_periods_without_drift():
    periods = {
        "a": period_df(5, 10, 4, 10),  # female ratio 0.8
        "b": period_df(5, 10, 3, 10),  # female ratio 0.6
        "c": period_df(5, 10, 2, 10),  # female ratio 0.4
    }
    sex = audit_lifecycle(periods, outcome="selected", horizon=2).series["sex"]
    assert sex[0].drift is None
    assert sex[1].drift is None
    # c compared to a: female 0.4 vs 0.8 -> 0.4 / sqrt(2)
    assert sex[2].drift == pytest.approx(0.4 / math.sqrt(2))


def test_adverse_impact_agrees_with_four_fifths_on_same_data():
    df = period_df(5, 10, 2, 10)
    ff = four_fifths(selection_rates(df, by=["sex"], outcome="selected")).set_index("sex")
    point = audit_lifecycle({"p": df}, outcome="selected").series["sex"][0]
    assert point.adverse_impact == bool(ff.loc["female", "adverse_impact_eeoc"])


def test_composition_change_is_flagged_and_drift_stays_finite():
    p1 = period_df(5, 10, 4, 10)
    # a third sex category (benchmarked, but does not beat male's 0.50 rate) appears
    p2 = pd.DataFrame(
        {
            "sex": ["male"] * 10 + ["female"] * 10 + ["other"] * 12,
            "race_ethnicity": "r",
            "selected": (
                [True] * 5 + [False] * 5 + [True] * 2 + [False] * 8 + [True] * 4 + [False] * 8
            ),
        }
    )
    sex = audit_lifecycle({"p1": p1, "p2": p2}, outcome="selected").series["sex"]
    assert sex[1].composition_changed is True
    assert sex[1].drift is not None and not math.isnan(sex[1].drift)


def test_drift_alert_is_the_only_way_drift_triggers_review():
    # female ratio 1.0 -> 0.8: no adverse impact, no crossing, but drift = 0.2/sqrt(2)
    periods = {"a": period_df(5, 10, 5, 10), "b": period_df(5, 10, 4, 10)}
    with_alert = audit_lifecycle(periods, outcome="selected", drift_alert=0.1)
    sex = with_alert.series["sex"]
    assert sex[1].adverse_impact is False
    assert sex[1].crossed_four_fifths is False
    triggered = with_alert.triggers()
    assert list(triggered.loc[triggered["grouping"] == "sex", "period"]) == ["b"]

    without_alert = audit_lifecycle(periods, outcome="selected", drift_alert=None)
    assert without_alert.triggers().empty


def test_worsening_synthetic_lifecycle_shrinks_the_margin():
    report = audit_lifecycle(synthetic_lifecycle(5, seed=0), outcome="selected")
    margins = [p.boundary_margin for p in report.series["sex"]]
    assert margins[-1] < margins[0]  # the injected worsening bias is recovered
    last = report.series["sex"][-1]
    assert last.worst_group == "female"
    assert last.adverse_impact is True


def test_sequence_input_preserves_period_order():
    report = audit_lifecycle(
        [("y1", period_df(5, 10, 4, 10)), ("y2", period_df(5, 10, 2, 10))], outcome="selected"
    )
    assert [p.period for p in report.series["sex"]] == ["y1", "y2"]


def test_scoring_lifecycle_reports_scoring_kind():
    report = audit_lifecycle(synthetic_lifecycle(3, seed=2), score="score")
    assert report.kind == "scoring"


def test_requires_exactly_one_of_outcome_or_score():
    periods = {"p": period_df(5, 10, 2, 10)}
    with pytest.raises(ValueError):
        audit_lifecycle(periods)
    with pytest.raises(ValueError):
        audit_lifecycle(periods, outcome="selected", score="score")


def test_empty_periods_and_bad_horizon_raise():
    with pytest.raises(ValueError):
        audit_lifecycle({}, outcome="selected")
    with pytest.raises(ValueError):
        audit_lifecycle({"p": period_df(5, 10, 2, 10)}, outcome="selected", horizon=0)


def test_markdown_render_mentions_legal_sources_and_disclaimer():
    report = audit_lifecycle(
        synthetic_lifecycle(4, seed=1),
        outcome="selected",
        metadata=AuditMetadata(tool_name="screener-x"),
    )
    text = report.to_markdown()
    assert "lifecycle" in text.lower()
    assert "LL144" in text
    assert "1607.4(D)" in text
    assert "independent bias audit" in text
    assert "screener-x" in text


def test_json_round_trip_and_valid_null_for_missing_drift():
    report = audit_lifecycle(synthetic_lifecycle(3, seed=3), outcome="selected")
    payload = json.loads(report.to_json())  # strict json.loads rejects NaN tokens
    assert payload["kind"] == "selection"
    assert set(payload["series"]) == {"sex", "race_ethnicity", "intersectional"}
    assert payload["series"]["sex"][0]["drift"] is None  # first period -> null, not NaN


def test_csv_export_writes_one_file_per_grouping(tmp_path):
    report = audit_lifecycle(synthetic_lifecycle(3, seed=4), outcome="selected")
    paths = report.save_csvs(tmp_path)
    assert len(paths) == 3
    for path in paths:
        assert Path(path).exists()


def test_html_render_mentions_legal_sources_and_disclaimer():
    report = audit_lifecycle(
        synthetic_lifecycle(3, seed=5),
        outcome="selected",
        drift_alert=0.05,
        metadata=AuditMetadata(tool_name="screener-y"),
    )
    html = report.to_html()
    assert "<h1>" in html and "screener-y" in html
    assert "1607.4(D)" in html and "independent bias audit" in html
    assert "drift alert threshold" in html


def test_csv_export_creates_missing_directories(tmp_path):
    target = tmp_path / "nested" / "dir"
    paths = audit_lifecycle(synthetic_lifecycle(2, seed=6), outcome="selected").save_csvs(target)
    assert len(paths) == 3 and all(Path(p).exists() for p in paths)

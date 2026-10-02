"""The SVG charts: well-formed, deterministic, and never colour-only."""

import math
import xml.etree.ElementTree as ET

import pandas as pd
import pytest

from aedt_audit import (
    audit_lifecycle,
    four_fifths,
    impact_ratio_chart,
    lifecycle_chart,
    selection_rates,
    synthetic_lifecycle,
)

SVG = "{http://www.w3.org/2000/svg}"


def table():
    df = pd.DataFrame(
        {
            "sex": ["male"] * 100 + ["female"] * 100 + ["other"] * 1 + [None] * 10,
            "selected": [True] * 50
            + [False] * 50
            + [True] * 30
            + [False] * 70
            + [True]
            + [True] * 10,
        }
    )
    return four_fifths(selection_rates(df, by=["sex"], outcome="selected"))


def test_impact_chart_is_well_formed_svg_with_one_bar_per_category():
    svg = impact_ratio_chart(table(), title="Impact ratios by sex", subtitle="demo")
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG}svg"
    bars = [p for p in root.iter(f"{SVG}path") if "fill-" in p.get("class", "")]
    assert len(bars) == 4  # male, female, other (excluded), unknown
    classes = {p.get("class") for p in bars}
    assert classes == {"fill-series", "fill-alert", "fill-neutral"}
    text = "".join(root.itertext())
    assert "four-fifths" in text and "benchmark" in text
    assert "◆ below four-fifths" in text  # flagged bar is labelled, not just coloured
    assert "excluded, under 2%" in text and "unknown" in text  # grey bars say why
    assert "Impact ratios by sex" in text and "demo" in text
    titles = [t.text for t in root.iter(f"{SVG}title")]
    assert any("female" in t and "below four-fifths" in t for t in titles)  # native tooltip


def test_impact_chart_orders_benchmarked_rows_worst_first_then_grey():
    svg = impact_ratio_chart(table())
    root = ET.fromstring(svg)
    bars = [p.get("class") for p in root.iter(f"{SVG}path") if "fill-" in p.get("class", "")]
    assert bars == ["fill-alert", "fill-series", "fill-neutral", "fill-neutral"]


def test_impact_chart_handles_missing_ratio_and_overflow():
    t = pd.DataFrame(
        {
            "g": ["a", "b", "c"],
            "n": [10, 10, 10],
            "selected": [0, 0, 9],
            "rate": [0.0, 0.0, 0.9],
            "share": [1 / 3, 1 / 3, 1 / 3],
            "excluded": [False, False, True],
        }
    )
    out = four_fifths(t)  # benchmark rate 0 -> ratios NaN
    svg = impact_ratio_chart(out, by=["g"])
    assert "n/a" in svg
    ET.fromstring(svg)
    t2 = pd.DataFrame(
        {
            "g": ["a", "u"],
            "n": [100, 10],
            "selected": [20, 10],
            "rate": [0.2, 1.0],
            "share": [100 / 110, 10 / 110],
            "excluded": [False, True],
        }
    )
    svg2 = impact_ratio_chart(four_fifths(t2, by=["g"]), by=["g"])
    assert "▸ 5.000" in svg2  # clipped at 1.5 with an overflow marker
    ET.fromstring(svg2)


def test_impact_chart_is_deterministic():
    assert impact_ratio_chart(table()) == impact_ratio_chart(table())


def test_lifecycle_chart_marks_adverse_periods_and_alert_threshold():
    report = audit_lifecycle(synthetic_lifecycle(5, seed=0), outcome="selected", drift_alert=0.05)
    df = report.to_dataframe()
    sub = df[df["grouping"] == "sex"].drop(columns="grouping").reset_index(drop=True)
    svg = lifecycle_chart(sub, title="sex", drift_alert=0.05, horizon=1)
    root = ET.fromstring(svg)
    dots = list(root.iter(f"{SVG}circle"))
    assert len(dots) == 5
    adverse = int(sub["adverse_impact"].sum())
    assert sum("fill-alert" in d.get("class") for d in dots) == adverse
    text = "".join(root.itertext())
    assert text.count("◆") >= adverse + 1  # one marker per adverse period plus the key
    assert "alert threshold 0.05" in text
    assert "four-fifths line" in text
    cols = [p for p in root.iter(f"{SVG}path") if p.get("class") == "fill-series"]
    assert len(cols) == int(sub["drift"].notna().sum())  # first period has no drift column
    assert "—" in text  # the blank drift is shown as a dash, not omitted silently


def test_lifecycle_chart_single_period_and_nan_margin():
    sub = pd.DataFrame(
        {
            "period": ["2025"],
            "n": [0],
            "benchmark_rate": [math.nan],
            "worst_group": [""],
            "worst_ratio": [math.nan],
            "boundary_margin": [math.nan],
            "adverse_impact": [False],
            "drift": [math.nan],
            "crossed_four_fifths": [False],
            "composition_changed": [False],
            "review": [False],
        }
    )
    svg = lifecycle_chart(sub, title="empty")
    ET.fromstring(svg)
    assert "<circle" not in svg


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_chart_style_defines_both_colour_schemes(mode):
    svg = impact_ratio_chart(table())
    assert "prefers-color-scheme:dark" in svg
    assert "--alert:#d03b3b" in svg  # status colour, paired with the ◆ marker

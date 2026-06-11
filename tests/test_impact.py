"""Hand-computed fixtures for impact ratios and the four-fifths rule."""

import pandas as pd
import pytest

from aedt_audit import four_fifths, impact_ratios, selection_rates


def rates_table():
    df = pd.DataFrame(
        {
            "sex": ["male"] * 10 + ["female"] * 8,
            "selected": [True] * 5 + [False] * 5 + [True] * 2 + [False] * 6,
        }
    )
    return selection_rates(df, by=["sex"], outcome="selected")


def test_impact_ratio_hand_computed():
    out = impact_ratios(rates_table()).set_index("sex")
    # benchmark = male rate 0.50 -> female ratio = 0.25 / 0.50 = 0.50
    assert out.loc["male", "impact_ratio"] == pytest.approx(1.0)
    assert out.loc["female", "impact_ratio"] == pytest.approx(0.5)


def test_four_fifths_flags_only_below_threshold():
    out = four_fifths(rates_table()).set_index("sex")
    assert bool(out.loc["female", "adverse_impact_eeoc"]) is True  # 0.5 < 0.8
    assert bool(out.loc["male", "adverse_impact_eeoc"]) is False


def test_ratio_exactly_at_threshold_is_not_flagged():
    # 0.8 is the EEOC boundary: "less than four-fifths" is flagged; 0.8 itself is not.
    table = pd.DataFrame({"g": ["a", "b"], "rate": [1.0, 0.8], "excluded": [False, False]})
    out = four_fifths(table).set_index("g")
    assert bool(out.loc["b", "adverse_impact_eeoc"]) is False


def test_excluded_category_cannot_set_benchmark():
    # A tiny category with a perfect rate must not become the denominator.
    table = pd.DataFrame(
        {
            "g": ["big_a", "big_b", "tiny"],
            "rate": [0.50, 0.40, 1.00],
            "excluded": [False, False, True],
        }
    )
    out = impact_ratios(table).set_index("g")
    assert out.attrs["benchmark_rate"] == pytest.approx(0.50)
    assert out.loc["big_b", "impact_ratio"] == pytest.approx(0.8)
    # the excluded category still gets a ratio, for transparency
    assert out.loc["tiny", "impact_ratio"] == pytest.approx(2.0)


def test_unknown_category_cannot_set_benchmark():
    # "unknown" demographics are disclosed but are not a comparison group
    # (DCWP audit practice) — even when they have the highest rate.
    df = pd.DataFrame(
        {
            "sex": ["male"] * 10 + ["female"] * 10 + [None] * 4,
            "selected": [True] * 5 + [False] * 5 + [True] * 4 + [False] * 6 + [True] * 4,
        }
    )
    out = impact_ratios(selection_rates(df, by=["sex"], outcome="selected")).set_index("sex")
    # unknown rate is 1.0, but the benchmark must be male's 0.50
    assert out.attrs["benchmark_rate"] == pytest.approx(0.50)
    assert out.loc["female", "impact_ratio"] == pytest.approx(0.8)
    # the unknown row still gets a ratio, for transparency
    assert out.loc["unknown", "impact_ratio"] == pytest.approx(2.0)


def test_unknown_in_any_intersectional_column_excluded_from_benchmark():
    df = pd.DataFrame(
        {
            "sex": ["m", "m", None, None],
            "race": ["x", "x", "x", "x"],
            "selected": [True, False, True, True],
        }
    )
    out = impact_ratios(selection_rates(df, by=["sex", "race"], outcome="selected"))
    assert out.attrs["benchmark_rate"] == pytest.approx(0.5)  # (m, x), not (unknown, x)


def test_missing_rate_column_raises():
    with pytest.raises(KeyError):
        impact_ratios(pd.DataFrame({"g": ["a"]}))

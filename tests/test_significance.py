"""Hand-computed fixtures for the standard-deviation analysis.

Legal basis: 29 CFR § 1607.4(D) ("significant in both statistical and practical
terms"); Castaneda v. Partida, 430 U.S. 482, 496–97 n.17 (1977); Hazelwood School
District v. United States, 433 U.S. 299, 308–09 n.14 (1977); Uniform Guidelines
Q&A 18, 20–22, 24 (44 Fed. Reg. 11996, Mar. 2, 1979).
"""

import json
import math

import numpy as np
import pandas as pd
import pytest

from aedt_audit import (
    SIGNIFICANCE_COLUMNS,
    four_fifths,
    ll144_summary,
    selection_rates,
    selections_to_four_fifths,
    significance,
    standard_deviation_test,
    synthetic_applicants,
)


def pool(male_sel, male_tot, female_sel, female_tot):
    return pd.DataFrame(
        {
            "sex": ["male"] * male_tot + ["female"] * female_tot,
            "selected": [True] * male_sel
            + [False] * (male_tot - male_sel)
            + [True] * female_sel
            + [False] * (female_tot - female_sel),
        }
    )


def analysed(df, **kwargs):
    return significance(four_fifths(selection_rates(df, by=["sex"], outcome="selected")), **kwargs)


def test_hand_computed_fixture_male_5_of_10_vs_female_2_of_8():
    # p_g = 2/8 = 0.25, p_b = 5/10 = 0.50, pooled p = 7/18 = 0.388889
    # 1/n_g + 1/n_b = 1/8 + 1/10 = 0.225
    # Var = 0.388889 * 0.611111 * 0.225 = 0.0534722 ; SE = 0.231241
    # z = (0.25 - 0.50) / 0.231241 = -1.08112
    # two-sided p = erfc(1.08112 / sqrt 2) = erfc(0.76447) = 0.2796
    out = analysed(pool(5, 10, 2, 8))
    row = out.set_index("sex")
    assert row.loc["female", "z_score"] == pytest.approx(-1.0811, abs=1e-4)
    assert row.loc["female", "p_value"] == pytest.approx(0.2796, abs=1e-3)
    # Impact ratio 0.5 trips four-fifths, yet the difference is not significant
    # at 2 SD on 18 people: the Q&A 21/24 situation the flag exists to surface.
    assert bool(row.loc["female", "adverse_impact_eeoc"]) is True
    assert bool(row.loc["female", "significant_2sd"]) is False
    assert bool(row.loc["female", "small_sample"]) is True  # 8 + 10 = 18 < 30
    # Four-fifths of 0.50 is 0.40; 0.40 * 8 = 3.2 -> 4 selections needed; 4 - 2 = 2.
    # (3/8 = 0.375 < 0.40, 4/8 = 0.50 >= 0.40)
    assert row.loc["female", "selections_to_four_fifths"] == 2
    # The benchmark compared with itself.
    assert row.loc["male", "z_score"] == 0.0
    assert row.loc["male", "p_value"] == 1.0
    assert row.loc["male", "selections_to_four_fifths"] == 0
    assert out.attrs["significance_sd"] == 2.0


def test_significant_but_passing_four_fifths():
    # male 500/1000 = 0.50, female 400/1000 = 0.40 -> ratio exactly 0.8: not flagged.
    # pooled p = 0.45; Var = 0.45 * 0.55 * (0.001 + 0.001) = 0.000495; SE = 0.0222486
    # z = -0.10 / 0.0222486 = -4.4947 -> far beyond 2 SD (29 CFR 1607.4(D): a smaller
    # difference "may nevertheless constitute adverse impact" when significant).
    out = analysed(pool(500, 1000, 400, 1000)).set_index("sex")
    assert out.loc["female", "impact_ratio"] == pytest.approx(0.8)
    assert bool(out.loc["female", "adverse_impact_eeoc"]) is False
    assert out.loc["female", "z_score"] == pytest.approx(-4.4947, abs=1e-3)
    assert bool(out.loc["female", "significant_2sd"]) is True
    assert bool(out.loc["female", "small_sample"]) is False
    assert out.loc["female", "selections_to_four_fifths"] == 0  # already on the line


def test_selections_to_four_fifths_uses_integer_arithmetic():
    # x_b=3, n_b=4 (0.75); n_g=5. Four-fifths of 0.75 is 0.60; 0.60 * 5 = 3 exactly.
    # Floating point gives 0.8 * 0.75 * 5 = 3.0000000000000004 -> ceil 4 (wrong).
    assert selections_to_four_fifths(3, 5, 3, 4) == 0  # 3/5 = 0.60 is on the line
    assert selections_to_four_fifths(2, 5, 3, 4) == 1  # 2 -> 3
    assert selections_to_four_fifths(0, 5, 3, 4) == 3
    assert selections_to_four_fifths(2, 8, 5, 10) == 2  # the first fixture
    assert selections_to_four_fifths(5, 10, 5, 10) == 0
    assert selections_to_four_fifths(0, 0, 5, 10) == 0  # degenerate sizes
    # Exhaustive agreement with exact rational arithmetic on small tables.
    from fractions import Fraction

    for n_b in range(1, 13):
        for x_b in range(n_b + 1):
            for n_g in range(1, 13):
                for x_g in range(n_g + 1):
                    line = Fraction(4, 5) * Fraction(x_b, n_b)
                    exact = 0
                    if Fraction(x_g, n_g) < line:
                        exact = math.ceil(line * n_g) - x_g
                    assert selections_to_four_fifths(x_g, n_g, x_b, n_b) == exact


def test_equal_rates_and_degenerate_pools_give_zero_not_nan():
    # Identical rates: z = 0, p = 1 (not 0/0 when nobody or everybody is selected).
    assert standard_deviation_test(5, 10, 5, 10) == (0.0, 1.0)
    assert standard_deviation_test(0, 10, 0, 10) == (0.0, 1.0)
    assert standard_deviation_test(10, 10, 10, 10) == (0.0, 1.0)
    z, p = standard_deviation_test(0, 0, 5, 10)
    assert math.isnan(z) and math.isnan(p)
    out = analysed(pool(0, 10, 0, 10))
    assert (out["z_score"] == 0.0).all() and (out["p_value"] == 1.0).all()
    assert not out["significant_2sd"].any()


def test_flag_is_directional_so_an_unknown_row_above_the_benchmark_is_not_flagged():
    df = pd.DataFrame(
        {
            "sex": ["male"] * 100 + ["female"] * 100 + [None] * 40,
            "selected": [True] * 50 + [False] * 50 + [True] * 50 + [False] * 50 + [True] * 40,
        }
    )
    out = analysed(df).set_index("sex")
    # unknown is selected 100% vs the 50% benchmark: a large *positive* z.
    assert out.loc["unknown", "z_score"] > 2
    assert bool(out.loc["unknown", "significant_2sd"]) is False
    assert out.loc["unknown", "selections_to_four_fifths"] == 0


def test_benchmark_tie_at_the_top_rate_picks_the_larger_category():
    # a: 2/4 = 0.5 ; b: 50/100 = 0.5 ; c: 1/10 = 0.1
    # vs b (n=100): pooled 51/110 = 0.4636, Var = 0.4636*0.5364*(0.1+0.01) = 0.027357,
    #   SE = 0.16540, z = -0.4/0.16540 = -2.418 -> significant
    # vs a (n=4):   pooled 3/14 = 0.2143,  Var = 0.2143*0.7857*(0.1+0.25) = 0.058929,
    #   SE = 0.24275, z = -0.4/0.24275 = -1.648 -> not significant
    table = pd.DataFrame(
        {
            "g": ["a", "b", "c"],
            "n": [4, 100, 10],
            "selected": [2, 50, 1],
            "rate": [0.5, 0.5, 0.1],
            "share": [4 / 114, 100 / 114, 10 / 114],
            "excluded": [False, False, False],
        }
    )
    out = significance(table).set_index("g")
    assert out.loc["c", "z_score"] == pytest.approx(-2.418, abs=1e-3)
    assert bool(out.loc["c", "significant_2sd"]) is True
    assert bool(out.loc["c", "small_sample"]) is False  # 10 + 100 >= 30


def test_excluded_tiny_category_cannot_be_the_benchmark_for_the_test():
    table = pd.DataFrame(
        {
            "g": ["big", "tiny"],
            "n": [100, 1],
            "selected": [50, 1],
            "rate": [0.5, 1.0],
            "share": [100 / 101, 1 / 101],
            "excluded": [False, True],
        }
    )
    out = significance(table).set_index("g")
    assert out.loc["big", "z_score"] == 0.0  # big is the benchmark, not tiny
    assert out.loc["tiny", "z_score"] > 0


def test_no_benchmark_row_yields_nan_statistics_and_false_flags():
    df = pd.DataFrame({"sex": [None, None, None], "selected": [True, False, True]})
    out = analysed(df)
    assert out["z_score"].isna().all() and out["p_value"].isna().all()
    assert not out["significant_2sd"].any() and not out["small_sample"].any()
    assert out["selections_to_four_fifths"].isna().all()


def test_rate_only_table_raises_a_clear_error():
    table = pd.DataFrame(
        {"g": ["a", "b"], "n": [10, 10], "rate": [1.0, 0.5], "excluded": [False, False]}
    )
    with pytest.raises(KeyError, match="selected"):
        significance(four_fifths(table))
    with pytest.raises(KeyError, match="'n'"):
        significance(pd.DataFrame({"g": ["a"], "rate": [1.0], "selected": [1]}))


def test_custom_threshold():
    out = analysed(pool(5, 10, 2, 8), threshold_sd=1.0).set_index("sex")
    assert bool(out.loc["female", "significant_2sd"]) is True  # |z| = 1.08 >= 1.0
    assert out.attrs["significance_sd"] == 1.0


def test_summary_wiring_and_renderers():
    data = synthetic_applicants(3000, seed=11, score_bias={("sex", "female"): -8.0})
    summary = ll144_summary(data, outcome="selected", significance=True)
    for table in summary.tables.values():
        for col in SIGNIFICANCE_COLUMNS:
            assert col in table.columns
    assert summary.has_significance
    by_sex = summary.tables["sex"].set_index("sex")
    assert bool(by_sex.loc["female", "significant_2sd"]) is True
    assert by_sex.loc["female", "selections_to_four_fifths"] > 0
    md = summary.to_markdown()
    assert "Castaneda" in md and "do not override" in md and "1607.4(D)" in md
    html = summary.to_html()
    assert "Castaneda" in html
    json.loads(summary.to_json())  # strict: no NaN tokens
    # scoring variant uses the above_median count
    scoring = ll144_summary(data, score="score", significance=True)
    assert "z_score" in scoring.tables["sex"].columns
    # off by default
    assert not ll144_summary(data, outcome="selected").has_significance
    assert "Castaneda" not in ll144_summary(data, outcome="selected").to_markdown()


def test_significance_columns_are_metric_columns_for_benchmarking():
    # Re-running the benchmark filter on an augmented table must not treat the
    # new columns as demographic categories.
    from aedt_audit import benchmark_mask
    from aedt_audit.impact import category_columns

    out = analysed(pool(5, 10, 2, 8))
    assert category_columns(out) == ["sex"]
    assert benchmark_mask(out).all()
    assert np.array_equal(out["sex"].to_numpy(), np.array(["female", "male"]))

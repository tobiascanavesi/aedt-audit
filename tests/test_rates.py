"""Hand-computed fixtures for the LL144 rate definitions."""

import numpy as np
import pandas as pd
import pytest

from aedt_audit import scoring_rates, selection_rates


def make_pool():
    # 10 men, 5 selected (rate 0.50); 8 women, 2 selected (rate 0.25)
    return pd.DataFrame(
        {
            "sex": ["male"] * 10 + ["female"] * 8,
            "selected": [True] * 5 + [False] * 5 + [True] * 2 + [False] * 6,
        }
    )


def test_selection_rates_hand_computed():
    rates = selection_rates(make_pool(), by=["sex"], outcome="selected")
    by_sex = rates.set_index("sex")
    assert by_sex.loc["male", "n"] == 10
    assert by_sex.loc["male", "selected"] == 5
    assert by_sex.loc["male", "rate"] == pytest.approx(0.50)
    assert by_sex.loc["female", "rate"] == pytest.approx(0.25)
    assert by_sex["n"].sum() == 18


def test_scoring_rate_uses_strictly_above_full_sample_median():
    # Scores 1..10: median 5.5; "above median" = {6,7,8,9,10}.
    # Group A holds 6 and 7 (2 of 5 above); group B holds 8, 9, 10 (3 of 5).
    df = pd.DataFrame(
        {
            "sex": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"],
            "score": [1, 2, 3, 6, 7, 4, 5, 8, 9, 10],
        }
    )
    rates = scoring_rates(df, by=["sex"], score="score")
    assert rates.attrs["sample_median"] == pytest.approx(5.5)
    by_sex = rates.set_index("sex")
    assert by_sex.loc["a", "above_median"] == 2
    assert by_sex.loc["a", "rate"] == pytest.approx(0.4)
    assert by_sex.loc["b", "rate"] == pytest.approx(0.6)


def test_scores_tied_at_median_do_not_count_as_above():
    # Even count of identical values: median equals the value; nobody is above.
    df = pd.DataFrame({"sex": ["a", "a", "b", "b"], "score": [5, 5, 5, 5]})
    rates = scoring_rates(df, by=["sex"], score="score")
    assert (rates["above_median"] == 0).all()


def test_small_category_flagged_excluded_not_dropped():
    df = pd.DataFrame(
        {
            "sex": ["male"] * 99 + ["nonbinary"],
            "selected": [True] * 50 + [False] * 49 + [True],
        }
    )
    rates = selection_rates(df, by=["sex"], outcome="selected")
    by_sex = rates.set_index("sex")
    assert bool(by_sex.loc["nonbinary", "excluded"]) is True  # 1% < 2%
    assert bool(by_sex.loc["male", "excluded"]) is False
    assert len(rates) == 2  # nothing dropped


def test_missing_demographics_reported_as_unknown():
    df = pd.DataFrame({"sex": ["male", None, np.nan], "selected": [True, True, False]})
    rates = selection_rates(df, by=["sex"], outcome="selected")
    by_sex = rates.set_index("sex")
    assert by_sex.loc["unknown", "n"] == 2
    assert by_sex.loc["unknown", "rate"] == pytest.approx(0.5)


def test_intersectional_grouping():
    df = pd.DataFrame(
        {
            "sex": ["f", "f", "m", "m"],
            "race": ["x", "y", "x", "y"],
            "selected": [True, False, True, True],
        }
    )
    rates = selection_rates(df, by=["sex", "race"], outcome="selected")
    assert len(rates) == 4
    cell = rates.set_index(["sex", "race"]).loc[("f", "x")]
    assert cell["rate"] == pytest.approx(1.0)


def test_missing_columns_raise():
    df = make_pool()
    with pytest.raises(KeyError):
        selection_rates(df, by=["nope"], outcome="selected")
    with pytest.raises(KeyError):
        scoring_rates(df, by=["sex"], score="nope")

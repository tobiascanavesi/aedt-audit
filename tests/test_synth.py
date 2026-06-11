import pandas as pd

from aedt_audit import synthetic_applicants


def test_deterministic_for_seed():
    a = synthetic_applicants(500, seed=42)
    b = synthetic_applicants(500, seed=42)
    pd.testing.assert_frame_equal(a, b)


def test_columns_and_ranges():
    df = synthetic_applicants(1000, seed=1)
    assert list(df.columns) == ["sex", "race_ethnicity", "score", "selected"]
    assert df["score"].between(0, 100).all()
    assert df["selected"].dtype == bool
    # top-30% default selection
    assert 0.25 < df["selected"].mean() < 0.35


def test_bias_knob_shifts_scores():
    fair = synthetic_applicants(4000, seed=3)
    biased = synthetic_applicants(4000, seed=3, score_bias={("sex", "female"): -10.0})
    fair_gap = (
        fair.loc[fair.sex == "male", "score"].mean()
        - fair.loc[fair.sex == "female", "score"].mean()
    )
    biased_gap = (
        biased.loc[biased.sex == "male", "score"].mean()
        - biased.loc[biased.sex == "female", "score"].mean()
    )
    assert abs(fair_gap) < 2.0
    assert biased_gap > 8.0

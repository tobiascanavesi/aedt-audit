import json

import pytest

from aedt_audit import AuditMetadata, ll144_summary, synthetic_applicants


@pytest.fixture()
def pool():
    return synthetic_applicants(2000, seed=7, score_bias={("sex", "female"): -8.0})


def test_summary_has_three_required_groupings(pool):
    summary = ll144_summary(pool, outcome="selected")
    assert set(summary.tables) == {"sex", "race_ethnicity", "intersectional"}
    assert summary.kind == "selection"


def test_scoring_summary_carries_sample_median(pool):
    summary = ll144_summary(pool, score="score")
    assert summary.kind == "scoring"
    assert summary.sample_median is not None


def test_requires_exactly_one_of_outcome_or_score(pool):
    with pytest.raises(ValueError):
        ll144_summary(pool)
    with pytest.raises(ValueError):
        ll144_summary(pool, outcome="selected", score="score")


def test_biased_scorer_is_detected(pool):
    summary = ll144_summary(pool, outcome="selected")
    by_sex = summary.tables["sex"].set_index("sex")
    assert bool(by_sex.loc["female", "adverse_impact_eeoc"]) is True
    assert by_sex.loc["female", "impact_ratio"] < by_sex.loc["male", "impact_ratio"]


def test_markdown_render_mentions_both_legal_sources(pool):
    summary = ll144_summary(
        pool,
        outcome="selected",
        metadata=AuditMetadata(tool_name="example-screener", prepared_by="QA"),
    )
    text = summary.to_markdown()
    assert "LL144" in text
    assert "1607.4(D)" in text  # EEOC four-fifths citation
    assert "example-screener" in text
    assert "independent bias audit" in text  # the not-an-audit disclaimer


def test_json_round_trip(pool):
    payload = json.loads(ll144_summary(pool, outcome="selected").to_json())
    assert payload["kind"] == "selection"
    sexes = {row["sex"] for row in payload["tables"]["sex"]}
    assert {"female", "male"} <= sexes


def test_csv_export(tmp_path, pool):
    paths = ll144_summary(pool, outcome="selected").save_csvs(tmp_path)
    assert len(paths) == 3
    for path in paths:
        assert tmp_path.joinpath(path.split("/")[-1]).exists()

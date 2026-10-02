import json
from html.parser import HTMLParser

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


def test_exclusion_footnote_names_only_categories(pool):
    # Regression: the footnote used to print each excluded category's `n` as
    # though it were another category ("Native Hawaiian or Pacific Islander × 95").
    summary = ll144_summary(pool, outcome="selected")
    table = summary.tables["intersectional"]
    small = table.loc[table["excluded"]]
    assert len(small) > 0, "intersectional fixture must have a <2% cell"
    section = summary.to_markdown().split("## intersectional")[1]
    footnote = [line for line in section.splitlines() if "below 2%" in line][0]
    for _, row in small.iterrows():
        cell = f"{row['sex']} × {row['race_ethnicity']}"
        assert cell in footnote
        assert f"{cell} × {row['n']}" not in footnote


def test_save_csvs_creates_missing_directories(tmp_path, pool):
    target = tmp_path / "audit_out" / "2025"
    paths = ll144_summary(pool, outcome="selected").save_csvs(target)
    assert len(paths) == 3 and all(target.joinpath(p.split("/")[-1]).exists() for p in paths)


def test_html_carries_metadata_footnote_and_disclaimer(pool):
    html = ll144_summary(
        pool, outcome="selected", metadata=AuditMetadata(tool_name="example-screener")
    ).to_html()
    assert "example-screener" in html
    assert "1607.4(D)" in html
    assert "below 2% of the sample" in html
    assert "independent bias audit" in html


def test_json_is_strict_even_when_nobody_is_selected():
    import pandas as pd

    df = pd.DataFrame({"sex": ["m", "f"], "race_ethnicity": "r", "selected": [False, False]})
    payload = json.loads(ll144_summary(df, outcome="selected").to_json())  # rejects NaN tokens
    assert payload["tables"]["sex"][0]["impact_ratio"] is None


def test_ratio_near_the_line_is_not_rounded_onto_it():
    import pandas as pd

    # female 199/250 = 0.796 of the male rate: flagged, and must not display as 0.80.
    df = pd.DataFrame(
        {
            "sex": ["m"] * 250 + ["f"] * 250,
            "race_ethnicity": "r",
            "selected": [True] * 250 + [True] * 199 + [False] * 51,
        }
    )
    summary = ll144_summary(df, outcome="selected")
    assert bool(summary.tables["sex"].set_index("sex").loc["f", "adverse_impact_eeoc"]) is True
    sex_table = summary.to_markdown().split("## sex")[1].split("##")[0]
    assert "0.796" in sex_table
    assert "| 0.8 " not in sex_table


def test_to_dataframe_is_tidy_long_form(pool):
    df = ll144_summary(pool, outcome="selected").to_dataframe()
    assert list(df.columns[:3]) == ["grouping", "sex", "race_ethnicity"]
    assert set(df["grouping"]) == {"sex", "race_ethnicity", "intersectional"}
    assert df.loc[df["grouping"] == "sex", "race_ethnicity"].isna().all()


class _Balanced(HTMLParser):
    """Checks that non-void tags nest properly and that every id is unique."""

    VOID = {"meta", "br", "hr", "img", "input", "link", "path", "line", "rect", "circle"}

    def __init__(self):
        super().__init__()
        self.stack, self.ids, self.problems = [], set(), []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "id":
                if value in self.ids:
                    self.problems.append(f"duplicate id {value!r}")
                self.ids.add(value)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
        else:
            self.stack.pop()


def assert_well_formed(html):
    parser = _Balanced()
    parser.feed(html)
    parser.close()
    assert not parser.problems, parser.problems[:5]
    assert not parser.stack, parser.stack


def test_html_is_a_complete_self_contained_document_with_charts(pool):
    html = ll144_summary(
        pool, outcome="selected", significance=True, metadata=AuditMetadata(tool_name="t-1")
    ).to_html()
    assert html.startswith("<!doctype html>")
    body = html.split("<body>")[1].replace("http://www.w3.org/2000/svg", "")
    assert "<script" not in html and "http" not in body
    assert html.count("<svg") == 3
    assert "Individuals assessed" in html and "How to read this" in html
    assert "Castaneda" in html  # the significance note travels with the columns
    assert "<title>t-1 — Bias-audit summary (selection rates)</title>" in html
    assert_well_formed(html)
    # the legal notes render identifiers as code, not as literal backticks
    assert "<code>adverse_impact_eeoc</code>" in html and "`adverse_impact_eeoc`" not in html

    fragment = ll144_summary(pool, outcome="selected").to_html(fragment=True)
    assert "<html" not in fragment and fragment.lstrip().startswith("<style>")
    assert fragment.count("<svg") == 3
    assert "body{" not in fragment  # embedding must not restyle the host page
    assert "body{margin:0}" in html


def test_well_formedness_check_catches_bad_markup():
    parser = _Balanced()
    parser.feed('<div id="a"><span id="a"></div>')
    assert len(parser.problems) == 2


def test_html_table_marks_flagged_and_dimmed_rows():
    import pandas as pd

    df = pd.DataFrame(
        {
            "sex": ["m"] * 100 + ["f"] * 100 + [None] * 10,
            "race_ethnicity": "r",
            "selected": [True] * 50 + [False] * 50 + [True] * 30 + [False] * 70 + [True] * 10,
        }
    )
    html = ll144_summary(df, outcome="selected").to_html()
    sex_section = html.split("<h2>sex</h2>")[1].split("</section>")[0]
    assert '<tr class="flag"><td class="cat">f</td>' in sex_section
    assert '<tr class="dim"><td class="cat">unknown</td>' in sex_section
    assert "◆ yes" in sex_section


def test_tiny_p_values_are_floored_in_markdown_and_kept_exact_in_json(pool):
    summary = ll144_summary(pool, outcome="selected", significance=True)
    sex_table = summary.to_markdown().split("## sex")[1].split("##")[0]
    assert "<0.001" in sex_table  # not a literal 0
    payload = json.loads(summary.to_json())
    female = next(r for r in payload["tables"]["sex"] if r["sex"] == "female")
    assert 0 < female["p_value"] < 1e-6  # full precision, not rounded to 0.0
    assert female["rate"] == round(female["rate"], 4)

"""The command-line interface, driven through ``main(argv)``."""

import json

import pandas as pd
import pytest

from aedt_audit import synthetic_applicants, synthetic_lifecycle
from aedt_audit.cli import EXIT_ERROR, EXIT_FINDING, EXIT_OK, main


@pytest.fixture()
def biased_csv(tmp_path):
    path = tmp_path / "applicants.csv"
    synthetic_applicants(3000, seed=0, score_bias={("sex", "female"): -8.0}).to_csv(
        path, index=False
    )
    return path


@pytest.fixture()
def fair_csv(tmp_path):
    # Exactly balanced: every sex x race cell has 200 people and 100 selected, so
    # every impact ratio is 1.0 by construction (a random pool can trip 0.8 by noise).
    rows = []
    for sex in ("female", "male"):
        for race in ("a", "b", "c"):
            rows.append(
                pd.DataFrame(
                    {"sex": sex, "race_ethnicity": race, "selected": [True] * 100 + [False] * 100}
                )
            )
    path = tmp_path / "fair.csv"
    pd.concat(rows).to_csv(path, index=False)
    return path


def test_markdown_to_stdout(biased_csv, capsys):
    assert main(["summary", str(biased_csv), "--outcome", "selected"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "# Bias-audit summary (selection rates)" in out and "## intersectional" in out


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "aedt-audit 0." in capsys.readouterr().out


def test_json_and_html_to_files_create_parent_dirs(biased_csv, tmp_path):
    target = tmp_path / "out" / "deep" / "report.json"
    code = main(
        [
            "summary",
            str(biased_csv),
            "--outcome",
            "selected",
            "--significance",
            "--format",
            "json",
            "--out",
            str(target),
            "--tool-name",
            "screener-x",
        ]
    )
    assert code == EXIT_OK
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["metadata"]["tool_name"] == "screener-x"
    assert "z_score" in payload["tables"]["sex"][0]
    html = tmp_path / "report.html"
    assert (
        main(
            [
                "summary",
                str(biased_csv),
                "--outcome",
                "selected",
                "--format",
                "html",
                "--out",
                str(html),
            ]
        )
        == EXIT_OK
    )
    assert html.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_csv_format_writes_three_files_and_needs_out(biased_csv, tmp_path, capsys):
    assert (
        main(["summary", str(biased_csv), "--outcome", "selected", "--format", "csv"]) == EXIT_ERROR
    )
    assert "--out" in capsys.readouterr().err
    target = tmp_path / "csvs"
    assert (
        main(
            [
                "summary",
                str(biased_csv),
                "--outcome",
                "selected",
                "--format",
                "csv",
                "--out",
                str(target),
            ]
        )
        == EXIT_OK
    )
    assert len(list(target.glob("ll144_selection_*.csv"))) == 3


def test_fail_on_adverse_impact_is_a_distinct_exit_code(biased_csv, fair_csv, capsys):
    code = main(["summary", str(biased_csv), "--outcome", "selected", "--fail-on-adverse-impact"])
    assert code == EXIT_FINDING
    assert "below the four-fifths line" in capsys.readouterr().err
    assert (
        main(["summary", str(fair_csv), "--outcome", "selected", "--fail-on-adverse-impact"])
        == EXIT_OK
    )


def test_missing_outcomes_error_then_opt_in_drop(tmp_path, capsys):
    df = synthetic_applicants(500, seed=2)
    df["selected"] = df["selected"].map({True: "Yes", False: "No"})
    df.loc[df.index[:7], "selected"] = None
    path = tmp_path / "ats.csv"
    df.to_csv(path, index=False)
    assert main(["summary", str(path), "--outcome", "selected"]) == EXIT_ERROR
    assert "7 missing" in capsys.readouterr().err
    assert (
        main(["summary", str(path), "--outcome", "selected", "--drop-missing-outcome"]) == EXIT_OK
    )
    captured = capsys.readouterr()
    assert "7 row(s)" in captured.err and "left out" in captured.out  # note travels into the report


def test_scoring_summary_and_custom_column_names(tmp_path, capsys):
    df = synthetic_applicants(800, seed=5).rename(
        columns={"sex": "Gender", "race_ethnicity": "Ethnicity"}
    )
    path = tmp_path / "scores.csv"
    df.to_csv(path, index=False)
    code = main(
        [
            "summary",
            str(path),
            "--score",
            "score",
            "--sex",
            "Gender",
            "--race",
            "Ethnicity",
            "--format",
            "json",
        ]
    )
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "scoring" and payload["sample_median"] is not None
    assert "Gender" in payload["tables"]["sex"][0]


def test_outcome_and_score_are_mutually_exclusive_and_required(biased_csv, capsys):
    for argv in (
        ["summary", str(biased_csv)],
        ["summary", str(biased_csv), "--outcome", "selected", "--score", "score"],
    ):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2  # argparse usage error


def test_bad_inputs_report_errors_not_tracebacks(biased_csv, capsys):
    assert main(["summary", "nope.csv", "--outcome", "selected"]) == EXIT_ERROR
    assert "no such file" in capsys.readouterr().err
    assert main(["summary", str(biased_csv), "--outcome", "nope"]) == EXIT_ERROR
    assert "'nope'" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["summary", str(biased_csv), "--outcome", "selected", "--min-share", "1.5"])


def test_lifecycle_from_label_file_pairs(tmp_path, capsys):
    periods = synthetic_lifecycle(3, seed=0, n=1500)
    argv = ["lifecycle"]
    for label, df in periods.items():
        p = tmp_path / f"{label}.csv"
        df.to_csv(p, index=False)
        argv.append(f"{label}={p}")
    argv += ["--outcome", "selected", "--drift-alert", "0.05", "--format", "json"]
    assert main(argv) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert [p["period"] for p in payload["series"]["sex"]] == ["2021", "2022", "2023"]
    assert payload["drift_alert"] == 0.05
    # a bare path uses the file name as the label
    bare = [a.split("=", 1)[1] for a in argv[1:4]]
    assert main(["lifecycle", *bare, "--outcome", "selected", "--format", "json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert [p["period"] for p in payload["series"]["sex"]] == ["2021", "2022", "2023"]


def test_lifecycle_from_period_column_keeps_first_appearance_order(tmp_path, capsys):
    frames = []
    for label, df in synthetic_lifecycle(["Q4 2024", "Q1 2025", "Q2 2025"], seed=1, n=1200).items():
        frames.append(df.assign(period=label))
    path = tmp_path / "all.csv"
    pd.concat(frames).to_csv(path, index=False)
    code = main(
        [
            "lifecycle",
            str(path),
            "--period-col",
            "period",
            "--outcome",
            "selected",
            "--format",
            "json",
            "--fail-on-review",
        ]
    )
    assert code in (EXIT_OK, EXIT_FINDING)
    payload = json.loads(capsys.readouterr().out)
    assert [p["period"] for p in payload["series"]["sex"]] == ["Q4 2024", "Q1 2025", "Q2 2025"]
    assert (
        main(["lifecycle", str(path), str(path), "--period-col", "period", "--outcome", "selected"])
        == EXIT_ERROR
    )  # exactly one file with --period-col
    assert (
        main(["lifecycle", str(path), "--period-col", "nope", "--outcome", "selected"])
        == EXIT_ERROR
    )


def test_lifecycle_fail_on_review(tmp_path):
    periods = synthetic_lifecycle(3, seed=0, n=1500)  # worsening bias -> adverse impact -> review
    argv = ["lifecycle"]
    for label, df in periods.items():
        p = tmp_path / f"{label}.csv"
        df.to_csv(p, index=False)
        argv.append(f"{label}={p}")
    assert (
        main(
            [
                *argv,
                "--outcome",
                "selected",
                "--fail-on-review",
                "--format",
                "json",
                "--out",
                str(tmp_path / "lc.json"),
            ]
        )
        == EXIT_FINDING
    )

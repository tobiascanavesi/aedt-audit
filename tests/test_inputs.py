"""Shared input handling for the CLI and the browser app."""

import numpy as np
import pandas as pd
import pytest

from aedt_audit.inputs import (
    drop_missing,
    missing_note,
    parse_period_args,
    read_table,
    split_periods,
)


def test_read_table_tries_utf8_bom_then_cp1252_then_latin1(tmp_path):
    utf8 = tmp_path / "a.csv"
    utf8.write_bytes("﻿sex,selected\nfemale,yes\n".encode())
    assert list(read_table(utf8).columns) == ["sex", "selected"]  # BOM stripped
    cp = tmp_path / "b.csv"
    cp.write_bytes("sex,selected\nfémale,yes\n".encode("cp1252"))
    assert read_table(cp)["sex"].iloc[0] == "fémale"
    assert read_table(str(cp), name="export.csv").shape == (1, 2)


def test_read_table_errors_are_specific(tmp_path):
    with pytest.raises(FileNotFoundError, match="no such file"):
        read_table(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="directory"):
        read_table(tmp_path)
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="not a valid .xlsx"):
        read_table(bad)


def test_read_table_reads_xlsx_and_uses_name_for_the_reader(tmp_path):
    pytest.importorskip("openpyxl")
    df = pd.DataFrame({"sex": ["m", "f"], "selected": [1, 0]})
    path = tmp_path / "upload.bin"  # the browser app stores uploads under a fixed name
    df.to_excel(path, index=False, engine="openpyxl")
    out = read_table(path, name="export.xlsx")
    assert list(out.columns) == ["sex", "selected"] and len(out) == 2


def test_drop_missing_treats_blank_text_as_missing():
    df = pd.DataFrame({"sex": list("abcdef"), "selected": ["yes", None, " ", "", "no", np.nan]})
    kept, dropped = drop_missing(df, "selected")
    assert dropped == 4 and list(kept["sex"]) == ["a", "e"]
    kept, dropped = drop_missing(pd.DataFrame({"x": [1.0, np.nan]}), "x")
    assert dropped == 1 and len(kept) == 1
    with pytest.raises(KeyError):
        drop_missing(df, "nope")


def test_missing_note_single_and_per_period():
    assert missing_note(4, "selected") == (
        "4 row(s) with no recorded selected were left out of this analysis."
    )
    assert missing_note({"2023": 4, "2024": 9}, "selected") == (
        "Rows with no recorded selected were left out of this analysis (2023: 4, 2024: 9)."
    )


def test_split_periods_orders_integer_labels_chronologically_and_strips_float_suffix():
    # newest-first file with a blank year: pandas reads the column as float
    df = pd.DataFrame(
        {"year": [2023.0, 2023.0, 2021.0, np.nan, 2022.0], "sex": list("fmfmf"), "selected": 1}
    )
    split = split_periods(df, "year")
    assert list(split.periods) == ["2021", "2022", "2023"]  # not "2021.0", not file order
    assert split.order == "chronological"
    assert split.no_period == 1
    assert "year" not in split.periods["2021"].columns
    assert len(split.periods["2023"]) == 2


def test_split_periods_orders_dates_and_keeps_first_appearance_otherwise():
    dates = pd.DataFrame({"p": ["2025-06-30", "2024-12-31", "2025-06-30"], "x": 1})
    assert list(split_periods(dates, "p").periods) == ["2024-12-31", "2025-06-30"]
    quarters = pd.DataFrame({"p": ["Q4 2024", "Q1 2025", "Q4 2024", "Q2 2025"], "x": 1})
    split = split_periods(quarters, "p")
    assert list(split.periods) == ["Q4 2024", "Q1 2025", "Q2 2025"]
    assert split.order == "first appearance"
    with pytest.raises(KeyError):
        split_periods(quarters, "nope")


def test_parse_period_args_labels_and_rejects_duplicates():
    assert parse_period_args(["2023=a.csv", "b/2024.csv"]) == [
        ("2023", "a.csv"),
        ("2024", "b/2024.csv"),
    ]
    with pytest.raises(ValueError, match="given twice"):
        parse_period_args(["x/data.csv", "y/data.csv"])
    with pytest.raises(ValueError, match="'2023'"):
        parse_period_args(["2023=a.csv", "2023=b.csv"])

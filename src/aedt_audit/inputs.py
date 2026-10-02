"""Reading and shaping input tables, shared by the command line and the browser app.

Both front ends accept the same files and make the same decisions about them,
so the decisions live here, once: which encodings to try, what counts as a
missing outcome, how a single file is split into audit periods and in what
order, and how duplicate period labels are rejected.
"""

from __future__ import annotations

import warnings
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

#: Spreadsheet formats read with ``pd.read_excel`` (needs the ``excel`` extra).
EXCEL_SUFFIXES = (".xlsx", ".xlsm")

#: CSV encodings tried in order. Latin-1 accepts any byte sequence, so it is
#: the last resort rather than a member of the loop.
_ENCODINGS = ("utf-8-sig", "cp1252")
_LAST_RESORT = "latin-1"


def read_table(path: str | Path, *, name: str | None = None) -> pd.DataFrame:
    """Read a ``.csv`` or ``.xlsx`` file into a DataFrame with string column names.

    ``name`` overrides the file name used to pick the reader (the browser app
    stores uploads under a fixed path). CSVs are read as UTF-8 (with or without
    a BOM), then Windows-1252, then Latin-1. Spreadsheets need openpyxl
    (``pip install 'aedt-audit[excel]'``).
    """
    file = Path(path)
    if file.is_dir():
        raise ValueError(f"{path} is a directory, not a data file")
    if not file.exists():
        raise FileNotFoundError(f"no such file: {path}")
    suffix = Path(name or file.name).suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        try:
            frame = pd.read_excel(file, engine="openpyxl")
        except ImportError as exc:
            raise ValueError(
                "reading spreadsheets needs openpyxl: pip install 'aedt-audit[excel]'"
            ) from exc
        except (zipfile.BadZipFile, ValueError, OSError) as exc:
            raise ValueError(f"{path} is not a valid .xlsx file ({exc})") from exc
    else:
        frame = None
        for encoding in _ENCODINGS:
            try:
                frame = pd.read_csv(file, encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        if frame is None:
            frame = pd.read_csv(file, encoding=_LAST_RESORT)
    frame.columns = [str(c) for c in frame.columns]
    return frame


def drop_missing(data: pd.DataFrame, column: str) -> tuple[pd.DataFrame, int]:
    """Drop rows whose ``column`` is missing or blank; return ``(kept, dropped)``.

    Blank means NaN/None or, for text columns, whitespace only — the way an
    export marks "no decision yet". This is the same notion of missing the
    rate functions refuse, so opting in here never leaves a row they would
    still reject.
    """
    if column not in data.columns:
        raise KeyError(f"column {column!r} not in data")
    values = data[column]
    missing = values.isna()
    if pd.api.types.is_object_dtype(values) or pd.api.types.is_string_dtype(values):
        blank = values.astype(str).str.strip().eq("") & values.notna()
        missing = missing | blank
    return data[~missing], int(missing.sum())


def missing_note(dropped: int | Mapping[str, int], column: str) -> str:
    """The sentence a report carries when rows without a recorded value were left out."""
    if isinstance(dropped, Mapping):
        parts = ", ".join(f"{label}: {n}" for label, n in dropped.items() if n)
        return f"Rows with no recorded {column} were left out of this analysis ({parts})."
    return f"{dropped} row(s) with no recorded {column} were left out of this analysis."


@dataclass
class PeriodSplit:
    """One file split into audit periods."""

    periods: dict[str, pd.DataFrame]
    order: str  # "chronological" or "first appearance"
    no_period: int  # rows left out because their period was missing


def split_periods(data: pd.DataFrame, column: str) -> PeriodSplit:
    """Split one table into ``{period_label: rows}`` in audit chronology.

    Rows with a missing period are left out and counted. Integral floats (an
    integer year column that pandas upcast because of blanks) label as
    ``"2021"``, not ``"2021.0"``. Labels are ordered chronologically when they
    are all integers or all parse as dates; otherwise (``"Q4 2024"``,
    ``"Q1 2025"``) the order of first appearance in the file is kept and
    ``order`` says so, so the caller can tell the user.
    """
    if column not in data.columns:
        raise KeyError(f"period column {column!r} not in data")
    present = data[column].notna()
    no_period = int((~present).sum())
    sub = data[present]
    values = sub[column]
    if pd.api.types.is_float_dtype(values) and len(values) and (values == values.round()).all():
        values = values.astype("int64")
    labels = values.astype(str)
    unique = list(dict.fromkeys(labels))

    order = "first appearance"
    try:
        keyed = sorted(unique, key=int)
        unique, order = keyed, "chronological"
    except ValueError:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # pandas warns when formats are inferred
                stamps = pd.to_datetime(pd.Series(unique), errors="raise")
            unique = [u for _, u in sorted(zip(stamps, unique, strict=True))]
            order = "chronological"
        except (ValueError, TypeError):
            pass

    periods = {label: sub[labels == label].drop(columns=[column]) for label in unique}
    return PeriodSplit(periods=periods, order=order, no_period=no_period)


def parse_period_args(items: Sequence[str]) -> list[tuple[str, str]]:
    """Turn ``LABEL=FILE`` arguments (or bare files, labelled by stem) into pairs.

    A label given twice would silently overwrite a whole audit period, so it is
    an error.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in items:
        label, sep, path = item.partition("=")
        if not sep:
            path, label = item, Path(item).stem
        if label in seen:
            raise ValueError(
                f"period label {label!r} is given twice; use LABEL=FILE to tell the files apart"
            )
        seen.add(label)
        pairs.append((label, path))
    return pairs

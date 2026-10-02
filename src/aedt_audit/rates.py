"""Selection and scoring rates for demographic categories.

Definitions follow NYC Local Law 144 of 2021 and its implementing rules
(NYC Dep't of Consumer and Worker Protection, 6 RCNY § 5-300 et seq.):

- **Selection rate**: the rate at which individuals in a category are selected
  to move forward in the hiring process (``selected / total in category``).
- **Scoring rate**: where an AEDT produces a score, the rate at which
  individuals in a category receive a score **above the sample's median score**
  (``above median / total in category``).

The DCWP rules permit excluding categories that represent less than 2% of the
data from the impact-ratio calculation, provided the exclusion is noted in the
published summary of results. This module never drops such categories: they are
kept in the output and flagged in the ``excluded`` column so reports can state
the exclusion explicitly.

Rows with a missing demographic value are reported under the ``"unknown"``
category, mirroring the requirement to disclose the number of applicants whose
demographic data is unknown.

Missing *outcomes* and missing *scores* are refused rather than guessed at: an
individual with no recorded outcome cannot be counted as selected or as not
selected without an auditor's decision, and silently doing either biases the
rate. Filter or resolve such rows before calling these functions.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

UNKNOWN = "unknown"

#: Minimum share of the sample below which a category may be excluded from the
#: impact-ratio benchmark (DCWP rules, 6 RCNY § 5-301).
DEFAULT_MIN_CATEGORY_SHARE = 0.02

_TEXT_BOOL = {
    "true": True,
    "false": False,
    "t": True,
    "f": False,
    "yes": True,
    "no": False,
    "y": True,
    "n": False,
    "1": True,
    "0": False,
}


def _normalize_categories(data: pd.DataFrame, by: Sequence[str]) -> pd.DataFrame:
    out = data.copy()
    for col in by:
        if col not in out.columns:
            raise KeyError(f"category column {col!r} not in data")
        out[col] = out[col].astype("object").where(out[col].notna(), UNKNOWN).astype(str)
    return out


def _require_rows(data: pd.DataFrame) -> None:
    if len(data) == 0:
        raise ValueError("data is empty; at least one assessed individual is required")


def _offenders(name: str, bad: np.ndarray) -> str:
    uniq = list(dict.fromkeys(str(v) for v in bad))[:5]
    return (
        f"outcome column {name!r} must be boolean, 0/1, or yes/no / true/false text; "
        f"found unrecognised value(s): {', '.join(repr(u) for u in uniq)}"
    )


def _coerce_binary(values: pd.Series, name: str) -> np.ndarray:
    """Coerce an outcome column to booleans, refusing anything ambiguous.

    Accepted: a boolean column; a numeric column whose values are all 0 or 1; a
    text column whose values (case-insensitive, stripped) are all one of
    ``true/false``, ``t/f``, ``yes/no``, ``y/n``, ``1/0``. Missing values raise.
    """
    missing = int(values.isna().sum())
    if missing:
        raise ValueError(
            f"outcome column {name!r} has {missing} missing value(s); drop or resolve them "
            "before auditing - a missing outcome cannot be counted as selected or not selected"
        )
    if pd.api.types.is_bool_dtype(values):
        return values.to_numpy(dtype=bool)
    if pd.api.types.is_numeric_dtype(values):
        arr = values.to_numpy()
        bad = ~np.isin(arr, (0, 1))
        if bad.any():
            raise ValueError(_offenders(name, arr[bad]))
        return arr.astype(bool)
    text = values.astype(str).str.strip().str.lower()
    mapped = text.map(_TEXT_BOOL)
    bad = mapped.isna()
    if bad.any():
        raise ValueError(_offenders(name, values[bad].to_numpy()))
    return mapped.to_numpy(dtype=bool)


def _validate_scores(values: pd.Series, name: str) -> None:
    if pd.api.types.is_bool_dtype(values) or not pd.api.types.is_numeric_dtype(values):
        raise ValueError(f"score column {name!r} must be numeric; got dtype {values.dtype}")
    missing = int(values.isna().sum())
    if missing:
        raise ValueError(
            f"score column {name!r} has {missing} missing value(s); drop or resolve them "
            "before auditing - an individual without a score cannot be placed relative to "
            "the median"
        )


def _rates(
    data: pd.DataFrame,
    by: Sequence[str],
    positive: np.ndarray,
    positive_label: str,
    min_category_share: float,
) -> pd.DataFrame:
    work = _normalize_categories(data, by)
    work["__positive__"] = positive
    grouped = (
        work.groupby(list(by), dropna=False)["__positive__"]
        .agg(n="size", **{positive_label: "sum"})
        .reset_index()
    )
    total = grouped["n"].sum()
    grouped["rate"] = grouped[positive_label] / grouped["n"]
    grouped["share"] = grouped["n"] / total
    grouped["excluded"] = grouped["share"] < min_category_share
    return grouped


def selection_rates(
    data: pd.DataFrame,
    *,
    by: Sequence[str],
    outcome: str,
    min_category_share: float = DEFAULT_MIN_CATEGORY_SHARE,
) -> pd.DataFrame:
    """Per-category selection rates (LL144).

    Parameters
    ----------
    data:
        One row per individual assessed by the tool.
    by:
        Demographic category column(s); pass two columns (e.g. ``["sex",
        "race_ethnicity"]``) for the intersectional analysis LL144 requires.
    outcome:
        Whether the individual was selected: a boolean column, a 0/1 column, or
        text such as ``yes``/``no`` or ``true``/``false``. Missing values raise
        ``ValueError`` — resolve them before auditing.
    min_category_share:
        Categories below this share of the sample are flagged ``excluded``
        (not dropped), per the DCWP small-category allowance.

    Returns
    -------
    DataFrame with the category columns plus ``n``, ``selected``, ``rate``,
    ``share`` and ``excluded``.
    """
    if outcome not in data.columns:
        raise KeyError(f"outcome column {outcome!r} not in data")
    _require_rows(data)
    positive = _coerce_binary(data[outcome], outcome)
    return _rates(data, by, positive, "selected", min_category_share)


def scoring_rates(
    data: pd.DataFrame,
    *,
    by: Sequence[str],
    score: str,
    min_category_share: float = DEFAULT_MIN_CATEGORY_SHARE,
) -> pd.DataFrame:
    """Per-category scoring rates (LL144).

    The scoring rate is the share of a category scoring **strictly above the
    median score of the full sample**, per the DCWP definition. The score
    column must be numeric with no missing values.

    Returns
    -------
    DataFrame with the category columns plus ``n``, ``above_median``, ``rate``,
    ``share`` and ``excluded``. The sample median used is attached as
    ``DataFrame.attrs["sample_median"]``.
    """
    if score not in data.columns:
        raise KeyError(f"score column {score!r} not in data")
    _require_rows(data)
    _validate_scores(data[score], score)
    median = float(data[score].median())
    positive = (data[score] > median).to_numpy(dtype=bool)
    result = _rates(data, by, positive, "above_median", min_category_share)
    result.attrs["sample_median"] = median
    return result

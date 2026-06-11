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
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

UNKNOWN = "unknown"

#: Minimum share of the sample below which a category may be excluded from the
#: impact-ratio benchmark (DCWP rules, 6 RCNY § 5-301).
DEFAULT_MIN_CATEGORY_SHARE = 0.02


def _normalize_categories(data: pd.DataFrame, by: Sequence[str]) -> pd.DataFrame:
    out = data.copy()
    for col in by:
        if col not in out.columns:
            raise KeyError(f"category column {col!r} not in data")
        out[col] = out[col].astype("object").where(out[col].notna(), UNKNOWN).astype(str)
    return out


def _rates(
    data: pd.DataFrame,
    by: Sequence[str],
    positive: pd.Series,
    positive_label: str,
    min_category_share: float,
) -> pd.DataFrame:
    work = _normalize_categories(data, by)
    work["__positive__"] = positive.astype(bool).to_numpy()
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
        Boolean/0-1 column: whether the individual was selected.
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
    return _rates(data, by, data[outcome], "selected", min_category_share)


def scoring_rates(
    data: pd.DataFrame,
    *,
    by: Sequence[str],
    score: str,
    min_category_share: float = DEFAULT_MIN_CATEGORY_SHARE,
) -> pd.DataFrame:
    """Per-category scoring rates (LL144).

    The scoring rate is the share of a category scoring **strictly above the
    median score of the full sample**, per the DCWP definition.

    Returns
    -------
    DataFrame with the category columns plus ``n``, ``above_median``, ``rate``,
    ``share`` and ``excluded``. The sample median used is attached as
    ``DataFrame.attrs["sample_median"]``.
    """
    if score not in data.columns:
        raise KeyError(f"score column {score!r} not in data")
    median = float(data[score].median())
    result = _rates(data, by, data[score] > median, "above_median", min_category_share)
    result.attrs["sample_median"] = median
    return result

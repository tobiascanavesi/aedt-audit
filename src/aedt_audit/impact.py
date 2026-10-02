"""Impact ratios (LL144) and the EEOC four-fifths adverse-impact rule.

- **Impact ratio** (LL144, 6 RCNY § 5-301): the selection rate (or scoring
  rate) of a category divided by the rate of the **most selected / highest
  scoring** category. The highest-rate category therefore has ratio 1.0.
- **Four-fifths rule** (EEOC Uniform Guidelines on Employee Selection
  Procedures, 29 CFR § 1607.4(D)): a selection rate for any group that is less
  than four-fifths (0.8) of the rate of the highest group is generally regarded
  by federal enforcement agencies as evidence of adverse impact.

These are distinct regimes and are kept distinct here: LL144 mandates
*publishing* impact ratios but sets no numeric threshold; the 0.8 threshold is
the federal rule of thumb. ``four_fifths`` labels its flag accordingly.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from .rates import UNKNOWN

#: The EEOC four-fifths threshold, 29 CFR § 1607.4(D).
FOUR_FIFTHS = 0.8

#: Every column this package adds to a rates table. When ``by`` is not given,
#: any other column in a table is taken to be a demographic category column.
_METRIC_COLUMNS = frozenset(
    {
        "n",
        "selected",
        "above_median",
        "rate",
        "share",
        "excluded",
        "impact_ratio",
        "adverse_impact_eeoc",
    }
)


def category_columns(table: pd.DataFrame, by: Sequence[str] | None = None) -> list[str]:
    """The demographic category column(s) of a rates table.

    ``by`` names them explicitly; otherwise every column that is not one of this
    package's metric columns is treated as a category column.
    """
    if by is not None:
        missing = [c for c in by if c not in table.columns]
        if missing:
            raise KeyError(f"category column(s) {missing!r} not in table")
        return list(by)
    return [c for c in table.columns if c not in _METRIC_COLUMNS]


def benchmark_mask(table: pd.DataFrame, by: Sequence[str] | None = None) -> pd.Series:
    """Boolean mask of the rows eligible to serve as the comparison benchmark.

    A row is *benchmarked* when it is neither flagged ``excluded`` (the <2%
    small-category allowance, 6 RCNY § 5-301) nor ``"unknown"`` in any
    demographic column (individuals whose demographics were not reported are
    disclosed but are not a comparison group, mirroring DCWP audit practice).
    These are exactly the rows the four-fifths rule compares; excluded and
    unknown rows still receive a ratio, for transparency.
    """
    if "excluded" in table.columns:
        mask = ~table["excluded"].astype(bool)
    else:
        mask = pd.Series(True, index=table.index)
    cats = category_columns(table, by)
    if cats:
        mask &= ~table[cats].astype(str).eq(UNKNOWN).any(axis=1)
    return mask


def impact_ratios(
    rates: pd.DataFrame, *, rate_col: str = "rate", by: Sequence[str] | None = None
) -> pd.DataFrame:
    """Add an ``impact_ratio`` column to a rates table.

    The benchmark (denominator) is the highest rate among the rows selected by
    :func:`benchmark_mask` — neither ``excluded`` nor ``"unknown"``. A tiny
    category cannot set the bar, and individuals whose demographics were not
    reported do not serve as a comparison group. Both kinds of rows still
    receive a ratio, for transparency. ``by`` names the demographic column(s);
    when omitted they are inferred as every non-metric column.
    """
    if rate_col not in rates.columns:
        raise KeyError(f"rate column {rate_col!r} not in rates table")
    out = rates.copy()
    eligible = out.loc[benchmark_mask(out, by) & out[rate_col].notna(), rate_col]
    benchmark = float(eligible.max()) if len(eligible) else float("nan")
    out["impact_ratio"] = out[rate_col] / benchmark if benchmark and benchmark > 0 else float("nan")
    out.attrs["benchmark_rate"] = benchmark
    return out


def four_fifths(
    rates: pd.DataFrame, *, threshold: float = FOUR_FIFTHS, by: Sequence[str] | None = None
) -> pd.DataFrame:
    """Add an ``adverse_impact_eeoc`` flag: ``impact_ratio < threshold``.

    Calls :func:`impact_ratios` first if the table has no ``impact_ratio``
    column. The flag is named for its source (EEOC four-fifths rule) to avoid
    implying LL144 sets a numeric threshold — it does not.
    """
    out = rates if "impact_ratio" in rates.columns else impact_ratios(rates, by=by)
    out = out.copy()
    out["adverse_impact_eeoc"] = out["impact_ratio"] < threshold
    return out

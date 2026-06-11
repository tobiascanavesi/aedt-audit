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

import pandas as pd

#: The EEOC four-fifths threshold, 29 CFR § 1607.4(D).
FOUR_FIFTHS = 0.8


def impact_ratios(rates: pd.DataFrame, *, rate_col: str = "rate") -> pd.DataFrame:
    """Add an ``impact_ratio`` column to a rates table.

    The benchmark (denominator) is the highest rate among categories **not**
    flagged ``excluded``, so a tiny category cannot set the bar; excluded
    categories still receive a ratio for transparency.
    """
    if rate_col not in rates.columns:
        raise KeyError(f"rate column {rate_col!r} not in rates table")
    out = rates.copy()
    included = ~out["excluded"] if "excluded" in out else out[rate_col].notna()
    eligible = out.loc[included, rate_col]
    benchmark = float(eligible.max()) if len(eligible) else float("nan")
    out["impact_ratio"] = out[rate_col] / benchmark if benchmark and benchmark > 0 else float("nan")
    out.attrs["benchmark_rate"] = benchmark
    return out


def four_fifths(rates: pd.DataFrame, *, threshold: float = FOUR_FIFTHS) -> pd.DataFrame:
    """Add an ``adverse_impact_eeoc`` flag: ``impact_ratio < threshold``.

    Calls :func:`impact_ratios` first if the table has no ``impact_ratio``
    column. The flag is named for its source (EEOC four-fifths rule) to avoid
    implying LL144 sets a numeric threshold — it does not.
    """
    out = rates if "impact_ratio" in rates.columns else impact_ratios(rates)
    out = out.copy()
    out["adverse_impact_eeoc"] = out["impact_ratio"] < threshold
    return out

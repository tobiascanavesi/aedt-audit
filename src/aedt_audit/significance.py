"""Statistical significance of rate differences (EEOC Uniform Guidelines).

The four-fifths rule is a rule of thumb. 29 CFR § 1607.4(D) adds that smaller
differences "may nevertheless constitute adverse impact, where they are
significant in both statistical and practical terms", and that greater
differences may not, where they are "based on small numbers and are not
statistically significant". Federal agencies and courts assess statistical
significance with the *standard-deviation analysis* described in *Castaneda v.
Partida*, 430 U.S. 482, 496–97 n.17 (1977) and applied to employment in
*Hazelwood School District v. United States*, 433 U.S. 299, 308–09 n.14 (1977):
a difference of more than "two or three standard deviations" from what equal
selection would produce is treated as unlikely to have arisen by chance.

This module implements that analysis as a pooled two-proportion z-test of each
category against the **benchmark** category — the highest-rate benchmarked
category, the same denominator the impact ratio uses — and reports:

- ``z_score``: the standard-deviation distance, negative when the category is
  selected less often than the benchmark;
- ``p_value``: the two-sided probability of a difference at least this large
  under equal selection (normal approximation);
- ``significant_2sd``: whether the category falls ``threshold_sd`` (default 2)
  or more standard deviations **below** the benchmark;
- ``small_sample``: fewer than 30 individuals in the two categories combined,
  where the normal approximation is unreliable and enforcement practice turns
  to exact tests;
- ``selections_to_four_fifths``: how many more selections the category would
  have needed for its rate to reach four-fifths of the benchmark rate — the
  practical size of the gap, in people.

**The test is supplementary.** The Uniform Guidelines Questions & Answers
(44 Fed. Reg. 11996, Mar. 2, 1979), Q&A 18, says enforcement agencies
"normally will use only the 80% rule of thumb"; Q&A 20–22 and 24 explain how
statistical significance and small numbers bear on it. Nothing here overrides
the ``adverse_impact_eeoc`` flag; it tells the reader how much weight that flag
can bear. No continuity correction is applied, matching the Castaneda/Hazelwood
description and federal enforcement practice.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from .impact import benchmark_mask

#: Default standard-deviation threshold ("two or three standard deviations",
#: Castaneda, 430 U.S. at 496–97 n.17; Hazelwood, 433 U.S. at 308–09 n.14).
SIGNIFICANCE_SD = 2.0

#: Below this many individuals in the two compared categories combined, the
#: normal approximation is unreliable; enforcement practice uses exact tests.
SMALL_SAMPLE_N = 30

#: The columns :func:`significance` adds.
SIGNIFICANCE_COLUMNS = (
    "z_score",
    "p_value",
    "significant_2sd",
    "small_sample",
    "selections_to_four_fifths",
)

SIGNIFICANCE_NOTE = (
    "`z_score` / `p_value`: standard-deviation analysis of each category against the "
    "benchmark category (pooled two-proportion test; Castaneda v. Partida, 430 U.S. 482 "
    "(1977); Hazelwood School District v. United States, 433 U.S. 299 (1977)). "
    "`significant_2sd` marks categories two or more standard deviations below the "
    "benchmark. `small_sample` marks comparisons of fewer than 30 individuals, where the "
    "approximation is unreliable. `selections_to_four_fifths` is how many more selections "
    "would have brought the category to the four-fifths line. Per the Uniform Guidelines "
    "Q&A (No. 18), agencies normally rely on the four-fifths rule itself; these statistics "
    "are supplementary and do not override `adverse_impact_eeoc`."
)


def selections_to_four_fifths(x_g: int, n_g: int, x_b: int, n_b: int) -> int:
    """Extra selections needed for rate ``x_g/n_g`` to reach 4/5 of ``x_b/n_b``.

    Integer arithmetic throughout: the category is below the line iff
    ``5·x_g·n_b < 4·x_b·n_g``, and the smallest count clearing it is
    ``ceil(4·x_b·n_g / (5·n_b))``. Floating-point ``ceil(0.8·p_b·n_g)`` is off
    by one for inputs such as ``x_b=3, n_b=4, n_g=5`` (3.0000000000000004 → 4).
    Returns 0 when the category already meets the line.
    """
    if n_g <= 0 or n_b <= 0:
        return 0
    if 5 * x_g * n_b >= 4 * x_b * n_g:
        return 0
    needed = -(-4 * x_b * n_g // (5 * n_b))
    return max(0, needed - x_g)


def standard_deviation_test(x_g: int, n_g: int, x_b: int, n_b: int) -> tuple[float, float]:
    """Pooled two-proportion z-test of ``x_g/n_g`` against ``x_b/n_b``.

    Returns ``(z, two_sided_p)``. ``z`` is negative when the first rate is the
    lower one. When both rates are equal and degenerate (all or none selected),
    the variance is zero and ``(0.0, 1.0)`` is returned explicitly.
    """
    if n_g <= 0 or n_b <= 0:
        return float("nan"), float("nan")
    p_g, p_b = x_g / n_g, x_b / n_b
    pooled = (x_g + x_b) / (n_g + n_b)
    variance = pooled * (1.0 - pooled) * (1.0 / n_g + 1.0 / n_b)
    if variance <= 0.0:
        return 0.0, 1.0
    z = (p_g - p_b) / math.sqrt(variance)
    return z, math.erfc(abs(z) / math.sqrt(2.0))


def _count_column(table: pd.DataFrame) -> str:
    for col in ("selected", "above_median"):
        if col in table.columns:
            return col
    raise KeyError(
        "significance() needs the per-category counts ('selected' or 'above_median' plus "
        "'n'); pass a table produced by selection_rates() or scoring_rates()"
    )


def _benchmark_index(table: pd.DataFrame, by: Sequence[str] | None):
    """Index label of the benchmark row: highest benchmarked rate; ties → largest ``n``."""
    mask = benchmark_mask(table, by) & table["rate"].notna()
    if not mask.any():
        return None
    sub = table.loc[mask]
    top = sub[sub["rate"] == sub["rate"].max()]
    return top["n"].idxmax()


def significance(
    rates: pd.DataFrame,
    *,
    threshold_sd: float = SIGNIFICANCE_SD,
    by: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Add the standard-deviation analysis to a rates table.

    Chain it after :func:`aedt_audit.four_fifths` (or :func:`impact_ratios`);
    it works on any table carrying ``n``, ``rate`` and a count column
    (``selected`` or ``above_median``). Every row is compared with the benchmark
    row — excluded and ``unknown`` rows included, for transparency, which is why
    ``significant_2sd`` is directional (only *below* the benchmark counts).

    Parameters
    ----------
    rates:
        Output of :func:`selection_rates` / :func:`scoring_rates`, optionally
        already carrying impact ratios and flags.
    threshold_sd:
        Standard deviations below the benchmark at which ``significant_2sd`` is
        set (default 2.0). The column name does not change with the threshold.
    by:
        Demographic column(s); inferred when omitted.

    Returns
    -------
    A copy of ``rates`` with :data:`SIGNIFICANCE_COLUMNS` appended and
    ``attrs["significance_sd"]`` set. With no benchmark row (every category
    excluded or unknown) the numeric columns are NaN and the flags False.
    """
    for col in ("n", "rate"):
        if col not in rates.columns:
            raise KeyError(f"column {col!r} not in rates table")
    count_col = _count_column(rates)
    out = rates.copy()
    bench = _benchmark_index(out, by)

    size = len(out)
    z = np.full(size, np.nan)
    p = np.full(size, np.nan)
    needed = np.full(size, np.nan)
    n_b = 0
    if bench is not None:
        x_b = int(out.at[bench, count_col])
        n_b = int(out.at[bench, "n"])
        counts = out[count_col].to_numpy()
        sizes = out["n"].to_numpy()
        for i in range(size):
            x_g, n_g = int(counts[i]), int(sizes[i])
            z[i], p[i] = standard_deviation_test(x_g, n_g, x_b, n_b)
            needed[i] = selections_to_four_fifths(x_g, n_g, x_b, n_b)

    out["z_score"] = z
    out["p_value"] = p
    out["significant_2sd"] = pd.Series(z, index=out.index) <= -threshold_sd
    out["small_sample"] = (out["n"] + n_b < SMALL_SAMPLE_N) if bench is not None else False
    out["selections_to_four_fifths"] = needed.astype(int) if bench is not None else needed
    out.attrs["significance_sd"] = threshold_sd
    return out

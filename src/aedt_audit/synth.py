"""Synthetic applicant pools for demos and tests.

Entirely fabricated data: no real person is represented. The optional
``score_bias`` knob injects a known disparity so examples can demonstrate the
toolkit *detecting* adverse impact against ground truth.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

SEXES = {"female": 0.485, "male": 0.485, "unknown": 0.03}

#: EEO-1 race/ethnicity categories with illustrative (not census) weights.
RACE_ETHNICITY = {
    "White": 0.46,
    "Hispanic or Latino": 0.19,
    "Black or African American": 0.13,
    "Asian": 0.12,
    "Two or More Races": 0.05,
    "American Indian or Alaska Native": 0.03,
    "Native Hawaiian or Pacific Islander": 0.02,
}


def synthetic_applicants(
    n: int = 5000,
    *,
    seed: int = 0,
    score_bias: dict[tuple[str, str], float] | None = None,
    selection_quantile: float = 0.7,
) -> pd.DataFrame:
    """Generate a fake applicant pool with a score and a selection outcome.

    Parameters
    ----------
    n:
        Number of applicants.
    seed:
        RNG seed; output is deterministic for a given seed.
    score_bias:
        Optional ``{(column, category): shift}`` map applied to the latent
        score, e.g. ``{("sex", "female"): -5.0}`` simulates a scorer biased
        against one group by 5 points.
    selection_quantile:
        Applicants scoring at or above this sample quantile are ``selected``
        (default: top 30%).

    Returns
    -------
    DataFrame with ``sex``, ``race_ethnicity``, ``score`` (0–100) and
    ``selected`` (bool).
    """
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(
        {
            "sex": rng.choice(list(SEXES), size=n, p=list(SEXES.values())),
            "race_ethnicity": rng.choice(
                list(RACE_ETHNICITY), size=n, p=list(RACE_ETHNICITY.values())
            ),
        }
    )
    score = rng.normal(60.0, 15.0, size=n)
    for (column, category), shift in (score_bias or {}).items():
        score = score + np.where(frame[column] == category, shift, 0.0)
    frame["score"] = np.clip(score, 0.0, 100.0).round(2)
    frame["selected"] = frame["score"] >= frame["score"].quantile(selection_quantile)
    return frame


def synthetic_lifecycle(
    periods: int | Sequence[str] = 5,
    *,
    seed: int = 0,
    bias_schedule: Sequence[float] | None = None,
    bias_target: tuple[str, str] = ("sex", "female"),
    start_year: int = 2021,
    n: int = 5000,
    selection_quantile: float = 0.7,
) -> dict[str, pd.DataFrame]:
    """Generate a sequence of audit-period applicant pools with a drifting bias.

    Produces the kind of longitudinal input :func:`aedt_audit.audit_lifecycle`
    consumes. By default the injected bias *worsens* over time (from −2 to −10
    points against ``bias_target``), so the lifecycle diagnostics can be shown
    catching a widening disparity against known ground truth.

    Parameters
    ----------
    periods:
        Number of audit periods (labelled with consecutive years from
        ``start_year``) or an explicit sequence of period labels.
    seed:
        Base RNG seed; period *i* uses ``seed + i`` so periods are independent
        yet the whole trajectory is deterministic.
    bias_schedule:
        Per-period score shift applied to ``bias_target``. Defaults to a linear
        worsening from −2 to −10; if given, its length must match the periods.
    bias_target:
        ``(column, category)`` the bias is injected against.

    Returns
    -------
    An ordered ``{period_label: DataFrame}`` mapping.
    """
    labels = (
        [str(start_year + i) for i in range(periods)]
        if isinstance(periods, int)
        else [str(label) for label in periods]
    )
    if bias_schedule is None:
        bias_schedule = [float(v) for v in np.linspace(-2.0, -10.0, len(labels))]
    if len(bias_schedule) != len(labels):
        raise ValueError("`bias_schedule` length must match the number of periods")

    return {
        label: synthetic_applicants(
            n,
            seed=seed + i,
            score_bias={bias_target: shift},
            selection_quantile=selection_quantile,
        )
        for i, (label, shift) in enumerate(zip(labels, bias_schedule, strict=True))
    }

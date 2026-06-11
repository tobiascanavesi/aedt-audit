"""Synthetic applicant pools for demos and tests.

Entirely fabricated data: no real person is represented. The optional
``score_bias`` knob injects a known disparity so examples can demonstrate the
toolkit *detecting* adverse impact against ground truth.
"""

from __future__ import annotations

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

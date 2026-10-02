"""Lifecycle monitoring: tracking an AEDT's bias metrics across audit periods.

Local Law 144 requires an annual bias audit, and the NIST AI Risk Management
Framework treats evaluation of consequential AI as a *continuous* Measure/Manage
activity. A single snapshot cannot answer the governance questions that arise
year over year: is the tool getting closer to tripping the four-fifths rule, and
are its disparities widening or narrowing?

This module adds a longitudinal layer on top of the existing per-period metrics.
It is inspired by the methodology of Ferrario, *A Methodology for Auditable
Trustworthiness Levels in AI Lifecycle Governance* (2026), which represents an AI
system's state as a *trustworthiness profile* over time and monitors it with two
diagnostics — a boundary margin and a profile drift. Here those objects are
re-grounded on U.S. statute:

- the **profile** at period *t* is the vector of LL144 **impact ratios** per
  benchmarked demographic group;
- the **boundary margin** is the worst benchmarked group's distance to the EEOC
  four-fifths line (``worst_ratio - 0.8``) — positive clears the rule, negative
  is evidence of adverse impact and its magnitude says how far past;
- the **profile drift** is ``(1/sqrt(n)) * ||ratios(t) - ratios(t-h)||_2`` over
  the groups shared between the two periods.

Deliberately **not** adopted from the paper: its *learned decision-tree rule* and
*arbitrary expert-defined levels/thresholds*. Those require scoring/ML logic and
expert-labeled data that this package does not touch (see the README scope note).
The only threshold used here is the statutory 0.8; the continuous margin supplies
the nuance without inventing any non-statutory band. The optional ``drift_alert``
is the user's own documented materiality threshold, never a default.

Every metric here is arithmetic over values produced by :func:`ll144_summary`;
this module adds no new legal formula of its own.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .impact import FOUR_FIFTHS, benchmark_mask
from .rates import DEFAULT_MIN_CATEGORY_SHARE
from .render import LIFECYCLE_DISCLAIMER, lifecycle_html, metadata_items
from .report import GROUPINGS, AuditMetadata, _json_safe, ll144_summary

_INTERSECTION_SEP = " × "


@dataclass
class LifecyclePoint:
    """One demographic grouping's bias profile at a single audit period."""

    period: str
    n: int  # number of benchmarked groups making up the profile
    benchmark_rate: float
    worst_group: str
    worst_ratio: float
    boundary_margin: float  # worst_ratio - FOUR_FIFTHS
    adverse_impact: bool  # worst_ratio < FOUR_FIFTHS
    drift: float | None  # vs period t-horizon; None for the first `horizon` periods
    crossed_four_fifths: bool  # adverse-impact status changed vs the previous period
    composition_changed: bool  # benchmarked group set differs from period t-horizon
    ratios: dict[str, float]  # the profile coordinates: {group: impact_ratio}


@dataclass
class LifecycleReport:
    """A per-grouping time series of :class:`LifecyclePoint` plus metadata."""

    kind: str  # "selection" or "scoring"
    horizon: int
    drift_alert: float | None
    series: dict[str, list[LifecyclePoint]]  # keyed by grouping name
    metadata: AuditMetadata = field(default_factory=AuditMetadata)

    def _flagged(self, point: LifecyclePoint) -> bool:
        drift_trigger = (
            point.drift is not None
            and self.drift_alert is not None
            and not pd.isna(point.drift)
            and point.drift > self.drift_alert
        )
        return bool(point.adverse_impact or point.crossed_four_fifths or drift_trigger)

    def to_dataframe(self) -> pd.DataFrame:
        """Tidy long-form table: one row per (grouping, period)."""
        rows = []
        for grouping, points in self.series.items():
            for p in points:
                rows.append(
                    {
                        "grouping": grouping,
                        "period": p.period,
                        "n": p.n,
                        "benchmark_rate": p.benchmark_rate,
                        "worst_group": p.worst_group,
                        "worst_ratio": p.worst_ratio,
                        "boundary_margin": p.boundary_margin,
                        "adverse_impact": p.adverse_impact,
                        "drift": p.drift,
                        "crossed_four_fifths": p.crossed_four_fifths,
                        "composition_changed": p.composition_changed,
                        "review": self._flagged(p),
                    }
                )
        return pd.DataFrame(rows)

    def triggers(self) -> pd.DataFrame:
        """The subset of periods flagged for review (adverse impact, a crossing,
        or drift above ``drift_alert``)."""
        df = self.to_dataframe()
        return df[df["review"]].reset_index(drop=True)

    def to_markdown(self, *, decimals: int = 2) -> str:
        parts = [f"# Bias-audit lifecycle summary ({self.kind} rates)"]
        meta = metadata_items(self.metadata)
        if meta:
            parts.append("\n".join(f"- **{k}**: {v}" for k, v in meta.items()))
        parts.append(f"- **drift horizon (h)**: {self.horizon} period(s)")
        if self.drift_alert is not None:
            parts.append(f"- **drift alert threshold**: {self.drift_alert:g}")
        df = self.to_dataframe()
        for grouping in self.series:
            sub = df[df["grouping"] == grouping].drop(columns="grouping")
            parts.append(f"## {grouping.replace('_', '/')}")
            parts.append(_format_table(sub, decimals).to_markdown(index=False))
        parts.append(f"*{LIFECYCLE_DISCLAIMER}*")
        return "\n\n".join(parts)

    def to_html(self, *, decimals: int = 2, fragment: bool = False) -> str:
        """A self-contained HTML report with margin/drift charts (no scripts).

        ``fragment=True`` returns just the report body for embedding.
        """
        return lifecycle_html(self, decimals=decimals, fragment=fragment)

    def to_json(self, *, decimals: int = 4) -> str:
        payload = {
            "kind": self.kind,
            "horizon": self.horizon,
            "drift_alert": self.drift_alert,
            "metadata": asdict(self.metadata),
            "series": {
                grouping: [_round_point(asdict(p), decimals) for p in points]
                for grouping, points in self.series.items()
            },
        }
        return json.dumps(_json_safe(payload), indent=2)

    def save_csvs(self, directory: str) -> list[str]:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        df = self.to_dataframe()
        paths = []
        for grouping in self.series:
            path = target / f"lifecycle_{self.kind}_{grouping}.csv"
            df[df["grouping"] == grouping].to_csv(path, index=False)
            paths.append(str(path))
        return paths


def audit_lifecycle(
    periods: Mapping[str, pd.DataFrame] | Sequence[tuple[str, pd.DataFrame]],
    *,
    sex: str = "sex",
    race: str = "race_ethnicity",
    outcome: str | None = None,
    score: str | None = None,
    horizon: int = 1,
    drift_alert: float | None = None,
    metadata: AuditMetadata | None = None,
    min_category_share: float = DEFAULT_MIN_CATEGORY_SHARE,
) -> LifecycleReport:
    """Track LL144 impact ratios across successive audit periods.

    Parameters
    ----------
    periods:
        Ordered audit snapshots — either a mapping ``{period_label: DataFrame}``
        or a sequence of ``(period_label, DataFrame)`` pairs. Each DataFrame has
        the same shape :func:`ll144_summary` expects (one row per individual
        assessed, with the demographic columns and an outcome/score column).
        Order is the audit chronology and is preserved.
    sex, race:
        Demographic column names (defaults ``"sex"`` / ``"race_ethnicity"``).
    outcome, score:
        Provide exactly one, as in :func:`ll144_summary`.
    horizon:
        The ``h`` in the profile-drift diagnostic: each period is compared to the
        period ``h`` steps earlier. The first ``h`` periods have ``drift = None``.
    drift_alert:
        Optional materiality threshold; a period whose drift exceeds it is flagged
        for review. ``None`` (default) introduces no threshold — drift is reported
        but never triggers on its own.
    metadata:
        Provenance for the published summary.

    Returns
    -------
    LifecycleReport
        A per-grouping (sex, race/ethnicity, intersectional) time series with the
        boundary margin, profile drift, and review triggers for each period.
    """
    if (outcome is None) == (score is None):
        raise ValueError("provide exactly one of `outcome` or `score`")
    if horizon < 1:
        raise ValueError("`horizon` must be a positive integer")

    items = list(periods.items()) if isinstance(periods, Mapping) else list(periods)
    if not items:
        raise ValueError("`periods` is empty; at least one audit period is required")

    summaries = [
        (
            str(label),
            ll144_summary(
                data,
                sex=sex,
                race=race,
                outcome=outcome,
                score=score,
                min_category_share=min_category_share,
            ),
        )
        for label, data in items
    ]

    grouping_cols = {"sex": [sex], "race_ethnicity": [race], "intersectional": [sex, race]}
    kind = "selection" if outcome is not None else "scoring"

    series: dict[str, list[LifecyclePoint]] = {}
    for grouping in GROUPINGS:
        cat_cols = grouping_cols[grouping]
        points: list[LifecyclePoint] = []
        history: list[dict[str, float]] = []
        for i, (label, summary) in enumerate(summaries):
            ratios, benchmark_rate = _profile(summary.tables[grouping], cat_cols)
            if ratios:
                worst_group = min(ratios, key=ratios.__getitem__)
                worst_ratio = ratios[worst_group]
            else:
                worst_group, worst_ratio = "", float("nan")
            margin = worst_ratio - FOUR_FIFTHS
            adverse = bool(worst_ratio < FOUR_FIFTHS)

            drift: float | None = None
            composition_changed = False
            if i >= horizon:
                prev = history[i - horizon]
                composition_changed = set(ratios) != set(prev)
                shared = sorted(set(ratios) & set(prev))
                if shared:
                    delta = [ratios[k] - prev[k] for k in shared]
                    drift = float(np.linalg.norm(delta) / np.sqrt(len(shared)))
                else:
                    drift = float("nan")

            crossed = bool(points and adverse != points[-1].adverse_impact)
            points.append(
                LifecyclePoint(
                    period=label,
                    n=len(ratios),
                    benchmark_rate=benchmark_rate,
                    worst_group=worst_group,
                    worst_ratio=worst_ratio,
                    boundary_margin=margin,
                    adverse_impact=adverse,
                    drift=drift,
                    crossed_four_fifths=crossed,
                    composition_changed=composition_changed,
                    ratios=ratios,
                )
            )
            history.append(ratios)
        series[grouping] = points

    return LifecycleReport(
        kind=kind,
        horizon=horizon,
        drift_alert=drift_alert,
        series=series,
        metadata=metadata or AuditMetadata(),
    )


def _profile(table: pd.DataFrame, cat_cols: Sequence[str]) -> tuple[dict[str, float], float]:
    """Extract a period's benchmarked impact-ratio profile for one grouping.

    Benchmarked groups are those the four-fifths rule actually compares: neither
    ``excluded`` (the <2% small-category allowance) nor ``"unknown"`` in any
    demographic column — :func:`aedt_audit.impact.benchmark_mask`.
    """
    sub = table.loc[benchmark_mask(table, cat_cols)]
    ratios = {
        _INTERSECTION_SEP.join(str(row[col]) for col in cat_cols): float(ratio)
        for (_, row), ratio in zip(sub.iterrows(), sub["impact_ratio"], strict=True)
    }
    benchmark_rate = float(sub["rate"].max()) if len(sub) else float("nan")
    return ratios, benchmark_rate


def _format_table(sub: pd.DataFrame, decimals: int) -> pd.DataFrame:
    """Round floats and blank out missing drift for readable Markdown."""
    out = sub.copy()
    for col in ("benchmark_rate", "worst_ratio", "boundary_margin", "drift"):
        out[col] = out[col].map(lambda x: "" if pd.isna(x) else round(float(x), decimals))
    return out


def _round_point(point: dict, decimals: int) -> dict:
    for key in ("benchmark_rate", "worst_ratio", "boundary_margin", "drift"):
        value = point.get(key)
        if isinstance(value, float):
            point[key] = round(value, decimals)
    point["ratios"] = {k: round(v, decimals) for k, v in point["ratios"].items()}
    return point

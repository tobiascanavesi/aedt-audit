"""LL144-style "summary of results" reports.

Local Law 144 requires employers to publish a summary of the most recent bias
audit: the number of individuals assessed per category, selection or scoring
rates, and impact ratios — for sex categories, race/ethnicity categories, and
the intersectional combination of both.

:func:`ll144_summary` produces all three tables in one call and renders them to
Markdown, a self-contained HTML report with charts, JSON, or CSV. This package
computes the required metrics; the bias audit itself must be conducted by an
independent auditor (6 RCNY § 5-301).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from .impact import _METRIC_COLUMNS, four_fifths
from .rates import DEFAULT_MIN_CATEGORY_SHARE, scoring_rates, selection_rates
from .render import (
    DISCLAIMER,
    RATIO_COLUMNS,
    exclusion_note,
    metadata_items,
    summary_html,
)
from .significance import SIGNIFICANCE_NOTE
from .significance import significance as _significance

GROUPINGS = ("sex", "race_ethnicity", "intersectional")


@dataclass
class AuditMetadata:
    """Provenance fields for the published summary."""

    tool_name: str = ""
    tool_version: str = ""
    data_start: str = ""
    data_end: str = ""
    prepared_by: str = ""
    notes: str = ""


_metadata_items = metadata_items
_exclusion_note = exclusion_note


def _round_table(table: pd.DataFrame, decimals: int, ratio_decimals: int) -> pd.DataFrame:
    out = table.round(decimals)
    for col in RATIO_COLUMNS:
        if col in out.columns:
            out[col] = table[col].round(ratio_decimals)
    return out


def _json_safe(obj):
    """Replace NaN floats with None so the output is valid JSON for any consumer."""
    if isinstance(obj, float):
        return None if pd.isna(obj) else obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


@dataclass
class LL144Summary:
    """The three LL144 tables plus metadata."""

    kind: str  # "selection" or "scoring"
    tables: dict[str, pd.DataFrame]
    metadata: AuditMetadata = field(default_factory=AuditMetadata)
    sample_median: float | None = None

    @property
    def has_significance(self) -> bool:
        return any("z_score" in t.columns for t in self.tables.values())

    def _notes(self) -> list[str]:
        notes = [SIGNIFICANCE_NOTE] if self.has_significance else []
        notes.append(DISCLAIMER)
        return notes

    def to_markdown(self, *, decimals: int = 2, ratio_decimals: int = 3) -> str:
        parts = [f"# Bias-audit summary ({self.kind} rates)"]
        meta = _metadata_items(self.metadata)
        if meta:
            parts.append("\n".join(f"- **{k}**: {v}" for k, v in meta.items()))
        if self.sample_median is not None:
            parts.append(f"- **sample median score**: {self.sample_median:g}")
        for name, table in self.tables.items():
            parts.append(f"## {name.replace('_', '/')}")
            parts.append(_round_table(table, decimals, ratio_decimals).to_markdown(index=False))
            note = _exclusion_note(table)
            if note:
                parts.append(f"*{note}*")
        parts.extend(f"*{note}*" for note in self._notes())
        return "\n\n".join(parts)

    def to_html(self, *, decimals: int = 2, ratio_decimals: int = 3, fragment: bool = False) -> str:
        """A self-contained HTML report: inline CSS, inline SVG charts, no scripts.

        Opens anywhere, prints to PDF, and can be emailed as a single file.
        ``fragment=True`` returns just the report body (with its styles) for
        embedding in another page.
        """
        return summary_html(
            self, decimals=decimals, ratio_decimals=ratio_decimals, fragment=fragment
        )

    def to_json(self, *, decimals: int = 4) -> str:
        payload = {
            "kind": self.kind,
            "metadata": asdict(self.metadata),
            "sample_median": self.sample_median,
            "tables": {
                name: table.round(decimals).to_dict(orient="records")
                for name, table in self.tables.items()
            },
        }
        return json.dumps(_json_safe(payload), indent=2)

    def to_dataframe(self) -> pd.DataFrame:
        """Tidy long-form table: the three groupings stacked, with a ``grouping`` column.

        Category columns absent from a grouping (e.g. ``race_ethnicity`` in the
        sex table) are left missing.
        """
        frames = [table.assign(grouping=name) for name, table in self.tables.items()]
        out = pd.concat(frames, ignore_index=True, sort=False)
        cats: list[str] = []
        for table in self.tables.values():
            cats.extend(c for c in table.columns if c not in _METRIC_COLUMNS and c not in cats)
        first = next(iter(self.tables.values()))
        metrics = [c for c in first.columns if c in _METRIC_COLUMNS]
        return out[["grouping", *cats, *metrics]]

    def save_csvs(self, directory: str) -> list[str]:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        paths = []
        for name, table in self.tables.items():
            path = target / f"ll144_{self.kind}_{name}.csv"
            table.to_csv(path, index=False)
            paths.append(str(path))
        return paths


def ll144_summary(
    data: pd.DataFrame,
    *,
    sex: str = "sex",
    race: str = "race_ethnicity",
    outcome: str | None = None,
    score: str | None = None,
    metadata: AuditMetadata | None = None,
    min_category_share: float = DEFAULT_MIN_CATEGORY_SHARE,
    significance: bool = False,
) -> LL144Summary:
    """Compute the three LL144 tables (sex, race/ethnicity, intersectional).

    Provide exactly one of ``outcome`` (binary selection) or ``score``
    (continuous; the median-rule scoring rate is used). With
    ``significance=True`` each table also carries the standard-deviation
    analysis from :func:`aedt_audit.significance` (z-score, p-value, flags,
    and the selections needed to reach the four-fifths line).
    """
    if (outcome is None) == (score is None):
        raise ValueError("provide exactly one of `outcome` or `score`")

    groupings = {"sex": [sex], "race_ethnicity": [race], "intersectional": [sex, race]}
    tables: dict[str, pd.DataFrame] = {}
    sample_median: float | None = None
    for name, by in groupings.items():
        if outcome is not None:
            rates = selection_rates(
                data, by=by, outcome=outcome, min_category_share=min_category_share
            )
        else:
            rates = scoring_rates(data, by=by, score=score, min_category_share=min_category_share)
            sample_median = rates.attrs["sample_median"]
        table = four_fifths(rates, by=by)
        tables[name] = _significance(table, by=by) if significance else table

    return LL144Summary(
        kind="selection" if outcome is not None else "scoring",
        tables=tables,
        metadata=metadata or AuditMetadata(),
        sample_median=sample_median,
    )

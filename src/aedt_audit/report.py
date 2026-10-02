"""LL144-style "summary of results" reports.

Local Law 144 requires employers to publish a summary of the most recent bias
audit: the number of individuals assessed per category, selection or scoring
rates, and impact ratios — for sex categories, race/ethnicity categories, and
the intersectional combination of both.

:func:`ll144_summary` produces all three tables in one call and renders them to
Markdown, HTML, JSON, or CSV. This package computes the required metrics; the
bias audit itself must be conducted by an independent auditor (6 RCNY § 5-301).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from html import escape
from pathlib import Path

import pandas as pd

from .impact import _METRIC_COLUMNS, four_fifths
from .rates import DEFAULT_MIN_CATEGORY_SHARE, scoring_rates, selection_rates

GROUPINGS = ("sex", "race_ethnicity", "intersectional")

#: Columns rendered with ``ratio_decimals`` instead of ``decimals``. An impact
#: ratio of 0.796 must not be displayed as 0.80 beside a flag saying it is below
#: 0.8, so ratios get one more decimal than rates by default.
RATIO_COLUMNS = ("impact_ratio",)

DISCLAIMER = (
    "Impact ratio = category rate / highest included category rate (LL144). "
    "`adverse_impact_eeoc` flags ratios below 0.8 per the EEOC four-fifths "
    "rule (29 CFR § 1607.4(D)); LL144 itself sets no numeric threshold. "
    "This summary is generated tooling output, not an independent bias audit "
    "and not legal advice."
)


@dataclass
class AuditMetadata:
    """Provenance fields for the published summary."""

    tool_name: str = ""
    tool_version: str = ""
    data_start: str = ""
    data_end: str = ""
    prepared_by: str = ""
    notes: str = ""


def _metadata_items(metadata: AuditMetadata) -> dict[str, str]:
    """The non-empty metadata fields, in declaration order."""
    return {k: v for k, v in asdict(metadata).items() if v}


def _exclusion_note(table: pd.DataFrame) -> str | None:
    """The DCWP small-category disclosure for a table, or ``None`` if nothing is excluded."""
    if "excluded" not in table.columns or not table["excluded"].any():
        return None
    cat_cols = [c for c in table.columns if c not in _METRIC_COLUMNS]
    small = table.loc[table["excluded"], cat_cols]
    cats = ", ".join(" × ".join(str(v) for v in row) for row in small.to_numpy())
    return (
        f"Categories below 2% of the sample ({cats}) are reported but excluded "
        f"from the impact-ratio benchmark, per 6 RCNY § 5-301."
    )


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
        parts.append(f"*{DISCLAIMER}*")
        return "\n\n".join(parts)

    def to_html(self, *, decimals: int = 2, ratio_decimals: int = 3) -> str:
        parts = [f"<h1>Bias-audit summary ({escape(self.kind)} rates)</h1>"]
        items = [
            f"<li><strong>{escape(k)}</strong>: {escape(str(v))}</li>"
            for k, v in _metadata_items(self.metadata).items()
        ]
        if self.sample_median is not None:
            items.append(f"<li><strong>sample median score</strong>: {self.sample_median:g}</li>")
        if items:
            parts.append("<ul>" + "".join(items) + "</ul>")
        for name, table in self.tables.items():
            parts.append(f"<h2>{escape(name.replace('_', '/'))}</h2>")
            parts.append(
                _round_table(table, decimals, ratio_decimals).to_html(index=False, border=0)
            )
            note = _exclusion_note(table)
            if note:
                parts.append(f"<p><em>{escape(note)}</em></p>")
        parts.append(f"<p><em>{escape(DISCLAIMER)}</em></p>")
        return "\n".join(parts)

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
) -> LL144Summary:
    """Compute the three LL144 tables (sex, race/ethnicity, intersectional).

    Provide exactly one of ``outcome`` (binary selection) or ``score``
    (continuous; the median-rule scoring rate is used).
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
            rates = scoring_rates(
                data, by=by, score=score, min_category_share=min_category_share
            )
            sample_median = rates.attrs["sample_median"]
        tables[name] = four_fifths(rates, by=by)

    return LL144Summary(
        kind="selection" if outcome is not None else "scoring",
        tables=tables,
        metadata=metadata or AuditMetadata(),
        sample_median=sample_median,
    )

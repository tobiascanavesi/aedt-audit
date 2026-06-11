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

import pandas as pd

from .impact import four_fifths
from .rates import DEFAULT_MIN_CATEGORY_SHARE, scoring_rates, selection_rates

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


@dataclass
class LL144Summary:
    """The three LL144 tables plus metadata."""

    kind: str  # "selection" or "scoring"
    tables: dict[str, pd.DataFrame]
    metadata: AuditMetadata = field(default_factory=AuditMetadata)
    sample_median: float | None = None

    def to_markdown(self, *, decimals: int = 2) -> str:
        parts = [f"# Bias-audit summary ({self.kind} rates)"]
        meta = {k: v for k, v in asdict(self.metadata).items() if v}
        if meta:
            parts.append("\n".join(f"- **{k}**: {v}" for k, v in meta.items()))
        if self.sample_median is not None:
            parts.append(f"- **sample median score**: {self.sample_median:g}")
        for name, table in self.tables.items():
            parts.append(f"## {name.replace('_', '/')}")
            parts.append(table.round(decimals).to_markdown(index=False))
            if table["excluded"].any():
                small = table.loc[table["excluded"]]
                cats = ", ".join(
                    " × ".join(str(v) for v in row) for row in small.iloc[:, : -6].to_numpy()
                )
                parts.append(
                    f"*Categories below 2% of the sample ({cats}) are reported but "
                    f"excluded from the impact-ratio benchmark, per 6 RCNY § 5-301.*"
                )
        parts.append(
            "*Impact ratio = category rate / highest included category rate (LL144). "
            "`adverse_impact_eeoc` flags ratios below 0.8 per the EEOC four-fifths "
            "rule (29 CFR § 1607.4(D)); LL144 itself sets no numeric threshold. "
            "This summary is generated tooling output, not an independent bias audit "
            "and not legal advice.*"
        )
        return "\n\n".join(parts)

    def to_html(self, *, decimals: int = 2) -> str:
        body = "".join(
            f"<h2>{name.replace('_', '/')}</h2>"
            + table.round(decimals).to_html(index=False, border=0)
            for name, table in self.tables.items()
        )
        return f"<h1>Bias-audit summary ({self.kind} rates)</h1>{body}"

    def to_json(self, *, decimals: int = 4) -> str:
        return json.dumps(
            {
                "kind": self.kind,
                "metadata": asdict(self.metadata),
                "sample_median": self.sample_median,
                "tables": {
                    name: table.round(decimals).to_dict(orient="records")
                    for name, table in self.tables.items()
                },
            },
            indent=2,
        )

    def save_csvs(self, directory: str) -> list[str]:
        from pathlib import Path

        paths = []
        for name, table in self.tables.items():
            path = Path(directory) / f"ll144_{self.kind}_{name}.csv"
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
        tables[name] = four_fifths(rates)

    return LL144Summary(
        kind="selection" if outcome is not None else "scoring",
        tables=tables,
        metadata=metadata or AuditMetadata(),
        sample_median=sample_median,
    )

"""HTML rendering for the published reports.

:func:`summary_html` and :func:`lifecycle_html` produce a complete, self-contained
HTML document — inline CSS, inline SVG charts, no JavaScript, no external assets
— that opens anywhere, prints to PDF cleanly, and can be emailed as a single
file. With ``fragment=True`` they return only the report body (with its styles),
for embedding in another page.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from html import escape
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from .charts import FLAG, FONT, MINUS, impact_ratio_chart, lifecycle_chart
from .impact import benchmark_mask, category_columns
from .rates import UNKNOWN
from .significance import SIGNIFICANCE_NOTE

if TYPE_CHECKING:  # pragma: no cover
    from .lifecycle import LifecycleReport
    from .report import LL144Summary

#: Columns rendered with ``ratio_decimals`` instead of ``decimals``. An impact
#: ratio of 0.796 must not be displayed as 0.80 beside a flag saying it is below
#: 0.8, so ratios (and the significance statistics) get one more decimal than
#: rates by default.
RATIO_COLUMNS = ("impact_ratio", "z_score", "p_value")

DISCLAIMER = (
    "Impact ratio = category rate / highest included category rate (LL144). "
    "`adverse_impact_eeoc` flags ratios below 0.8 per the EEOC four-fifths "
    "rule (29 CFR § 1607.4(D)); LL144 itself sets no numeric threshold. "
    "This summary is generated tooling output, not an independent bias audit "
    "and not legal advice."
)

LIFECYCLE_DISCLAIMER = (
    "Boundary margin = worst benchmarked impact ratio − 0.8; profile drift = "
    "`(1/√n)·‖ratios(t) − ratios(t−h)‖₂` over shared groups. Methodology after "
    "Ferrario (2026); the only threshold is the EEOC four-fifths rule (0.8, "
    "29 CFR § 1607.4(D)). LL144 mandates publishing impact ratios but sets no "
    "numeric threshold. This summary is generated tooling output, not an "
    "independent bias audit and not legal advice."
)

REPORT_CSS = (
    ".aedt-report{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;"
    "--rule:#e1e0d9;--alert:#d03b3b;--alert-bg:rgba(208,59,59,.08);"
    "font-family:" + FONT + ";color:var(--ink);background:var(--page);margin:0;"
    "padding:24px 16px 48px;line-height:1.5;-webkit-text-size-adjust:100%}"
    "@media (prefers-color-scheme:dark){.aedt-report{--page:#0d0d0d;--surface:#1a1a19;"
    "--ink:#fff;--ink-2:#c3c2b7;--rule:#2c2c2a;--alert-bg:rgba(208,59,59,.18)}}"
    ".aedt-report>*{max-width:900px;margin-left:auto;margin-right:auto}"
    ".aedt-report h1{font-size:26px;line-height:1.2;margin:0 0 6px}"
    ".aedt-report h2{font-size:18px;margin:0 0 12px}"
    ".aedt-report h3{font-size:15px;margin:16px 0 6px}"
    ".aedt-report .sub{color:var(--ink-2);margin:0 0 14px}"
    ".aedt-report dl.meta{display:grid;grid-template-columns:max-content 1fr;"
    "gap:2px 16px;font-size:14px;margin:0 0 24px}"
    ".aedt-report dl.meta dt{color:var(--ink-2)}.aedt-report dl.meta dd{margin:0}"
    ".aedt-report .glance{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));"
    "gap:12px;margin:0 auto 24px}"
    ".aedt-report .tile{background:var(--surface);border:1px solid var(--rule);"
    "border-radius:10px;padding:14px 16px}"
    ".aedt-report .tile .label{display:block;font-size:13px;color:var(--ink-2)}"
    ".aedt-report .tile .value{display:block;font-size:28px;font-weight:600;"
    "line-height:1.2;margin-top:2px}"
    ".aedt-report .tile .detail{display:block;font-size:12px;color:var(--ink-2);margin-top:4px}"
    ".aedt-report section{background:var(--surface);border:1px solid var(--rule);"
    "border-radius:12px;padding:20px;margin-bottom:20px}"
    ".aedt-report figure{margin:0 0 16px}.aedt-report svg{width:100%;height:auto;display:block}"
    ".aedt-report .tbl{overflow-x:auto}"
    ".aedt-report table{border-collapse:collapse;width:100%;font-size:13px;"
    "font-variant-numeric:tabular-nums}"
    ".aedt-report th,.aedt-report td{text-align:right;padding:6px 10px;"
    "border-bottom:1px solid var(--rule);white-space:nowrap}"
    ".aedt-report th.cat,.aedt-report td.cat{text-align:left}"
    ".aedt-report thead th{color:var(--ink-2);font-weight:600;font-size:12px}"
    ".aedt-report tr.flag td{background:var(--alert-bg)}"
    ".aedt-report tr.flag td:first-child{box-shadow:inset 3px 0 0 var(--alert)}"
    ".aedt-report tr.dim td{color:var(--ink-2)}"
    ".aedt-report .note,.aedt-report .disclaimer{color:var(--ink-2);font-size:13px}"
    ".aedt-report .how ul{padding-left:20px;margin:0}.aedt-report .how li{margin:6px 0}"
    ".aedt-report code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em}"
    "@media print{.aedt-report{padding:0;background:#fff}"
    ".aedt-report section,.aedt-report .tile{break-inside:avoid;border-color:#ccc}}"
)


def metadata_items(metadata: Any) -> dict[str, str]:
    """The non-empty metadata fields, in declaration order."""
    return {k: v for k, v in asdict(metadata).items() if v}


def exclusion_note(table: pd.DataFrame) -> str | None:
    """The DCWP small-category disclosure for a table, or ``None`` if nothing is excluded."""
    if "excluded" not in table.columns or not table["excluded"].any():
        return None
    small = table.loc[table["excluded"], category_columns(table)]
    cats = ", ".join(" × ".join(str(v) for v in row) for row in small.to_numpy())
    return (
        f"Categories below 2% of the sample ({cats}) are reported but excluded "
        f"from the impact-ratio benchmark, per 6 RCNY § 5-301."
    )


def document(title: str, body: str) -> str:
    """Wrap a report body in a complete HTML document."""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>body{{margin:0}}{REPORT_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n</body>\n</html>\n"
    )


_CODE_SPAN = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    """Escape a note for HTML and render its backticked identifiers as ``<code>``."""
    return _CODE_SPAN.sub(r"<code>\1</code>", escape(text))


def _finish(title: str, body: str, fragment: bool) -> str:
    if fragment:
        return f"<style>{REPORT_CSS}</style>\n{body}"
    return document(title, body)


# --------------------------------------------------------------------------- #
# cells and tables
# --------------------------------------------------------------------------- #

_INT_COLUMNS = {"n", "selected", "above_median", "selections_to_four_fifths"}


def _cell(col: str, value: Any, decimals: int, ratio_decimals: int) -> str:
    if isinstance(value, (bool, np.bool_)):
        if col == "adverse_impact_eeoc" and value:
            return f"{FLAG} yes"
        return "yes" if value else "no"
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return "—"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    if isinstance(value, (float, np.floating)):
        if col in _INT_COLUMNS and float(value).is_integer():
            return f"{int(value):,}"
        if col == "p_value" and value < 10**-ratio_decimals:
            return f"<{10**-ratio_decimals:.{ratio_decimals}f}"
        d = ratio_decimals if col in RATIO_COLUMNS else decimals
        return f"{value:.{d}f}".replace("-", MINUS)
    return escape(str(value))


def render_table(
    table: pd.DataFrame,
    *,
    decimals: int = 2,
    ratio_decimals: int = 3,
    text_cols: list[str] | None = None,
    flag_mask: pd.Series | None = None,
    dim_mask: pd.Series | None = None,
) -> str:
    """An HTML table with flagged rows highlighted and non-benchmarked rows dimmed."""
    text_cols = text_cols if text_cols is not None else []
    cols = list(table.columns)
    head = "".join(
        f'<th class="cat">{escape(c)}</th>' if c in text_cols else f"<th>{escape(c)}</th>"
        for c in cols
    )
    body = []
    for idx in table.index:
        row = table.loc[idx]
        cls = ""
        if flag_mask is not None and bool(flag_mask.loc[idx]):
            cls = "flag"
        elif dim_mask is not None and bool(dim_mask.loc[idx]):
            cls = "dim"
        cells = []
        for c in cols:
            if c in text_cols:
                cells.append(f'<td class="cat">{escape(str(row[c]))}</td>')
            else:
                cells.append(f"<td>{_cell(c, row[c], decimals, ratio_decimals)}</td>")
        tr = f'<tr class="{cls}">' if cls else "<tr>"
        body.append(tr + "".join(cells) + "</tr>")
    return (
        '<div class="tbl"><table><thead><tr>'
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def _tile(label: str, value: str, detail: str = "") -> str:
    d = f'<span class="detail">{escape(detail)}</span>' if detail else ""
    return (
        f'<div class="tile"><span class="label">{escape(label)}</span>'
        f'<span class="value">{escape(value)}</span>{d}</div>'
    )


def _meta_block(items: dict[str, str]) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<dt>{escape(k.replace('_', ' '))}</dt><dd>{escape(str(v))}</dd>" for k, v in items.items()
    )
    return f'<dl class="meta">{rows}</dl>'


# --------------------------------------------------------------------------- #
# LL144 summary
# --------------------------------------------------------------------------- #


def _grouping_title(name: str) -> str:
    return name.replace("_", "/")


def _summary_glance(summary: LL144Summary) -> str:
    tables = summary.tables
    first = next(iter(tables.values()))
    assessed = int(first["n"].sum())

    flagged = total_bench = 0
    worst_ratio, worst_label = float("inf"), ""
    for name, table in tables.items():
        bench = benchmark_mask(table)
        total_bench += int(bench.sum())
        flagged += int((bench & table["adverse_impact_eeoc"].astype(bool)).sum())
        sub = table.loc[bench & table["impact_ratio"].notna()]
        if len(sub):
            i = sub["impact_ratio"].idxmin()
            if float(sub.at[i, "impact_ratio"]) < worst_ratio:
                worst_ratio = float(sub.at[i, "impact_ratio"])
                cats = category_columns(table)
                worst_label = (
                    " × ".join(str(sub.at[i, c]) for c in cats) + f" ({_grouping_title(name)})"
                )

    unknown_n = 0
    inter = tables.get("intersectional")
    if inter is not None:
        cats = category_columns(inter)
        mask = inter[cats].astype(str).eq(UNKNOWN).any(axis=1)
        unknown_n = int(inter.loc[mask, "n"].sum())

    tiles = [
        _tile("Individuals assessed", f"{assessed:,}", "one row per person the tool assessed"),
        _tile(
            "Categories below four-fifths",
            f"{FLAG} {flagged}" if flagged else "0",
            f"of {total_bench} benchmarked, across the three tables",
        ),
        _tile(
            "Lowest impact ratio",
            "n/a" if worst_ratio == float("inf") else f"{worst_ratio:.3f}",
            worst_label or "no benchmarked category",
        ),
        _tile("Demographics unknown", f"{unknown_n:,}", "disclosed, not used as the benchmark"),
    ]
    return '<div class="glance">' + "".join(tiles) + "</div>"


def _summary_how(summary: LL144Summary) -> str:
    scoring = summary.kind == "scoring"
    count_word = "scored above the median" if scoring else "advanced"
    items = [
        f"<li><code>n</code>, <code>{'above_median' if scoring else 'selected'}</code>, "
        "<code>rate</code> "
        f"— how many people in the category were assessed, how many {count_word}, and the "
        "share who did. This is the raw fact everything else is built on."
        + (
            f" The scoring rate is the share scoring above the whole sample's median "
            f"score ({summary.sample_median:g})."
            if scoring and summary.sample_median is not None
            else ""
        )
        + "</li>",
        "<li><code>impact_ratio</code> — the category's rate divided by the highest benchmarked "
        "rate. 1.000 is the benchmark itself; 0.544 would mean the category advances at 54% of "
        "the benchmark's rate. Local Law 144 requires this number to be published; it sets no "
        "pass/fail line.</li>",
        f"<li><code>adverse_impact_eeoc</code> — {FLAG} marks ratios below 0.8, the federal "
        "four-fifths rule (29 CFR § 1607.4(D)). A flag is evidence of adverse impact, not a "
        "verdict: investigate whether the gap is real or sampling noise, document what you "
        "find, and involve counsel — do not rerun the numbers until they pass.</li>",
        "<li><code>excluded</code> — categories under 2% of the sample may be left out of the "
        "benchmark (6 RCNY § 5-301). They are never dropped: the row stays, in grey, and the "
        "exclusion is disclosed under the table.</li>",
        "<li><code>unknown</code> — people whose demographics were not reported. Disclosed as "
        "their own row; not used as the benchmark, so their ratio can exceed 1.</li>",
    ]
    if summary.has_significance:
        items.append(
            "<li><code>z_score</code>, <code>p_value</code>, <code>significant_2sd</code> — how "
            "many standard deviations the category sits below the benchmark and how likely a gap "
            "that large is by chance alone; two or more standard deviations is the level courts "
            "treat as unlikely to be chance. <code>small_sample</code> marks comparisons of fewer "
            "than 30 people, where this test is unreliable. <code>selections_to_four_fifths</code> "
            "is the gap in people: how many more selections would have put the category on the "
            "line. These columns never override the four-fifths flag.</li>"
        )
    items.append(
        "<li>Read the <b>intersectional</b> table last: a tool can look acceptable by sex and by "
        "race separately and still fail for specific combinations.</li>"
    )
    return '<section class="how"><h2>How to read this</h2><ul>' + "".join(items) + "</ul></section>"


def summary_html(
    summary: LL144Summary, *, decimals: int = 2, ratio_decimals: int = 3, fragment: bool = False
) -> str:
    """The LL144 summary as a self-contained HTML report with charts."""
    meta = metadata_items(summary.metadata)
    title = f"Bias-audit summary ({summary.kind} rates)"
    if meta.get("tool_name"):
        title = f"{meta['tool_name']} — {title}"
    sub_bits = [f"{summary.kind} rates"]
    if meta.get("tool_name"):
        sub_bits.append(
            meta["tool_name"] + (f" v{meta['tool_version']}" if meta.get("tool_version") else "")
        )
    if meta.get("data_start") or meta.get("data_end"):
        sub_bits.append(f"{meta.get('data_start', '…')} to {meta.get('data_end', '…')}")
    rate_word = "selection" if summary.kind == "selection" else "scoring"

    parts = ['<main class="aedt-report">', "<header><h1>Bias-audit summary</h1>"]
    parts.append(f'<p class="sub">{escape(" · ".join(sub_bits))}</p>')
    parts.append(_meta_block(meta))
    if summary.sample_median is not None:
        parts.append(f'<p class="note">Sample median score: {summary.sample_median:g}</p>')
    parts.append("</header>")
    parts.append(_summary_glance(summary))
    parts.append(_summary_how(summary))

    for name, table in summary.tables.items():
        cats = category_columns(table)
        bench = benchmark_mask(table, cats)
        bench_rate = table.attrs.get("benchmark_rate", float("nan"))
        if pd.isna(bench_rate) and bench.any():
            bench_rate = float(table.loc[bench, "rate"].max())
        subtitle = f"Each category's {rate_word} rate ÷ the benchmark rate"
        if not pd.isna(bench_rate):
            top = table.loc[bench & (table["rate"] == bench_rate)]
            if len(top):
                who = " × ".join(str(top.iloc[0][c]) for c in cats)
                subtitle += f" ({bench_rate * 100:.0f}%, {who})"
        chart = impact_ratio_chart(
            table, by=cats, title=f"Impact ratios by {_grouping_title(name)}", subtitle=subtitle
        )
        flag = bench & table["adverse_impact_eeoc"].astype(bool)
        html_table = render_table(
            table,
            decimals=decimals,
            ratio_decimals=ratio_decimals,
            text_cols=cats,
            flag_mask=flag,
            dim_mask=~bench,
        )
        parts.append(f"<section><h2>{escape(_grouping_title(name))}</h2>")
        parts.append(f"<figure>{chart}</figure>{html_table}")
        note = exclusion_note(table)
        if note:
            parts.append(f'<p class="note">{escape(note)}</p>')
        parts.append("</section>")

    parts.append("<footer>")
    if summary.has_significance:
        parts.append(f'<p class="disclaimer">{_inline(SIGNIFICANCE_NOTE)}</p>')
    parts.append(f'<p class="disclaimer">{_inline(DISCLAIMER)}</p></footer></main>')
    return _finish(title, "\n".join(parts), fragment)


# --------------------------------------------------------------------------- #
# Lifecycle report
# --------------------------------------------------------------------------- #

_LIFECYCLE_TEXT_COLS = ["period", "worst_group"]


def _lifecycle_how(report: LifecycleReport) -> str:
    alert = (
        f"({report.drift_alert:g} here)"
        if report.drift_alert is not None
        else "(none set here, so drift alone never triggers)"
    )
    h = report.horizon
    items = [
        "<li><code>boundary_margin</code> — the worst benchmarked group's impact ratio minus 0.8. "
        "Positive clears the four-fifths line with that much room; negative is evidence of "
        "adverse impact, and the size says how far past the line.</li>",
        f"<li><code>drift</code> — how much the whole set of impact ratios moved since the period "
        f"{h} step{'s' if h != 1 else ''} earlier. Rising drift means the tool's behaviour toward "
        f"groups is changing, in either direction. It triggers review only above the alert "
        f"threshold you document {alert}.</li>",
        "<li><code>crossed_four_fifths</code> — the adverse-impact status flipped versus the "
        "previous period.</li>",
        "<li><code>composition_changed</code> — the set of benchmarked groups differs from the "
        "comparison period, so drift is computed on the shared groups only.</li>",
        "<li><code>review</code> — flagged when adverse impact is present, the line was crossed, "
        "or drift exceeded the alert threshold.</li>",
    ]
    return '<section class="how"><h2>How to read this</h2><ul>' + "".join(items) + "</ul></section>"


def lifecycle_html(report: LifecycleReport, *, decimals: int = 2, fragment: bool = False) -> str:
    """The lifecycle report as a self-contained HTML document with charts."""
    meta = metadata_items(report.metadata)
    title = f"Bias-audit lifecycle summary ({report.kind} rates)"
    if meta.get("tool_name"):
        title = f"{meta['tool_name']} — {title}"
    df = report.to_dataframe()
    groupings = list(report.series)
    periods = list(dict.fromkeys(df["period"]))

    latest_margin, latest_label = float("inf"), ""
    for g in groupings:
        pts = report.series[g]
        if pts and not pd.isna(pts[-1].boundary_margin) and pts[-1].boundary_margin < latest_margin:
            latest_margin = float(pts[-1].boundary_margin)
            latest_label = f"{_grouping_title(g)}: {pts[-1].worst_group}"
    flagged = int(df["review"].sum())

    sub_bits = [f"{report.kind} rates", f"{len(periods)} audit periods"]
    if meta.get("tool_name"):
        sub_bits.append(
            meta["tool_name"] + (f" v{meta['tool_version']}" if meta.get("tool_version") else "")
        )
    extra = {"drift horizon (h)": f"{report.horizon} period(s)"}
    if report.drift_alert is not None:
        extra["drift alert threshold"] = f"{report.drift_alert:g}"

    parts = ['<main class="aedt-report">', "<header><h1>Bias-audit lifecycle summary</h1>"]
    parts.append(f'<p class="sub">{escape(" · ".join(sub_bits))}</p>')
    parts.append(_meta_block({**meta, **extra}))
    parts.append("</header>")
    tiles = [
        _tile(
            "Audit periods", str(len(periods)), f"{periods[0]} to {periods[-1]}" if periods else ""
        ),
        _tile(
            "Latest boundary margin",
            "n/a" if latest_margin == float("inf") else f"{latest_margin:+.2f}".replace("-", "−"),
            latest_label or "no benchmarked group",
        ),
        _tile(
            "Periods flagged for review",
            f"{FLAG} {flagged}" if flagged else "0",
            f"of {len(df)} grouping-periods",
        ),
    ]
    parts.append('<div class="glance">' + "".join(tiles) + "</div>")
    parts.append(_lifecycle_how(report))

    for g in groupings:
        sub = df[df["grouping"] == g].drop(columns="grouping").reset_index(drop=True)
        chart = lifecycle_chart(
            sub,
            title=f"{_grouping_title(g)}: distance to the four-fifths line over time",
            subtitle="Worst benchmarked group each period; drift of the whole impact-ratio profile",
            drift_alert=report.drift_alert,
            horizon=report.horizon,
        )
        html_table = render_table(
            sub,
            decimals=decimals,
            ratio_decimals=decimals,
            text_cols=_LIFECYCLE_TEXT_COLS,
            flag_mask=sub["review"].astype(bool),
        )
        parts.append(f"<section><h2>{escape(_grouping_title(g))}</h2>")
        parts.append(f"<figure>{chart}</figure>{html_table}</section>")

    parts.append(
        f'<footer><p class="disclaimer">{escape(LIFECYCLE_DISCLAIMER)}</p></footer></main>'
    )
    return _finish(title, "\n".join(parts), fragment)

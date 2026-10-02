"""Self-contained SVG charts for the HTML report.

Pure Python, no JavaScript, no external assets. Each chart is one ``<svg>`` with
its own ``<style>`` block, so it renders the same inline in the report, saved as
a ``.svg`` file, or pasted into a wiki, and follows the viewer's light/dark
preference. Colour is never the only channel: bars below the four-fifths line
carry a ◆ marker and say so in words, bars that are not benchmarked say why,
every mark has a native tooltip (``<title>``), and the report always places the
table beside the chart.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from html import escape

import pandas as pd

from .impact import FOUR_FIFTHS, benchmark_mask, category_columns

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

#: Styles embedded in every chart. Variables are redefined for dark mode.
CHART_STYLE = (
    ".aedt-chart{font-family:" + FONT + ";"
    "--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--grid:#e1e0d9;--axis:#c3c2b7;"
    "--series:#2a78d6;--alert:#d03b3b;--neutral:#898781}"
    "@media (prefers-color-scheme:dark){.aedt-chart{--surface:#1a1a19;--ink:#fff;"
    "--ink-2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--series:#3987e5}}"
    ".aedt-chart text{fill:var(--ink);font-size:13px}"
    ".aedt-chart .t-title{font-size:15px;font-weight:600}"
    ".aedt-chart .t-sub,.aedt-chart .t-axis,.aedt-chart .t-key,.aedt-chart .t-dim"
    "{fill:var(--ink-2);font-size:12px}"
    ".aedt-chart .t-small{fill:var(--ink-2);font-size:11px}"
    ".aedt-chart .t-val{font-variant-numeric:tabular-nums}"
    ".aedt-chart .grid{stroke:var(--grid);stroke-width:1}"
    ".aedt-chart .axis{stroke:var(--axis);stroke-width:1}"
    ".aedt-chart .threshold{stroke:var(--ink-2);stroke-width:1;stroke-dasharray:4 3}"
    ".aedt-chart .fill-series{fill:var(--series)}"
    ".aedt-chart .fill-alert{fill:var(--alert)}"
    ".aedt-chart .fill-neutral{fill:var(--neutral)}"
    ".aedt-chart .line{stroke:var(--series);stroke-width:2;fill:none;"
    "stroke-linejoin:round;stroke-linecap:round}"
    ".aedt-chart .dot{stroke:var(--surface);stroke-width:2}"
    ".aedt-chart .wash{fill:var(--alert);fill-opacity:.1}"
    ".aedt-chart .hit{fill:transparent}"
)

MINUS = "−"
FLAG = "◆"  # ◆


def _fmt_ratio(v: float) -> str:
    return "n/a" if pd.isna(v) else f"{v:.3f}"


def _fmt_signed(v: float, decimals: int = 2) -> str:
    return "n/a" if pd.isna(v) else f"{v:+.{decimals}f}".replace("-", MINUS)


def _fmt_int(v) -> str:
    return f"{int(v):,}"


def _text_w(text: str, size: float = 13.0) -> float:
    """Rough width of a sans-serif string, enough to size label columns."""
    return len(text) * size * 0.56


def _svg_open(width: int, height: int, title: str, desc: str) -> str:
    return (
        f'<svg class="aedt-chart" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'style="max-width:100%;height:auto" aria-labelledby="t d">'
        f'<title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>'
        f"<style>{CHART_STYLE}</style>"
    )


def _text(x: float, y: float, s: str, cls: str = "", anchor: str = "start") -> str:
    cls_attr = f' class="{cls}"' if cls else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}"{cls_attr} text-anchor="{anchor}" '
        f'dominant-baseline="middle">{escape(s)}</text>'
    )


def _hline(x1: float, y: float, x2: float, cls: str) -> str:
    return f'<line class="{cls}" x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}"/>'


def _hbar(x: float, y: float, w: float, h: float, cls: str, r: float = 4.0) -> str:
    """Horizontal bar growing right from ``x``: square at the baseline, rounded data-end."""
    if w <= 0:
        return ""
    r = min(r, w, h / 2)
    return (
        f'<path class="{cls}" d="M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} '
        f'v{h - 2 * r:.1f} a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z"/>'
    )


def _vbar(x: float, y_base: float, w: float, h: float, cls: str, r: float = 4.0) -> str:
    """Column growing up from the baseline ``y_base``: square at the base, rounded cap."""
    if h <= 0:
        return ""
    r = min(r, w / 2, h)
    return (
        f'<path class="{cls}" d="M{x:.1f},{y_base:.1f} v-{h - r:.1f} a{r},{r} 0 0 1 {r},-{r} '
        f'h{w - 2 * r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - r:.1f} z"/>'
    )


# --------------------------------------------------------------------------- #
# Impact-ratio bar chart (one per grouping)
# --------------------------------------------------------------------------- #


def impact_ratio_chart(
    table: pd.DataFrame,
    *,
    by: Sequence[str] | None = None,
    title: str = "Impact ratios",
    subtitle: str = "",
    width: int = 760,
) -> str:
    """Horizontal bars of impact ratios with the four-fifths and benchmark lines.

    Benchmarked categories come first, worst ratio at the top; categories that
    are not benchmarked (excluded <2% or unknown) follow in grey with the reason
    spelled out. Bars below 0.8 wear the alert colour **and** a ◆ marker with the
    words "below four-fifths". Ratios above 1.5 are clipped with a ▸ marker.
    """
    cats = category_columns(table, by)
    bench = benchmark_mask(table, by)
    count_col = next((c for c in ("selected", "above_median") if c in table.columns), None)
    count_word = "selected" if count_col == "selected" else "above the median"

    rows = []
    for idx in table.index:
        r = table.loc[idx]
        ratio = float(r["impact_ratio"]) if "impact_ratio" in table.columns else float("nan")
        is_bench = bool(bench.loc[idx])
        flagged = is_bench and bool(r.get("adverse_impact_eeoc", False))
        reason = ""
        if not is_bench:
            reason = "excluded, under 2%" if bool(r.get("excluded", False)) else "unknown"
        rows.append(
            {
                "label": " × ".join(str(r[c]) for c in cats),
                "ratio": ratio,
                "bench": is_bench,
                "flagged": flagged,
                "reason": reason,
                "n": int(r["n"]) if "n" in table.columns else None,
                "count": int(r[count_col]) if count_col else None,
                "rate": float(r["rate"]) if "rate" in table.columns else float("nan"),
            }
        )
    rows.sort(
        key=lambda d: (0 if d["bench"] else 1, math.inf if pd.isna(d["ratio"]) else d["ratio"])
    )

    pad = 16
    def _sub(d):
        bits = []
        if d["n"] is not None:
            bits.append(f"n {d['n']:,}")
        if not pd.isna(d["rate"]):
            bits.append(f"{d['rate'] * 100:.0f}% {count_word}")
        return " · ".join(bits)

    label_w = max(
        (max(_text_w(d["label"]), _text_w(_sub(d), 11)) for d in rows), default=60.0
    )
    left = int(min(300, max(110, label_w + 14)))
    right = 190
    plot_w = max(140, width - pad * 2 - left - right)
    finite = [d["ratio"] for d in rows if not pd.isna(d["ratio"])]
    data_max = max(finite, default=1.0)
    xmax = min(1.5, max(1.0, math.ceil(data_max * 10) / 10))
    title_h = 50 if subtitle else 34
    row_h, bar_h = 34, 18
    y0 = title_h + 18
    axis_h, key_h = 26, 22
    height = int(y0 + len(rows) * row_h + 6 + axis_h + key_h + pad)
    x_of = lambda v: pad + left + (min(v, xmax) / xmax) * plot_w  # noqa: E731
    y_bottom = y0 + len(rows) * row_h

    desc = f"Bar chart of impact ratios for {len(rows)} categories. " + "; ".join(
        f"{d['label']}: {_fmt_ratio(d['ratio'])}"
        + (", below four-fifths" if d["flagged"] else "")
        + (f" ({d['reason']})" if d["reason"] else "")
        for d in rows
    )
    out = [_svg_open(width, height, title, desc)]
    out.append(_text(pad, 20, title, "t-title"))
    if subtitle:
        out.append(_text(pad, 40, subtitle, "t-sub"))

    # grid, threshold and benchmark lines
    tick = 0.0
    while tick <= xmax + 1e-9:
        x = x_of(tick)
        if abs(tick - FOUR_FIFTHS) < 1e-9:
            out.append(
                f'<line class="threshold" x1="{x:.1f}" y1="{y0 - 6}" x2="{x:.1f}" y2="{y_bottom}"/>'
            )
            out.append(_text(x - 4, y0 - 12, "four-fifths 0.8", "t-small", "end"))
        elif abs(tick - 1.0) < 1e-9:
            out.append(
                f'<line class="axis" x1="{x:.1f}" y1="{y0 - 6}" x2="{x:.1f}" y2="{y_bottom}"/>'
            )
            out.append(_text(x + 4, y0 - 12, "benchmark 1.0", "t-small", "start"))
        else:
            out.append(f'<line class="grid" x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y_bottom}"/>')
        out.append(_text(x, y_bottom + 14, f"{tick:.1f}", "t-axis", "middle"))
        tick = round(tick + 0.2, 10)
    out.append(
        f'<line class="axis" x1="{x_of(0):.1f}" y1="{y0}" x2="{x_of(0):.1f}" y2="{y_bottom}"/>'
    )

    for i, d in enumerate(rows):
        y = y0 + i * row_h
        yc = y + row_h / 2
        label_cls = "" if d["bench"] else "t-dim"
        out.append(_text(pad + left - 10, yc - 7, d["label"], label_cls, "end"))
        sub = _sub(d)
        if sub:
            out.append(_text(pad + left - 10, yc + 8, sub, "t-small", "end"))

        tip_bits = [d["label"]]
        if d["n"] is not None:
            tip_bits.append(f"{d['n']:,} assessed")
        if d["count"] is not None and not pd.isna(d["rate"]):
            tip_bits.append(f"{d['count']:,} {count_word} ({d['rate'] * 100:.0f}%)")
        tip_bits.append(f"impact ratio {_fmt_ratio(d['ratio'])}")
        if d["flagged"]:
            tip_bits.append("below four-fifths")
        if d["reason"]:
            tip_bits.append(f"not benchmarked: {d['reason']}")
        out.append(f"<g><title>{escape(' · '.join(tip_bits))}</title>")
        out.append(
            f'<rect class="hit" x="{pad}" y="{y}" width="{width - 2 * pad}" height="{row_h}"/>'
        )
        if pd.isna(d["ratio"]):
            out.append(_text(x_of(0) + 8, yc, "n/a — no benchmark", "t-dim"))
        else:
            cls = (
                "fill-neutral"
                if not d["bench"]
                else ("fill-alert" if d["flagged"] else "fill-series")
            )
            w = x_of(d["ratio"]) - x_of(0)
            out.append(_hbar(x_of(0), yc - bar_h / 2, w, bar_h, cls))
            end_x = x_of(d["ratio"])
            value = _fmt_ratio(d["ratio"])
            note = ""
            if d["ratio"] > xmax:
                value = "▸ " + value
            if d["flagged"]:
                note = f" {FLAG} below four-fifths"
            elif d["reason"]:
                note = f" ({d['reason']})"
            out.append(
                f'<text x="{end_x + 8:.1f}" y="{yc:.1f}" dominant-baseline="middle">'
                f'<tspan class="t-val">{escape(value)}</tspan>'
                f'<tspan class="t-small">{escape(note)}</tspan></text>'
            )
        out.append("</g>")

    key = (
        f"{FLAG} below the EEOC four-fifths line (0.8) · grey bars are not benchmarked: "
        "under 2% of the sample, or demographics unknown"
    )
    out.append(_text(pad, y_bottom + axis_h + 10, key, "t-key"))
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# Lifecycle chart (one per grouping): boundary margin over time + profile drift
# --------------------------------------------------------------------------- #


def _nice_step(span: float) -> float:
    if span <= 0:
        return 0.1
    raw = span / 4
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def lifecycle_chart(
    points: pd.DataFrame,
    *,
    title: str = "Lifecycle",
    subtitle: str = "",
    drift_alert: float | None = None,
    horizon: int = 1,
    width: int = 760,
) -> str:
    """Two stacked panels over the audit periods.

    Top: the boundary margin (worst benchmarked impact ratio − 0.8) as a line
    with a solid zero line for the four-fifths rule and a wash over the
    negative region; periods with adverse impact wear the alert colour and a ◆.
    Bottom: profile drift as columns, with the documented alert threshold when
    one is set. ``points`` is one grouping's slice of
    :meth:`LifecycleReport.to_dataframe` (columns ``period``, ``boundary_margin``,
    ``drift``, ``adverse_impact``, ``worst_group``, ``worst_ratio``, ``review``).
    """
    n = len(points)
    periods = [str(p) for p in points["period"]]
    margins = [float(v) for v in points["boundary_margin"]]
    drifts = [float(v) if not pd.isna(v) else float("nan") for v in points["drift"]]
    adverse = [bool(v) for v in points["adverse_impact"]]

    pad, left, right = 16, 64, 24
    title_h = 50 if subtitle else 34
    a_h, gap, b_h, xlab_h, key_h = 150, 40, 96, 26, 22
    y_a0 = title_h + 16
    y_a1 = y_a0 + a_h
    y_b0 = y_a1 + gap
    y_b1 = y_b0 + b_h
    height = int(y_b1 + xlab_h + key_h + pad)
    plot_w = width - pad * 2 - left - right
    step = plot_w / max(n, 1)
    xs = [pad + left + step * (i + 0.5) for i in range(n)]

    finite_m = [m for m in margins if not pd.isna(m)]
    lo = min(0.0, min(finite_m, default=0.0))
    hi = max(0.0, max(finite_m, default=0.0))
    span = (hi - lo) or 0.2
    lo, hi = lo - span * 0.18, hi + span * 0.18
    y_a = lambda v: y_a1 - (v - lo) / (hi - lo) * a_h  # noqa: E731

    finite_d = [d for d in drifts if not pd.isna(d)]
    d_max = max(finite_d + ([drift_alert] if drift_alert is not None else []), default=0.0)
    d_max = (d_max or 0.1) * 1.25
    y_b = lambda v: y_b1 - (v / d_max) * b_h  # noqa: E731

    desc = "Boundary margin by period: " + "; ".join(
        f"{p} {_fmt_signed(m)}" + (" (adverse impact)" if a else "")
        for p, m, a in zip(periods, margins, adverse, strict=True)
    )
    out = [_svg_open(width, height, title, desc)]
    out.append(_text(pad, 20, title, "t-title"))
    if subtitle:
        out.append(_text(pad, 40, subtitle, "t-sub"))

    # panel A: margin
    out.append(
        _text(pad + left, y_a0 - 8, f"Boundary margin (worst impact ratio {MINUS} 0.8)", "t-sub")
    )
    if lo < 0:
        out.append(
            f'<rect class="wash" x="{pad + left}" y="{y_a(0):.1f}" width="{plot_w}" '
            f'height="{y_a1 - y_a(0):.1f}"/>'
        )
    tick_step = _nice_step(hi - lo)
    t = math.ceil(lo / tick_step) * tick_step
    while t <= hi + 1e-9:
        yy = y_a(t)
        cls = "axis" if abs(t) < 1e-9 else "grid"
        out.append(_hline(pad + left, yy, pad + left + plot_w, cls))
        out.append(
            _text(pad + left - 8, yy, _fmt_signed(t, 2) if abs(t) > 1e-9 else "0", "t-axis", "end")
        )
        t = round(t + tick_step, 10)
    if lo <= 0 <= hi:
        out.append(_text(pad + left + plot_w, y_a(0) - 9, "four-fifths line", "t-small", "end"))

    path = []
    for x, m in zip(xs, margins, strict=True):
        if pd.isna(m):
            continue
        path.append(f"{'M' if not path else 'L'}{x:.1f},{y_a(m):.1f}")
    if len(path) > 1:
        out.append(f'<path class="line" d="{" ".join(path)}"/>')
    label_idx = set()
    if finite_m:
        label_idx.add(min(i for i in range(n) if not pd.isna(margins[i])))  # first period
        label_idx.add(max(i for i in range(n) if not pd.isna(margins[i])))  # endpoint
        label_idx.add(min(range(n), key=lambda i: math.inf if pd.isna(margins[i]) else margins[i]))
    for i, (x, m, a) in enumerate(zip(xs, margins, adverse, strict=True)):
        if pd.isna(m):
            continue
        cls = "fill-alert" if a else "fill-series"
        out.append(f'<circle class="dot {cls}" cx="{x:.1f}" cy="{y_a(m):.1f}" r="4.5"/>')
        if a:
            out.append(_text(x, y_a(m) - 13, FLAG, "t-small", "middle"))
        if i in label_idx:
            dy = 16 if m < 0 else -14
            if a:
                dy = 16
            out.append(_text(x, y_a(m) + dy, _fmt_signed(m), "t-val", "middle"))

    # panel B: drift
    sub_b = f"Profile drift vs. {horizon} period{'s' if horizon != 1 else ''} earlier"
    out.append(_text(pad + left, y_b0 - 8, sub_b, "t-sub"))
    out.append(
        f'<line class="axis" x1="{pad + left}" y1="{y_b1}" x2="{pad + left + plot_w}" y2="{y_b1}"/>'
    )
    out.append(_text(pad + left - 8, y_b1, "0", "t-axis", "end"))
    if drift_alert is not None:
        ya = y_b(drift_alert)
        out.append(_hline(pad + left, ya, pad + left + plot_w, "threshold"))
        out.append(_text(pad + left + 4, ya - 9, f"alert threshold {drift_alert:g}", "t-small"))
    col_w = min(24.0, step * 0.5)
    d_label_idx = set()
    if finite_d:
        d_label_idx.add(max(i for i in range(n) if not pd.isna(drifts[i])))
        d_label_idx.add(max(range(n), key=lambda i: -math.inf if pd.isna(drifts[i]) else drifts[i]))
    for i, (x, d) in enumerate(zip(xs, drifts, strict=True)):
        if pd.isna(d):
            out.append(_text(x, y_b1 - 10, "—", "t-dim", "middle"))
            continue
        h = y_b1 - y_b(d)
        out.append(_vbar(x - col_w / 2, y_b1, col_w, h, "fill-series"))
        if i in d_label_idx:
            out.append(_text(x, y_b(d) - 10, f"{d:.2f}", "t-val", "middle"))

    # shared x labels + tooltips
    for i, (x, p) in enumerate(zip(xs, periods, strict=True)):
        out.append(_text(x, y_b1 + 14, p, "t-axis", "middle"))
        r = points.iloc[i]
        tip = [
            f"{p}",
            f"worst group {r['worst_group']} at {_fmt_ratio(float(r['worst_ratio']))}",
            f"margin {_fmt_signed(margins[i])}" + (" (adverse impact)" if adverse[i] else ""),
            "drift " + ("n/a" if pd.isna(drifts[i]) else f"{drifts[i]:.3f}"),
        ]
        if "review" in points.columns and bool(r["review"]):
            tip.append("flagged for review")
        out.append(
            f"<g><title>{escape(' · '.join(tip))}</title>"
            f'<rect class="hit" x="{x - step / 2:.1f}" y="{y_a0}" width="{step:.1f}" '
            f'height="{y_b1 - y_a0}"/></g>'
        )

    key = (
        f"{FLAG} period with adverse impact (margin below 0) · "
        f"drift blank for the first {horizon} period(s)"
    )
    out.append(_text(pad, y_b1 + xlab_h + 10, key, "t-key"))
    out.append("</svg>")
    return "".join(out)

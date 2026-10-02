"""Command-line interface: the same reports without writing Python.

::

    aedt-audit summary applicants.csv --outcome selected --format html --out report.html
    aedt-audit lifecycle 2023=a.csv 2024=b.csv --outcome selected --drift-alert 0.05
    aedt-audit lifecycle all_years.csv --period-col year --score score

Exit status: 0 on success; 1 when the input could not be read or audited (the
message says why); 2 for a usage error; 3 when ``--fail-on-adverse-impact`` or
``--fail-on-review`` is set and the condition holds — a distinct code so a CI
gate can tell a finding from a typo.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from . import __version__
from .impact import benchmark_mask
from .lifecycle import audit_lifecycle
from .rates import DEFAULT_MIN_CATEGORY_SHARE
from .report import AuditMetadata, ll144_summary

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_FINDING = 3

_FORMATS = ("markdown", "html", "json", "csv")
_EXCEL = (".xlsx", ".xlsm", ".xls")


def _share(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from exc
    if not 0 <= value < 1:
        raise argparse.ArgumentTypeError("--min-share must be between 0 and 1")
    return value


def _add_shared(p: argparse.ArgumentParser) -> None:
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--outcome", metavar="COL", help="yes/no column: was the person selected?")
    what.add_argument(
        "--score", metavar="COL", help="numeric score column (median-rule scoring rates)"
    )
    p.add_argument("--sex", metavar="COL", default="sex", help="sex column (default: sex)")
    p.add_argument(
        "--race",
        metavar="COL",
        default="race_ethnicity",
        help="race/ethnicity column (default: race_ethnicity)",
    )
    p.add_argument(
        "--min-share",
        type=_share,
        default=DEFAULT_MIN_CATEGORY_SHARE,
        metavar="FRACTION",
        help="categories below this share of the sample are flagged excluded (default: 0.02)",
    )
    p.add_argument(
        "--drop-missing-outcome",
        action="store_true",
        help="leave out rows whose outcome/score is missing instead of stopping; "
        "the count is reported and noted in the report",
    )
    out = p.add_argument_group("output")
    out.add_argument("--format", choices=_FORMATS, default="markdown", help="default: markdown")
    out.add_argument(
        "--out",
        metavar="PATH",
        help="file to write (markdown/html/json) or directory (csv); default: stdout",
    )
    out.add_argument("--decimals", type=int, default=2, help="decimals for rates (default: 2)")
    meta = p.add_argument_group("report details")
    meta.add_argument("--tool-name", default="")
    meta.add_argument("--tool-version", default="")
    meta.add_argument("--data-start", default="", metavar="DATE")
    meta.add_argument("--data-end", default="", metavar="DATE")
    meta.add_argument("--prepared-by", default="")
    meta.add_argument("--notes", default="")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aedt-audit",
        description="Bias-audit artifacts for automated employment decision tools: NYC Local "
        "Law 144 selection/scoring rates and impact ratios, the EEOC four-fifths flag, and the "
        "standard-deviation significance test. Not legal advice; under LL144 the audit itself "
        "must be conducted by an independent auditor.",
        epilog="exit status: 0 ok, 1 input or audit error, 2 usage error, 3 finding "
        "(with --fail-on-adverse-impact / --fail-on-review).",
    )
    p.add_argument("--version", action="version", version=f"aedt-audit {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    s = sub.add_parser(
        "summary",
        help="the three LL144 tables for one audit period",
        description="Compute the sex, race/ethnicity and intersectional tables for one data set.",
    )
    s.add_argument("data", metavar="FILE", help="CSV (or .xlsx) with one row per person assessed")
    _add_shared(s)
    s.add_argument(
        "--significance",
        action="store_true",
        help="add the standard-deviation test and selections-to-four-fifths columns",
    )
    s.add_argument(
        "--fail-on-adverse-impact",
        action="store_true",
        help=f"exit {EXIT_FINDING} if any benchmarked category is below the four-fifths line",
    )

    lc = sub.add_parser(
        "lifecycle",
        help="boundary margin and drift across audit periods",
        description="Track impact ratios across successive audit periods. Give one file per "
        "period as LABEL=FILE (chronological order), or one file with --period-col.",
    )
    lc.add_argument(
        "periods",
        nargs="+",
        metavar="LABEL=FILE",
        help="period files in chronological order (a bare FILE uses its name as the label)",
    )
    lc.add_argument(
        "--period-col",
        metavar="COL",
        help="with a single FILE: the column holding the period label; periods are ordered "
        "by first appearance",
    )
    lc.add_argument(
        "--horizon", type=int, default=1, metavar="H", help="drift horizon (default: 1)"
    )
    lc.add_argument(
        "--drift-alert",
        type=float,
        metavar="X",
        help="your documented drift threshold; periods above it are flagged for review",
    )
    lc.add_argument(
        "--fail-on-review",
        action="store_true",
        help=f"exit {EXIT_FINDING} if any period is flagged for review",
    )
    _add_shared(lc)
    return p


# --------------------------------------------------------------------------- #


def _read(path: str) -> pd.DataFrame:
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"no such file: {path}")
    if file.suffix.lower() in _EXCEL:
        return pd.read_excel(file)
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(file, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(file, encoding="latin-1")


def _drop_missing(df: pd.DataFrame, col: str, enabled: bool, meta: AuditMetadata) -> pd.DataFrame:
    if not enabled or col not in df.columns:
        return df
    keep = df[col].notna()
    dropped = int((~keep).sum())
    if dropped:
        print(f"note: {dropped} row(s) with no recorded {col!r} were left out", file=sys.stderr)
        note = f"{dropped} row(s) with no recorded {col} were left out of this analysis."
        meta.notes = f"{meta.notes} {note}".strip()
    return df[keep]


def _metadata(args: argparse.Namespace) -> AuditMetadata:
    return AuditMetadata(
        tool_name=args.tool_name,
        tool_version=args.tool_version,
        data_start=args.data_start,
        data_end=args.data_end,
        prepared_by=args.prepared_by,
        notes=args.notes,
    )


def _emit(report, args: argparse.Namespace) -> None:
    fmt = args.format
    if fmt == "csv":
        if not args.out:
            raise ValueError("--format csv needs --out DIRECTORY")
        for path in report.save_csvs(args.out):
            print(path, file=sys.stderr)
        return
    if fmt == "markdown":
        text = report.to_markdown(decimals=args.decimals)
    elif fmt == "html":
        text = report.to_html(decimals=args.decimals)
    else:
        text = report.to_json()
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target}", file=sys.stderr)
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        print(text)


def _parse_periods(items: Sequence[str]) -> list[tuple[str, str]]:
    pairs = []
    for item in items:
        label, sep, path = item.partition("=")
        if not sep:
            path, label = item, Path(item).stem
        pairs.append((label, path))
    return pairs


def _run_summary(args: argparse.Namespace) -> int:
    meta = _metadata(args)
    df = _read(args.data)
    value_col = args.outcome if args.outcome is not None else args.score
    df = _drop_missing(df, value_col, args.drop_missing_outcome, meta)
    summary = ll144_summary(
        df,
        sex=args.sex,
        race=args.race,
        outcome=args.outcome,
        score=args.score,
        metadata=meta,
        min_category_share=args.min_share,
        significance=args.significance,
    )
    _emit(summary, args)
    if args.fail_on_adverse_impact:
        flagged = sum(
            int((benchmark_mask(t) & t["adverse_impact_eeoc"].astype(bool)).sum())
            for t in summary.tables.values()
        )
        if flagged:
            print(
                f"adverse impact: {flagged} benchmarked "
                f"categor{'y is' if flagged == 1 else 'ies are'} below the four-fifths line",
                file=sys.stderr,
            )
            return EXIT_FINDING
    return EXIT_OK


def _run_lifecycle(args: argparse.Namespace) -> int:
    meta = _metadata(args)
    value_col = args.outcome if args.outcome is not None else args.score
    if args.period_col:
        if len(args.periods) != 1:
            raise ValueError("--period-col takes exactly one FILE")
        df = _read(args.periods[0])
        if args.period_col not in df.columns:
            raise KeyError(f"period column {args.period_col!r} not in data")
        has_period = df[args.period_col].notna()
        if int((~has_period).sum()):
            print(
                f"note: {int((~has_period).sum())} row(s) with no period were left out",
                file=sys.stderr,
            )
            df = df[has_period]
        df = _drop_missing(df, value_col, args.drop_missing_outcome, meta)
        labels = list(dict.fromkeys(str(v) for v in df[args.period_col]))
        periods = {
            label: df[df[args.period_col].astype(str) == label].drop(columns=[args.period_col])
            for label in labels
        }
    else:
        periods = {}
        for label, path in _parse_periods(args.periods):
            periods[label] = _drop_missing(_read(path), value_col, args.drop_missing_outcome, meta)
    report = audit_lifecycle(
        periods,
        sex=args.sex,
        race=args.race,
        outcome=args.outcome,
        score=args.score,
        horizon=args.horizon,
        drift_alert=args.drift_alert,
        metadata=meta,
        min_category_share=args.min_share,
    )
    _emit(report, args)
    if args.fail_on_review:
        flagged = len(report.triggers())
        if flagged:
            print(f"review: {flagged} grouping-period(s) flagged", file=sys.stderr)
            return EXIT_FINDING
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "summary":
            return _run_summary(args)
        return _run_lifecycle(args)
    except (ValueError, KeyError, FileNotFoundError, pd.errors.ParserError, ImportError) as exc:
        message = exc.args[0] if exc.args else str(exc)
        print(f"error: {message}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-10-02

### Fixed
- Missing outcomes were silently counted as **selected** (NaN is truthy under
  `astype(bool)`), and text outcomes such as `yes`/`no` were all counted as
  selected. Outcomes are now validated: booleans, 0/1, or yes/no / true/false
  text are accepted; anything else, and any missing value, raises `ValueError`.
- Missing scores stayed in a category's `n` but could never be "above median",
  deflating that category's scoring rate. Non-numeric or missing scores now
  raise `ValueError`.
- The small-category footnote printed each excluded category's `n` as though it
  were a category (`Native Hawaiian or Pacific Islander × 95`).
- `save_csvs()` raised when the target directory did not exist (the README's
  own example). It is now created.
- `LL144Summary.to_json()` could emit bare `NaN` tokens, which is not valid
  JSON; they are now `null`, as the lifecycle report already did.
- `to_html()` omitted the metadata, the small-category disclosure, and the
  legal disclaimer that `to_markdown()` includes. `LifecycleReport.to_html()`
  added.
- Empty input now raises instead of returning an empty report.
- Impact ratios render with three decimals by default (`ratio_decimals=3`), so a
  ratio of 0.796 is no longer displayed as `0.80` beside an adverse-impact flag.

### Added
- `aedt-audit` command line (`summary` and `lifecycle`): Markdown, HTML, JSON or
  CSV output to stdout or a path, `--significance`, `--drop-missing-outcome`,
  `LABEL=FILE` periods or `--period-col`, and CI gates `--fail-on-adverse-impact`
  / `--fail-on-review` that exit with status 3 on a finding.
- **A no-code web app for HR teams** (`web/index.html`, published to GitHub
  Pages): drop in a `.csv`/`.xlsx` export, confirm which column is which, run
  the audit, and download the report, JSON, Markdown or CSVs. It runs this
  package in the browser with Pyodide, so the file never leaves the user's
  computer. Handles yes/no text decisions, rows with no recorded decision (opt-in
  exclusion, disclosed in the report), scores, and a period column for the
  lifecycle view.
- `to_html()` on both reports now returns a **complete, self-contained HTML
  document** — inline CSS, inline SVG charts, no JavaScript, no external
  assets — with an at-a-glance strip, a plain-language "how to read this"
  box, and a chart per table (bars below four-fifths marked ◆, non-benchmarked
  categories grey with the reason). `fragment=True` returns the body only.
  New `charts` module (`impact_ratio_chart`, `lifecycle_chart`) and `render`
  module; zero new dependencies.
- `significance()` and `ll144_summary(..., significance=True)`: the standard-
  deviation analysis federal guidance pairs with the four-fifths rule
  (29 CFR § 1607.4(D); *Castaneda v. Partida*; *Hazelwood*). Adds `z_score`,
  two-sided `p_value`, a directional `significant_2sd` flag, a `small_sample`
  flag (< 30 individuals compared), and `selections_to_four_fifths`, the number
  of additional selections that would have brought a category to the line.
  Supplementary by design: it never overrides `adverse_impact_eeoc`. Pure
  Python arithmetic, no scipy.
- `benchmark_mask()`: the rows the four-fifths rule actually compares (neither
  `excluded` nor `unknown`), shared by the impact-ratio, lifecycle and report code.
- `impact_ratios()` / `four_fifths()` accept `by=` to name the demographic
  columns explicitly.
- `LL144Summary.to_dataframe()` (tidy long form), mirroring the lifecycle report.
- `py.typed` marker; CI covers Python 3.10–3.14 plus a minimum-pins job at
  pandas 1.5 / numpy 1.23.

## [0.2.0] - 2026-07-21

Not published to PyPI.

### Added
- Lifecycle monitoring (`audit_lifecycle`, `synthetic_lifecycle`): boundary
  margin and profile drift of the impact-ratio profile across audit periods,
  with review triggers. Methodology after Ferrario (2026), grounded on the
  statutory EEOC 0.8 threshold only.

## [0.1.1] - 2026-06-11

### Changed
- Rows with `unknown` in any demographic column are still disclosed with their
  own impact ratio but no longer set the comparison benchmark, mirroring DCWP
  audit practice.
- README: complete worked example, badges, scoring-rate variant, related projects.

## [0.1.0] - 2026-06-11

First public release.

### Added
- Selection and scoring rates per NYC Local Law 144 / 6 RCNY § 5-301
  (median-rule scoring rates, intersectional groupings, <2% category flagging,
  unknown-demographic reporting).
- Impact ratios (LL144) and EEOC four-fifths adverse-impact flags
  (29 CFR § 1607.4(D)), kept as distinct legal regimes.
- Publishable LL144 summary-of-results reports (Markdown / HTML / JSON / CSV).
- Score-traceability JSON Schema with validator.
- Synthetic applicant generator with injectable bias for demos and tests.
- Hand-computed test fixtures for every legal formula.

[Unreleased]: https://github.com/tobiascanavesi/aedt-audit/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/tobiascanavesi/aedt-audit/compare/v0.1.1...v0.3.0
[0.2.0]: https://github.com/tobiascanavesi/aedt-audit/compare/v0.1.1...73bfd44
[0.1.1]: https://github.com/tobiascanavesi/aedt-audit/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/tobiascanavesi/aedt-audit/releases/tag/v0.1.0

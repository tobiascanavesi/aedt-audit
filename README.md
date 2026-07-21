# aedt-audit

[![PyPI](https://img.shields.io/pypi/v/aedt-audit)](https://pypi.org/project/aedt-audit/)
[![Python versions](https://img.shields.io/pypi/pyversions/aedt-audit)](https://pypi.org/project/aedt-audit/)
[![CI](https://github.com/tobiascanavesi/aedt-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/tobiascanavesi/aedt-audit/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/aedt-audit)](LICENSE)

**Bias-audit artifacts for automated employment decision tools (AEDTs).**

If your organization uses AI or algorithms to screen, score, or rank job
candidates, U.S. rules already tell you what you must measure. `aedt-audit`
computes those artifacts from a plain table — no model access, no PII — and
renders the publishable summary. It is useful to HR/people-analytics teams
preparing for an audit, independent auditors performing one, and engineers who
want bias checks in CI before a tool ever reaches production.

- **NYC Local Law 144 (2021)** requires annual bias audits of AEDTs and public
  summaries of **selection/scoring rates and impact ratios** — by sex, by
  race/ethnicity, and intersectionally (6 RCNY § 5-300 et seq.).
- The **EEOC Uniform Guidelines** (29 CFR § 1607.4(D)) treat a selection rate
  below **four-fifths (0.8)** of the highest group's rate as evidence of
  adverse impact.
- The **NIST AI Risk Management Framework** expects measurable, documented
  evaluation of AI systems used for consequential decisions.

## Contents

- [Installation](#installation)
- [A complete example](#a-complete-example)
  - [1. The input: what your data must look like](#1-the-input-what-your-data-must-look-like)
  - [2. Run the audit](#2-run-the-audit)
  - [3. The output](#3-the-output)
  - [4. How to read the tables](#4-how-to-read-the-tables)
- [Scoring tools (continuous scores)](#scoring-tools-continuous-scores)
- [Monitoring over time (lifecycle audits)](#monitoring-over-time-lifecycle-audits)
- [What it computes](#what-it-computes)
- [Score traceability](#score-traceability)
- [Scope — what this is and is not](#scope--what-this-is-and-is-not)
- [Related projects](#related-projects)
- [Contributing](#contributing)

## Installation

```bash
pip install aedt-audit            # core
pip install 'aedt-audit[schema]'  # + traceability-record validation
```

## A complete example

### 1. The input: what your data must look like

One row per person the tool assessed, three columns. That's it — most
applicant-tracking systems can export this directly:

| column | type | meaning |
|---|---|---|
| `sex` | text | self-reported sex category; missing values are reported as `unknown` |
| `race_ethnicity` | text | self-reported race/ethnicity (EEO-1 categories work well) |
| `selected` | bool / 0-1 | did this person advance (interview, shortlist, hire)? |

```text
      sex             race_ethnicity  selected
0    male                      Asian      True
1  female  Black or African American     False
2  female         Hispanic or Latino     False
3  female  Black or African American      True
4    male                      Asian     False
```

No names, no resumes, no model internals — demographic categories and an
outcome are all the law's metrics need.

> The data below is **synthetic** (5,000 fake applicants from
> `aedt_audit.synth`, seeded for reproducibility) with a scorer deliberately
> biased 8 points against one group — so we know the ground truth the audit
> should find.

### 2. Run the audit

```python
import pandas as pd
from aedt_audit import ll144_summary, AuditMetadata

applicants = pd.read_csv("applicants.csv")   # or your ATS export

summary = ll144_summary(
    applicants,
    outcome="selected",
    metadata=AuditMetadata(
        tool_name="resume-screener", tool_version="2.3.1",
        data_start="2025-01-01", data_end="2025-12-31",
    ),
)

print(summary.to_markdown())       # all three required tables
summary.save_csvs("audit_out/")    # or .to_html() / .to_json()
```

### 3. The output

Three tables — **sex**, **race/ethnicity**, and the **intersectional**
combination LL144 requires. Here are the first two on the demo data:

**sex**

| sex     |    n |   selected |   rate |   share | excluded   |   impact_ratio | adverse_impact_eeoc   |
|:--------|-----:|-----------:|-------:|--------:|:-----------|---------------:|:----------------------|
| female  | 2441 |        510 |   0.21 |    0.49 | False      |           0.54 | True                  |
| male    | 2409 |        925 |   0.38 |    0.48 | False      |           1    | False                 |
| unknown |  150 |         65 |   0.43 |    0.03 | False      |           1.13 | False                 |

**race/ethnicity**

| race_ethnicity                      |    n |   selected |   rate |   share | excluded   |   impact_ratio | adverse_impact_eeoc   |
|:------------------------------------|-----:|-----------:|-------:|--------:|:-----------|---------------:|:----------------------|
| American Indian or Alaska Native    |  154 |         43 |   0.28 |    0.03 | False      |           0.74 | True                  |
| Asian                               |  600 |        188 |   0.31 |    0.12 | False      |           0.83 | False                 |
| Black or African American           |  681 |        195 |   0.29 |    0.14 | False      |           0.76 | True                  |
| Hispanic or Latino                  |  933 |        272 |   0.29 |    0.19 | False      |           0.77 | True                  |
| Native Hawaiian or Pacific Islander |   95 |         28 |   0.29 |    0.02 | True       |           0.78 | True                  |
| Two or More Races                   |  244 |         92 |   0.38 |    0.05 | False      |           1    | False                 |
| White                               | 2293 |        682 |   0.3  |    0.46 | False      |           0.79 | True                  |

### 4. How to read the tables

Walk the columns left to right:

- **`n` / `selected` / `rate`** — 2,441 women were assessed, 510 advanced, a
  selection rate of 21%. This is the raw fact the rest is built on.
- **`impact_ratio`** — each rate divided by the **highest-rate comparison
  group** (here: men at 38%, whose ratio is therefore 1.0). Women's ratio is
  0.21 / 0.38 ≈ **0.54**: women advance at 54% the rate of men. LL144 requires
  this number to be computed and published; it does not set a pass/fail line.
- **`adverse_impact_eeoc`** — `True` whenever the impact ratio falls below
  **0.8**, the federal four-fifths rule. This is the column to scan first.
  A flag is *evidence of adverse impact, not a verdict*: the correct response
  is to investigate (Is the disparity real or sampling noise? Is a specific
  feature or cutoff driving it?), document what you find, and involve counsel —
  not to quietly rerun the numbers until they pass.
- **`excluded`** — categories under 2% of the sample (here: Native Hawaiian or
  Pacific Islander, 95 people) may be excluded from the benchmark under the
  DCWP small-category allowance. They are **never dropped**: the row stays, the
  flag is disclosed, and the published summary must say so.
- **`unknown`** — people whose demographics weren't reported are disclosed as
  their own row but do not serve as the comparison benchmark, mirroring audit
  practice. (Note their ratio can exceed 1.0, as here.)

Then look at the **intersectional table** — it exists because averages hide
compounding. On this same data, the worst cells are worse than either parent
category alone:

| sex    | race_ethnicity            |    n |   rate |   impact_ratio | adverse_impact_eeoc   |
|:-------|:--------------------------|-----:|-------:|---------------:|:----------------------|
| female | Hispanic or Latino        |  478 |   0.19 |           0.40 | True                  |
| female | White                     | 1109 |   0.20 |           0.42 | True                  |
| female | Black or African American |  335 |   0.21 |           0.43 | True                  |

A tool can look acceptable by sex and by race separately and still fail badly
for specific intersections — which is exactly why LL144 mandates this table.

The audit correctly recovered the ground truth we injected: bias against
women, surfacing in the sex table and compounding intersectionally.

## Scoring tools (continuous scores)

If your tool outputs a score instead of a yes/no, pass `score=` instead of
`outcome=`. Rates become **scoring rates** — the share of each category scoring
**above the full sample's median** (the DCWP definition); everything downstream
is identical:

```python
summary = ll144_summary(applicants, score="score")
summary.sample_median   # the median the rates are measured against
```

## Monitoring over time (lifecycle audits)

A single audit is a snapshot. But LL144 requires a **new bias audit every year**,
and the NIST AI RMF treats evaluation of consequential AI as a *continuous*
Measure/Manage activity. The two questions that only a longitudinal view can
answer are: *is this tool getting closer to tripping the four-fifths rule, and
are its disparities widening or narrowing?*

`audit_lifecycle` runs the same audit across successive periods and adds two
diagnostics on top of the impact ratios you already get — no new legal math, just
a subtraction and a distance:

- **Boundary margin** — the worst benchmarked group's distance to the four-fifths
  line (`worst_impact_ratio − 0.8`). Positive clears the rule with room to spare;
  negative is evidence of adverse impact, and its size says *how far past*.
- **Profile drift** — how much the whole impact-ratio vector moved since the
  previous period, `(1/√n)·‖ratios(t) − ratios(t−h)‖₂`. Rising drift means the
  tool's behaviour toward groups is changing, in either direction.

Each period is also flagged for review when adverse impact is present, when the
tool **crosses** the 0.8 line versus the prior year, or when drift exceeds an
optional threshold *you* document (there is no built-in drift threshold).

```python
from aedt_audit import audit_lifecycle, synthetic_lifecycle

# five yearly pools; injected bias against one group worsens −2 → −10 (synthetic)
periods = synthetic_lifecycle(periods=5, seed=0)

report = audit_lifecycle(periods, outcome="selected", drift_alert=0.05)
print(report.to_markdown())     # one time-series table per grouping
report.triggers()               # just the periods needing review
```

The **sex** grouping recovers the ground truth we injected — a tool that was fine
in 2021 and drifts into adverse impact, tripping four-fifths in 2022:

| period | worst_group | worst_ratio | boundary_margin | adverse_impact | drift | crossed_four_fifths | review |
|-------:|:------------|------------:|----------------:|:---------------|------:|:--------------------|:-------|
| 2021 | female | 0.85 |  0.05 | False |      | False | False |
| 2022 | female | 0.73 | -0.07 | True  | 0.09 | True  | True  |
| 2023 | female | 0.65 | -0.15 | True  | 0.06 | False | True  |
| 2024 | female | 0.54 | -0.26 | True  | 0.07 | False | True  |
| 2025 | female | 0.45 | -0.35 | True  | 0.06 | False | True  |

`report.to_json()`, `.to_dataframe()` (tidy long form), and `.save_csvs(dir)` are
also available, mirroring the single-period summary.

**Methodology & scope.** The lifecycle layer follows Andrea Ferrario,
*A Methodology for Auditable Trustworthiness Levels in AI Lifecycle Governance*
(2026, [arXiv:2607.16130](https://arxiv.org/abs/2607.16130)), which represents a
system's state as a *trustworthiness profile* over time and monitors it with a
boundary margin and a profile drift. Here that profile is the vector of LL144
impact ratios, and the only threshold is the statutory EEOC 0.8 — the continuous
margin supplies the nuance without inventing any non-statutory band. Consistent
with this package's scope, we **do not** adopt the paper's learned decision-tree
rule or arbitrary expert-defined levels: those require scoring/ML logic and
expert-labelled data this toolkit deliberately does not touch.

## What it computes

| Artifact | Definition source |
|---|---|
| Selection rate per category | LL144 / 6 RCNY § 5-301 |
| Scoring rate (share **above the sample median score**) | LL144 / DCWP final rule |
| Impact ratio (category rate ÷ highest comparison-group rate) | LL144 |
| Small-category (<2%) exclusion, flagged and disclosed — never silently dropped | DCWP rules |
| `unknown` demographic reporting (disclosed, not benchmarked) | DCWP rules |
| Four-fifths adverse-impact flag (labeled as EEOC, since LL144 sets no threshold) | 29 CFR § 1607.4(D) |
| Boundary margin (worst impact ratio − 0.8) across audit periods | Ferrario 2026 methodology, grounded on EEOC 0.8 |
| Profile drift (change in the impact-ratio vector between periods) | Ferrario 2026 methodology / NIST AI RMF *Measure/Manage* |
| Score-traceability record schema (JSON Schema, per-decision provenance) | NIST AI RMF *Measure/Manage* practice |

## Score traceability

`schemas/score_traceability.schema.json` defines a portable per-decision audit
record — tool identity and version, per-factor contributions, gates, human
review — **without prescribing or containing any scoring method**. Identifiers
are opaque references; the schema rejects extra fields, so PII cannot ride
along:

```python
from aedt_audit import validate_record, example_record
validate_record(example_record())   # requires: pip install 'aedt-audit[schema]'
```

## Scope — what this is and is not

- It computes the **required metrics**. Under LL144 the bias audit itself must
  be conducted by an **independent auditor**; this library serves employers
  preparing for, and auditors performing, such audits.
- It contains **only mathematics defined by statute, regulation, and federal
  guidance**. There is no candidate ranking, matching, similarity, or scoring
  logic here, and none will be added.
- It is **not legal advice**. Consult counsel about your obligations.

## Related projects

- [fairlearn](https://github.com/fairlearn/fairlearn) — general-purpose
  fairness metrics and mitigation for ML models. Use fairlearn to *improve* a
  model; use `aedt-audit` to produce the specific artifacts U.S. hiring
  regulation asks you to publish.

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Every legal
formula in this package is covered by a hand-computed test fixture; PRs that
touch the math must update the corresponding fixture.

## License

Apache-2.0 — see [LICENSE](LICENSE).

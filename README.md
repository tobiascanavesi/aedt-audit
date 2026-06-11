# aedt-audit

**Bias-audit artifacts for automated employment decision tools (AEDTs).**

If your organization uses AI or algorithms to screen, score, or rank job
candidates, U.S. rules already tell you what you must measure:

- **NYC Local Law 144 (2021)** requires annual bias audits of AEDTs and public
  summaries of **selection/scoring rates and impact ratios** — by sex, by
  race/ethnicity, and intersectionally (6 RCNY § 5-300 et seq.).
- The **EEOC Uniform Guidelines** (29 CFR § 1607.4(D)) treat a selection rate
  below **four-fifths (0.8)** of the highest group's rate as evidence of
  adverse impact.
- The **NIST AI Risk Management Framework** expects measurable, documented
  evaluation of AI systems used for consequential decisions.

`aedt-audit` computes those artifacts from a plain DataFrame — no model access,
no PII required — and renders the publishable summary tables.

```bash
pip install aedt-audit          # + [schema] for traceability validation
```

## Quickstart

```python
from aedt_audit import ll144_summary, synthetic_applicants, AuditMetadata

# Demo on synthetic data with a deliberately biased scorer:
pool = synthetic_applicants(5000, seed=0, score_bias={("sex", "female"): -8.0})

summary = ll144_summary(
    pool,
    outcome="selected",                      # or score="score" for the median-rule scoring rate
    metadata=AuditMetadata(tool_name="example-screener", data_start="2025-01-01", data_end="2025-12-31"),
)

print(summary.to_markdown())                 # sex, race/ethnicity, and intersectional tables
summary.save_csvs("audit_out/")              # or .to_html() / .to_json()
```

The injected bias is detected: the `female` category's impact ratio falls below
0.8 and is flagged `adverse_impact_eeoc` — against synthetic ground truth you
control. Bring your own data with three columns (two demographic, one outcome
or score) and you get the same tables for your tool.

### What it computes

| Artifact | Definition source |
|---|---|
| Selection rate per category | LL144 / 6 RCNY § 5-301 |
| Scoring rate (share **above the sample median score**) | LL144 / DCWP final rule |
| Impact ratio (category rate ÷ highest included category rate) | LL144 |
| Small-category (<2%) exclusion, flagged and disclosed — never silently dropped | DCWP rules |
| `unknown` demographic reporting | DCWP rules |
| Four-fifths adverse-impact flag (labeled as EEOC, since LL144 sets no threshold) | 29 CFR § 1607.4(D) |
| Score-traceability record schema (JSON Schema, per-decision provenance) | NIST AI RMF *Measure/Manage* practice |

### Score traceability

`schemas/score_traceability.schema.json` defines a portable per-decision audit
record — tool identity and version, per-factor contributions, gates, human
review — **without prescribing or containing any scoring method**. Identifiers
are opaque references; the schema rejects extra fields, so PII cannot ride
along. Validate with:

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

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Every legal
formula in this package is covered by a hand-computed test fixture; PRs that
touch the math must update the corresponding fixture.

## License

Apache-2.0 — see [LICENSE](LICENSE).

"""End-to-end demo: a biased scorer, caught.

Run:  python examples/quickstart.py
"""

from aedt_audit import AuditMetadata, ll144_summary, synthetic_applicants

# A synthetic applicant pool whose scorer is biased 8 points against one group.
pool = synthetic_applicants(5000, seed=0, score_bias={("sex", "female"): -8.0})

summary = ll144_summary(
    pool,
    outcome="selected",
    metadata=AuditMetadata(
        tool_name="example-screener",
        tool_version="2.3.1",
        data_start="2025-01-01",
        data_end="2025-12-31",
        prepared_by="aedt-audit quickstart",
        notes="Synthetic data; bias injected deliberately for demonstration.",
    ),
)

print(summary.to_markdown())

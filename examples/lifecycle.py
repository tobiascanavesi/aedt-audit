"""Lifecycle demo: a screener whose bias worsens year over year, tracked.

LL144 audits are annual; the NIST AI RMF treats evaluation as continuous. This
demo runs five yearly audits on a synthetic screener whose injected bias against
one group grows from −2 to −10 points, and shows the two lifecycle diagnostics —
boundary margin (distance to the four-fifths line) and profile drift — catching
the widening disparity.

Run:  python examples/lifecycle.py
"""

from aedt_audit import AuditMetadata, audit_lifecycle, synthetic_lifecycle

# Five yearly applicant pools; the bias against "female" worsens each year.
periods = synthetic_lifecycle(periods=5, seed=0)

report = audit_lifecycle(
    periods,
    outcome="selected",
    horizon=1,
    drift_alert=0.05,  # the auditor's documented materiality threshold (not a default)
    metadata=AuditMetadata(
        tool_name="example-screener",
        tool_version="2.x",
        prepared_by="aedt-audit lifecycle demo",
        notes="Synthetic data; a worsening bias injected deliberately for demonstration.",
    ),
)

print(report.to_markdown())

print("\n\n--- Periods flagged for review ---")
triggers = report.triggers()
print("none" if triggers.empty else triggers.to_string(index=False))

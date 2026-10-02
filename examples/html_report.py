"""Write the shareable HTML reports: one audit summary and one lifecycle report.

Run:  python examples/html_report.py
Then open audit_out/bias_audit.html and audit_out/bias_audit_lifecycle.html.
"""

from pathlib import Path

from aedt_audit import (
    AuditMetadata,
    audit_lifecycle,
    ll144_summary,
    synthetic_applicants,
    synthetic_lifecycle,
)

out = Path("audit_out")
out.mkdir(exist_ok=True)

meta = AuditMetadata(
    tool_name="example-screener",
    tool_version="2.3.1",
    data_start="2025-01-01",
    data_end="2025-12-31",
    prepared_by="aedt-audit html demo",
    notes="Synthetic data; bias injected deliberately for demonstration.",
)

pool = synthetic_applicants(5000, seed=0, score_bias={("sex", "female"): -8.0})
summary = ll144_summary(pool, outcome="selected", significance=True, metadata=meta)
(out / "bias_audit.html").write_text(summary.to_html(), encoding="utf-8")

report = audit_lifecycle(synthetic_lifecycle(5, seed=0), outcome="selected", drift_alert=0.05)
(out / "bias_audit_lifecycle.html").write_text(report.to_html(), encoding="utf-8")

print("wrote", out / "bias_audit.html", "and", out / "bias_audit_lifecycle.html")

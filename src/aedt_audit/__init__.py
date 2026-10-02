"""aedt-audit: bias-audit artifacts for automated employment decision tools.

Computes the metrics NYC Local Law 144 requires employers to publish
(selection/scoring rates and impact ratios, including intersectional
categories), flags adverse impact under the EEOC four-fifths rule, adds the
standard-deviation significance analysis federal guidance pairs with it,
renders publishable summary reports, and ships a score-traceability schema.

This package computes required metrics; under LL144 the bias audit itself must
be conducted by an independent auditor. Nothing here is legal advice.
"""

from .charts import impact_ratio_chart, lifecycle_chart
from .impact import FOUR_FIFTHS, benchmark_mask, four_fifths, impact_ratios
from .lifecycle import LifecyclePoint, LifecycleReport, audit_lifecycle
from .rates import DEFAULT_MIN_CATEGORY_SHARE, UNKNOWN, scoring_rates, selection_rates
from .report import AuditMetadata, LL144Summary, ll144_summary
from .significance import (
    SIGNIFICANCE_COLUMNS,
    SIGNIFICANCE_SD,
    selections_to_four_fifths,
    significance,
    standard_deviation_test,
)
from .synth import synthetic_applicants, synthetic_lifecycle
from .traceability import example_record, load_schema, validate_record

__version__ = "0.3.0"

__all__ = [
    "DEFAULT_MIN_CATEGORY_SHARE",
    "FOUR_FIFTHS",
    "SIGNIFICANCE_COLUMNS",
    "SIGNIFICANCE_SD",
    "UNKNOWN",
    "AuditMetadata",
    "LL144Summary",
    "LifecyclePoint",
    "LifecycleReport",
    "__version__",
    "audit_lifecycle",
    "benchmark_mask",
    "example_record",
    "four_fifths",
    "impact_ratio_chart",
    "impact_ratios",
    "lifecycle_chart",
    "ll144_summary",
    "load_schema",
    "scoring_rates",
    "selection_rates",
    "selections_to_four_fifths",
    "significance",
    "standard_deviation_test",
    "synthetic_applicants",
    "synthetic_lifecycle",
    "validate_record",
]

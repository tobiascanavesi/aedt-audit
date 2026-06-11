"""aedt-audit: bias-audit artifacts for automated employment decision tools.

Computes the metrics NYC Local Law 144 requires employers to publish
(selection/scoring rates and impact ratios, including intersectional
categories), flags adverse impact under the EEOC four-fifths rule, renders
publishable summary reports, and ships a score-traceability record schema.

This package computes required metrics; under LL144 the bias audit itself must
be conducted by an independent auditor. Nothing here is legal advice.
"""

from .impact import FOUR_FIFTHS, four_fifths, impact_ratios
from .rates import DEFAULT_MIN_CATEGORY_SHARE, UNKNOWN, scoring_rates, selection_rates
from .report import AuditMetadata, LL144Summary, ll144_summary
from .synth import synthetic_applicants
from .traceability import example_record, load_schema, validate_record

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_MIN_CATEGORY_SHARE",
    "FOUR_FIFTHS",
    "UNKNOWN",
    "AuditMetadata",
    "LL144Summary",
    "__version__",
    "example_record",
    "four_fifths",
    "impact_ratios",
    "ll144_summary",
    "load_schema",
    "scoring_rates",
    "selection_rates",
    "synthetic_applicants",
    "validate_record",
]

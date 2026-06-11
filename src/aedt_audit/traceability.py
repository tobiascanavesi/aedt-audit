"""Score-traceability records: a portable audit-trail format for AEDTs.

The schema (``schemas/score_traceability.schema.json``) describes *what a
decision record must capture* — tool identity and version, per-factor
contributions, gates, human review — without prescribing or containing any
scoring method. Any vendor or employer can adopt the format; an auditor
receiving records in it can reconstruct decision provenance uniformly.

Validation requires the optional ``jsonschema`` dependency
(``pip install aedt-audit[schema]``).
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

SCHEMA_RESOURCE = "score_traceability.schema.json"


def load_schema() -> dict[str, Any]:
    """Return the score-traceability JSON Schema bundled with the package."""
    path = resources.files("aedt_audit.schemas").joinpath(SCHEMA_RESOURCE)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_record(record: dict[str, Any]) -> None:
    """Validate one decision record against the schema.

    Raises
    ------
    jsonschema.ValidationError
        If the record does not conform.
    ImportError
        If ``jsonschema`` is not installed.
    """
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "schema validation requires the optional dependency: "
            "pip install 'aedt-audit[schema]'"
        ) from exc
    jsonschema.validate(record, load_schema())


def example_record() -> dict[str, Any]:
    """A minimal valid record, useful as a starting template."""
    return {
        "record_id": "rec-000001",
        "timestamp": "2026-01-15T12:00:00Z",
        "tool": {"name": "example-screener", "version": "2.3.1"},
        "subject_ref": "subject-7f3a",
        "score": {"value": 71.5, "scale_min": 0, "scale_max": 100},
        "factors": [
            {"name": "skills_match", "contribution": 12.4, "weight": 0.4},
            {"name": "experience_match", "contribution": 6.1, "weight": 0.35},
            {"name": "education_match", "contribution": 3.0, "weight": 0.25},
        ],
        "gates": [{"name": "minimum_requirements", "passed": True}],
        "human_review": {"occurred": False},
        "audit": {"software": "aedt-audit", "schema_version": "0.1"},
    }

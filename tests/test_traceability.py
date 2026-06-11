import pytest

jsonschema = pytest.importorskip("jsonschema")

from aedt_audit import example_record, load_schema, validate_record  # noqa: E402


def test_schema_loads_and_is_valid_jsonschema():
    schema = load_schema()
    jsonschema.Draft202012Validator.check_schema(schema)


def test_example_record_validates():
    validate_record(example_record())


def test_missing_required_field_fails():
    record = example_record()
    del record["factors"]
    with pytest.raises(jsonschema.ValidationError):
        validate_record(record)


def test_pii_like_extra_field_rejected():
    record = example_record()
    record["candidate_name"] = "Jane Doe"  # additionalProperties: false
    with pytest.raises(jsonschema.ValidationError):
        validate_record(record)

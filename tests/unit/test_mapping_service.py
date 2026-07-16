import pandas as pd
import pytest

from app.core.mapping_service import MappingService


@pytest.fixture()
def svc():
    return MappingService()


class _Mapping:
    def __init__(self, source_column: str, target_column: str):
        self.source_column = source_column
        self.target_column = target_column


def test_apply_mapping_renames_columns(svc):
    df = pd.DataFrame({"First Name": ["Alice"], "Last Name": ["Smith"]})
    mappings = [
        _Mapping("First Name", "first_name"),
        _Mapping("Last Name", "last_name"),
    ]
    result = svc.apply_mapping(df, mappings)
    assert list(result.columns) == ["first_name", "last_name"]
    assert result.iloc[0]["first_name"] == "Alice"


def test_apply_mapping_drops_unmapped_columns(svc):
    df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    mappings = [_Mapping("a", "alpha"), _Mapping("c", "gamma")]
    result = svc.apply_mapping(df, mappings)
    assert set(result.columns) == {"alpha", "gamma"}
    assert "b" not in result.columns


def test_apply_mapping_missing_source_skipped(svc):
    df = pd.DataFrame({"a": [1]})
    mappings = [_Mapping("a", "alpha"), _Mapping("nonexistent", "x")]
    result = svc.apply_mapping(df, mappings)
    assert "alpha" in result.columns
    assert "x" not in result.columns


def test_validate_mapping_reports_missing_source(svc):
    df = pd.DataFrame({"col_a": [1]})
    mappings = [_Mapping("col_a", "a"), _Mapping("col_missing", "b")]
    errors = svc.validate_mapping(df, mappings)
    assert len(errors) == 1
    assert "col_missing" in errors[0]


def test_validate_mapping_no_errors(svc):
    df = pd.DataFrame({"x": [1], "y": [2]})
    mappings = [_Mapping("x", "a"), _Mapping("y", "b")]
    errors = svc.validate_mapping(df, mappings)
    assert errors == []


def test_suggest_mappings_exact_case_insensitive(svc):
    suggestions = svc.suggest_mappings(
        ["First Name", "Email"],
        ["first_name", "email"],
    )
    src_to_tgt = {s["source"]: s["target"] for s in suggestions}
    assert src_to_tgt["First Name"] == "first_name"
    assert src_to_tgt["Email"] == "email"


def test_suggest_mappings_uses_normalized_fallback(svc):
    suggestions = svc.suggest_mappings(["My Column"], [])
    assert suggestions[0]["target"] == "my_column"

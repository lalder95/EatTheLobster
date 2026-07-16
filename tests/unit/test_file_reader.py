import io
import pathlib
import tempfile

import pandas as pd
import pytest

from app.core.file_reader import FileReader


@pytest.fixture()
def reader():
    return FileReader()


def _write_temp_csv(content: str, suffix: str = ".csv") -> pathlib.Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return pathlib.Path(f.name)


def test_read_csv_basic(reader):
    path = _write_temp_csv("name,age\nAlice,30\nBob,25\n")
    try:
        df = reader.read_file(path)
        assert list(df.columns) == ["name", "age"]
        assert len(df) == 2
        assert df.iloc[0]["name"] == "Alice"
    finally:
        path.unlink(missing_ok=True)


def test_read_csv_trims_column_whitespace(reader):
    path = _write_temp_csv(" name , age \nAlice,30\n")
    try:
        df = reader.read_file(path)
        assert "name" in df.columns
        assert "age" in df.columns
    finally:
        path.unlink(missing_ok=True)


def test_read_unsupported_extension(reader, tmp_path):
    bad_file = tmp_path / "data.json"
    bad_file.write_text("{}")
    with pytest.raises(ValueError, match="Unsupported file type"):
        reader.read_file(bad_file)


def test_read_missing_file(reader, tmp_path):
    with pytest.raises(FileNotFoundError):
        reader.read_file(tmp_path / "does_not_exist.csv")


def test_get_columns(reader):
    path = _write_temp_csv("col_a,col_b,col_c\n1,2,3\n")
    try:
        cols = reader.get_columns(path)
        assert cols == ["col_a", "col_b", "col_c"]
    finally:
        path.unlink(missing_ok=True)

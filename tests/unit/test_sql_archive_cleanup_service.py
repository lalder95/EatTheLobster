from datetime import datetime, timedelta
import os

import pytest

from app.core.sql_archive_cleanup_service import SqlArchiveCleanupService


def _set_modified_at(path, timestamp: datetime) -> None:
    seconds = timestamp.timestamp()
    os.utime(path, (seconds, seconds))


def test_cleanup_deletes_only_expired_sql_files(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    old_sql = archive / "old.sql"
    current_sql = archive / "current.sql"
    old_csv = archive / "old.csv"
    old_sql.write_text("select 1", encoding="utf-8")
    current_sql.write_text("select 2", encoding="utf-8")
    old_csv.write_text("value", encoding="utf-8")

    now = datetime(2026, 8, 15, 12, 0, 0)
    _set_modified_at(old_sql, now - timedelta(days=91))
    _set_modified_at(current_sql, now - timedelta(days=90))
    _set_modified_at(old_csv, now - timedelta(days=100))

    removed = SqlArchiveCleanupService().cleanup(tmp_path, now=now)

    assert removed == [old_sql]
    assert not old_sql.exists()
    assert current_sql.exists()
    assert old_csv.exists()


def test_cleanup_dry_run_preserves_expired_files(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    old_sql = archive / "old.sql"
    old_sql.write_text("select 1", encoding="utf-8")
    now = datetime(2026, 8, 15, 12, 0, 0)
    _set_modified_at(old_sql, now - timedelta(days=91))

    removed = SqlArchiveCleanupService().cleanup(tmp_path, dry_run=True, now=now)

    assert removed == [old_sql]
    assert old_sql.exists()


def test_cleanup_deletes_only_expired_top_level_report_outputs(tmp_path):
    old_csv = tmp_path / "old.csv"
    old_xlsx = tmp_path / "old.xlsx"
    current_csv = tmp_path / "current.csv"
    old_sql = tmp_path / "old.sql"
    nested_dir = tmp_path / "archive"
    nested_dir.mkdir()
    nested_xlsx = nested_dir / "old.xlsx"
    for path in (old_csv, old_xlsx, current_csv, old_sql, nested_xlsx):
        path.write_text("data", encoding="utf-8")

    now = datetime(2026, 8, 15, 12, 0, 0)
    for path in (old_csv, old_xlsx, old_sql, nested_xlsx):
        _set_modified_at(path, now - timedelta(days=91))
    _set_modified_at(current_csv, now - timedelta(days=90))

    removed = SqlArchiveCleanupService().cleanup_report_outputs(tmp_path, now=now)

    assert removed == [old_csv, old_xlsx]
    assert not old_csv.exists()
    assert not old_xlsx.exists()
    assert current_csv.exists()
    assert old_sql.exists()
    assert nested_xlsx.exists()


def test_report_output_cleanup_dry_run_preserves_expired_files(tmp_path):
    old_report = tmp_path / "old.xlsx"
    old_report.write_text("data", encoding="utf-8")
    now = datetime(2026, 8, 15, 12, 0, 0)
    _set_modified_at(old_report, now - timedelta(days=91))

    removed = SqlArchiveCleanupService().cleanup_report_outputs(
        tmp_path,
        dry_run=True,
        now=now,
    )

    assert removed == [old_report]
    assert old_report.exists()


def test_cleanup_ignores_missing_archive_folder(tmp_path):
    assert SqlArchiveCleanupService().cleanup(tmp_path) == []


def test_cleanup_rejects_negative_retention(tmp_path):
    with pytest.raises(ValueError, match="cannot be negative"):
        SqlArchiveCleanupService().cleanup(tmp_path, retention_days=-1)
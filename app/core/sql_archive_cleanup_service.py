from __future__ import annotations

import pathlib
from datetime import datetime, timedelta


class SqlArchiveCleanupService:
    """Removes expired archived SQL files and generated report outputs."""

    def cleanup(
        self,
        query_folder: str | pathlib.Path,
        archive_folder_name: str = "archive",
        retention_days: int = 90,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> list[pathlib.Path]:
        if retention_days < 0:
            raise ValueError("retention_days cannot be negative")

        archive_dir = pathlib.Path(query_folder).expanduser() / archive_folder_name
        if not archive_dir.is_dir():
            return []

        cutoff = (now or datetime.now()) - timedelta(days=retention_days)
        expired_files = sorted(
            path
            for path in archive_dir.glob("*.sql")
            if path.is_file()
            and datetime.fromtimestamp(path.stat().st_mtime) < cutoff
        )

        if not dry_run:
            for path in expired_files:
                path.unlink()

        return expired_files

    def cleanup_report_outputs(
        self,
        query_folder: str | pathlib.Path,
        retention_days: int = 90,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> list[pathlib.Path]:
        """Remove expired SQL, CSV, and XLSX files from the top-level query folder."""
        if retention_days < 0:
            raise ValueError("retention_days cannot be negative")

        query_dir = pathlib.Path(query_folder).expanduser()
        if not query_dir.is_dir():
            return []

        cutoff = (now or datetime.now()) - timedelta(days=retention_days)
        expired_files = sorted(
            path
            for path in query_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".sql", ".csv", ".xlsx"}
            and datetime.fromtimestamp(path.stat().st_mtime) < cutoff
        )

        if not dry_run:
            for path in expired_files:
                path.unlink()

        return expired_files
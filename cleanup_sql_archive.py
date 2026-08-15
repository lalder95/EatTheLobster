from __future__ import annotations

import argparse
import logging
import sys

from app.core.sql_archive_cleanup_service import SqlArchiveCleanupService
from app.data.database import get_session, init_db
from app.data.repositories import QueryAutomationSettingsRepository
from app.logging.log_service import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete expired .sql files from the configured query archive."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Archive retention period in days (default: 90).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be deleted without deleting them.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.days < 0:
        print("Error: --days cannot be negative.", file=sys.stderr)
        return 2

    setup_logging()
    init_db()
    logger = logging.getLogger(__name__)

    session = get_session()
    try:
        settings = QueryAutomationSettingsRepository(session).get()
        if not settings.query_folder_path:
            print("Query folder is not configured; nothing to clean.")
            return 0

        cleanup_service = SqlArchiveCleanupService()
        removed_archived_sql = cleanup_service.cleanup(
            query_folder=settings.query_folder_path,
            archive_folder_name=settings.archive_folder_name or "archive",
            retention_days=args.days,
            dry_run=args.dry_run,
        )
        removed_report_outputs = cleanup_service.cleanup_report_outputs(
            query_folder=settings.query_folder_path,
            retention_days=args.days,
            dry_run=args.dry_run,
        )
    finally:
        session.close()

    removed = [*removed_archived_sql, *removed_report_outputs]
    action = "Would delete" if args.dry_run else "Deleted"
    print(
        f"{action} {len(removed)} expired file(s) older than {args.days} day(s): "
        f"{len(removed_archived_sql)} archived SQL file(s) and "
        f"{len(removed_report_outputs)} CSV/XLSX report file(s)."
    )
    for path in removed:
        print(f" - {path}")
    logger.info(
        "%s %s archived SQL file(s) older than %s day(s).",
        action,
        len(removed),
        args.days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
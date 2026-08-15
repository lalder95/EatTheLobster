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

        removed = SqlArchiveCleanupService().cleanup(
            query_folder=settings.query_folder_path,
            archive_folder_name=settings.archive_folder_name or "archive",
            retention_days=args.days,
            dry_run=args.dry_run,
        )
    finally:
        session.close()

    action = "Would delete" if args.dry_run else "Deleted"
    print(f"{action} {len(removed)} archived SQL file(s) older than {args.days} day(s).")
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
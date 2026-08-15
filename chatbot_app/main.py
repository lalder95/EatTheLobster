from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from app.core.sql_archive_cleanup_service import SqlArchiveCleanupService
from app.data.database import get_session as get_query_automation_session
from app.data.database import init_db as init_query_automation_db
from app.data.repositories import QueryAutomationSettingsRepository
from chatbot_app.data.database import init_db
from chatbot_app.logging_service import setup_logging
from chatbot_app.ui.main_window import MainWindow


logger = logging.getLogger(__name__)


def cleanup_sql_archive_on_startup() -> int:
    """Remove expired processed SQL files without preventing chatbot startup."""
    try:
        init_query_automation_db()
        session = get_query_automation_session()
        try:
            settings = QueryAutomationSettingsRepository(session).get()
            if not settings.query_folder_path:
                logger.info("SQL archive cleanup skipped; query folder is not configured.")
                return 0

            cleanup_service = SqlArchiveCleanupService()
            removed_archived_sql = cleanup_service.cleanup(
                query_folder=settings.query_folder_path,
                archive_folder_name=settings.archive_folder_name or "archive",
                retention_days=90,
            )
            removed_report_outputs = cleanup_service.cleanup_report_outputs(
                query_folder=settings.query_folder_path,
                retention_days=90,
            )
        finally:
            session.close()

        removed_count = len(removed_archived_sql) + len(removed_report_outputs)
        logger.info(
            "Deleted %s expired file(s) on chatbot startup: %s archived SQL file(s), %s primary SQL/CSV/XLSX file(s).",
            removed_count,
            len(removed_archived_sql),
            len(removed_report_outputs),
        )
        return removed_count
    except Exception:
        logger.exception("SQL archive cleanup failed during chatbot startup.")
        return 0


def main() -> None:
    setup_logging()
    init_db()
    cleanup_sql_archive_on_startup()

    app = QApplication(sys.argv)
    app.setApplicationName("ETL Importer SQL Chatbot")
    app.setOrganizationName("ETLImporter")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

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

            removed = SqlArchiveCleanupService().cleanup(
                query_folder=settings.query_folder_path,
                archive_folder_name=settings.archive_folder_name or "archive",
                retention_days=90,
            )
        finally:
            session.close()

        logger.info("Deleted %s expired archived SQL file(s) on chatbot startup.", len(removed))
        return len(removed)
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

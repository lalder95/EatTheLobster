from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from chatbot_app.data.database import init_db
from chatbot_app.logging_service import setup_logging
from chatbot_app.ui.main_window import MainWindow


def main() -> None:
    setup_logging()
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("ETL Importer SQL Chatbot")
    app.setOrganizationName("ETLImporter")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

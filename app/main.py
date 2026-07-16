import sys

from PySide6.QtWidgets import QApplication

from app.logging.log_service import setup_logging
from app.data.database import init_db
from app.scheduler.scheduler_service import SchedulerService
from app.ui.main_window import MainWindow


def main() -> None:
    setup_logging()

    # Initialise internal metadata database (SQLite in AppData)
    init_db()

    # Start the background scheduler; it will reload all enabled jobs
    scheduler = SchedulerService.get_instance()
    scheduler.start()

    # Launch the Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("ETL Importer")
    app.setOrganizationName("ETLImporter")

    window = MainWindow()
    window.show()

    exit_code = app.exec()

    # Graceful shutdown
    scheduler.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

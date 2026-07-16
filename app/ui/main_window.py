import logging

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_SIDEBAR_STYLE = """
QWidget#Sidebar {
    background: #1e1e1e;
}
QPushButton.nav {
    text-align: left;
    padding: 10px 20px;
    border: none;
    background: transparent;
    font-size: 14px;
    color: #cccccc;
    border-radius: 0;
}
QPushButton.nav:hover {
    background: #2d2d2d;
    color: #ffffff;
}
QPushButton.nav:checked {
    background: #0078d4;
    color: #ffffff;
    font-weight: bold;
}
"""

_APP_STYLE = """
QMainWindow, QWidget {
    background: #2b2b2b;
    color: #dddddd;
    font-size: 13px;
}
QTableWidget {
    background: #1e1e1e;
    alternate-background-color: #252525;
    gridline-color: #3a3a3a;
    border: 1px solid #3a3a3a;
}
QTableWidget::item:selected {
    background: #0078d4;
}
QHeaderView::section {
    background: #252525;
    color: #aaaaaa;
    border: none;
    border-bottom: 1px solid #3a3a3a;
    padding: 6px;
}
QLineEdit, QComboBox, QSpinBox, QTimeEdit {
    background: #1e1e1e;
    color: #dddddd;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 26px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus {
    border: 1px solid #0078d4;
}
QPushButton {
    background: #3a3a3a;
    color: #dddddd;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 26px;
}
QPushButton:hover {
    background: #4a4a4a;
}
QPushButton:pressed {
    background: #2a2a2a;
}
QPushButton#primary {
    background: #0078d4;
    border: none;
    color: white;
}
QPushButton#primary:hover {
    background: #1084d8;
}
QPushButton#danger {
    background: #c0392b;
    border: none;
    color: white;
}
QPushButton#danger:hover {
    background: #e74c3c;
}
QGroupBox {
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    margin-top: 14px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #aaaaaa;
}
QCheckBox {
    color: #dddddd;
}
QRadioButton {
    color: #dddddd;
}
QScrollBar:vertical {
    width: 10px;
    background: #1e1e1e;
}
QScrollBar::handle:vertical {
    background: #4a4a4a;
    border-radius: 4px;
}
"""


class _NavButton(QPushButton):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setProperty("class", "nav")
        self.setMinimumHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class _RunJobThread(QThread):
    finished = Signal(int)  # job_id

    def __init__(self, job_id: int, parent=None) -> None:
        super().__init__(parent)
        self._job_id = job_id

    def run(self) -> None:
        from app.scheduler.scheduler_service import SchedulerService

        SchedulerService.get_instance().trigger_now(self._job_id)
        self.finished.emit(self._job_id)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ETL Importer")
        self.resize(1280, 780)
        self.setStyleSheet(_APP_STYLE)
        self._threads: list = []
        self._setup_ui()
        self._start_status_timer()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        sidebar = self._build_sidebar()
        content.addWidget(sidebar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3a3a3a;")
        content.addWidget(sep)

        self._stack = QStackedWidget()
        content.addWidget(self._stack, stretch=1)

        root.addLayout(content, stretch=1)
        root.addWidget(self._build_status_bar())

        # Lazy-import pages to avoid circular imports at module load time
        from app.ui.pages.jobs_page import JobsPage
        from app.ui.pages.logs_page import LogsPage
        from app.ui.pages.config_page import ConfigPage

        self._jobs_page = JobsPage(self)
        self._logs_page = LogsPage(self)
        self._config_page = ConfigPage(self)

        self._stack.addWidget(self._jobs_page)   # index 0
        self._stack.addWidget(self._logs_page)   # index 1
        self._stack.addWidget(self._config_page) # index 2

        self._nav_buttons[0].setChecked(True)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(_SIDEBAR_STYLE)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(0)

        title = QLabel("ETL Importer")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(
            "color: white; padding: 20px 0 16px 0; background: #1e1e1e;"
        )
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333333; background: #333333; max-height: 1px;")
        layout.addWidget(sep)
        layout.addSpacing(8)

        self._nav_buttons: list[_NavButton] = []
        nav_items = [("  Jobs", 0), ("  Logs", 1), ("  Settings", 2)]
        for label, index in nav_items:
            btn = _NavButton(label)
            btn.clicked.connect(
                lambda _checked, i=index, b=btn: self._navigate(i, b)
            )
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()
        return sidebar

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet(
            "QWidget { background: #1a1a1a; border-top: 1px solid #3a3a3a; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)

        self._scheduler_label = QLabel("Scheduler: Starting…")
        self._scheduler_label.setStyleSheet("font-size: 12px; color: #888888;")
        layout.addWidget(self._scheduler_label)
        layout.addStretch()
        return bar

    def _navigate(self, index: int, clicked_btn: _NavButton) -> None:
        for btn in self._nav_buttons:
            btn.setChecked(False)
        clicked_btn.setChecked(True)
        self._stack.setCurrentIndex(index)
        if index == 0:
            self._jobs_page.refresh()
        elif index == 1:
            self._logs_page.refresh()

    def _start_status_timer(self) -> None:
        timer = QTimer(self)
        timer.timeout.connect(self._update_status)
        timer.start(5000)
        self._update_status()

    def _update_status(self) -> None:
        from app.scheduler.scheduler_service import SchedulerService

        svc = SchedulerService.get_instance()
        if svc.is_running:
            self._scheduler_label.setText("Scheduler: Running")
            self._scheduler_label.setStyleSheet(
                "font-size: 12px; color: #4caf50;"
            )
        else:
            self._scheduler_label.setText("Scheduler: Stopped")
            self._scheduler_label.setStyleSheet(
                "font-size: 12px; color: #f44336;"
            )

    def refresh_jobs(self) -> None:
        self._jobs_page.refresh()

    def navigate_to_logs(self) -> None:
        self._navigate(1, self._nav_buttons[1])

    def run_job_async(self, job_id: int) -> None:
        thread = _RunJobThread(job_id, self)
        thread.finished.connect(lambda _jid: self._jobs_page.refresh())
        self._threads.append(thread)
        thread.start()

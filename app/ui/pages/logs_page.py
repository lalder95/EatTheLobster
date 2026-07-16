import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    "success": "#4caf50",
    "partial": "#ff9800",
    "failed": "#f44336",
    "running": "#2196f3",
    "cancelled": "#9e9e9e",
}


class LogsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(5000)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("Import Logs")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # Filters
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Job:"))
        self._job_filter = QComboBox()
        self._job_filter.setMinimumWidth(200)
        self._job_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._job_filter)

        filter_row.addSpacing(16)
        filter_row.addWidget(QLabel("Status:"))
        self._status_filter = QComboBox()
        self._status_filter.addItems([
            "All", "success", "partial", "failed", "running", "cancelled"
        ])
        self._status_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._status_filter)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Splitter: runs table (top) + error detail (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Runs table
        self._runs_table = QTableWidget()
        self._runs_table.setColumnCount(8)
        self._runs_table.setHorizontalHeaderLabels([
            "Job", "Started", "Completed", "Status",
            "Trigger", "Files", "Rows", "Skipped",
        ])
        self._runs_table.setAlternatingRowColors(True)
        self._runs_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._runs_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._runs_table.verticalHeader().setVisible(False)
        hdr = self._runs_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self._runs_table.itemSelectionChanged.connect(self._on_run_selected)
        splitter.addWidget(self._runs_table)

        # Error detail panel
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(4)
        detail_label = QLabel("Error Details")
        detail_label.setStyleSheet("font-weight: bold; color: #aaaaaa;")
        detail_layout.addWidget(detail_label)
        self._error_text = QTextEdit()
        self._error_text.setReadOnly(True)
        self._error_text.setStyleSheet(
            "background: #1a1a1a; color: #dddddd; "
            "border: 1px solid #3a3a3a; font-family: Consolas, monospace;"
        )
        self._error_text.setPlaceholderText(
            "Select a run to view error details…"
        )
        detail_layout.addWidget(self._error_text)
        splitter.addWidget(detail_widget)

        splitter.setSizes([500, 200])
        layout.addWidget(splitter, stretch=1)

        # Cache for run->errors lookup
        self._run_id_map: dict = {}

    def refresh(self) -> None:
        self._load_job_filter()
        self._apply_filter()

    def _load_job_filter(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import ImportJobRepository

        session = get_session()
        try:
            jobs = ImportJobRepository(session).get_all()
            self._job_filter.blockSignals(True)
            current_id = self._job_filter.currentData()
            self._job_filter.clear()
            self._job_filter.addItem("All Jobs", userData=None)
            for j in jobs:
                self._job_filter.addItem(j.name, userData=j.id)
            # Restore selection
            for i in range(self._job_filter.count()):
                if self._job_filter.itemData(i) == current_id:
                    self._job_filter.setCurrentIndex(i)
                    break
            self._job_filter.blockSignals(False)
        finally:
            session.close()

    def _apply_filter(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import ImportRunRepository

        job_id = self._job_filter.currentData()
        status_filter = self._status_filter.currentText()

        session = get_session()
        try:
            runs = ImportRunRepository(session).get_recent(
                limit=500, job_id=job_id
            )
        finally:
            session.close()

        if status_filter != "All":
            runs = [r for r in runs if r.status == status_filter]

        self._run_id_map = {r.id: r for r in runs}
        self._runs_table.setRowCount(0)

        for run in runs:
            row = self._runs_table.rowCount()
            self._runs_table.insertRow(row)

            job_name = run.job.name if run.job else f"Job #{run.job_id}"
            started = run.started_at.strftime("%Y-%m-%d %H:%M:%S")
            completed = (
                run.completed_at.strftime("%Y-%m-%d %H:%M:%S")
                if run.completed_at
                else "—"
            )

            values = [
                job_name,
                started,
                completed,
                run.status,
                run.trigger_type,
                str(run.files_processed),
                str(run.rows_imported),
                str(run.rows_skipped),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, run.id)
                if col == 3 and run.status in _STATUS_COLORS:
                    item.setForeground(
                        QColor(_STATUS_COLORS[run.status])
                    )
                self._runs_table.setItem(row, col, item)

    def _on_run_selected(self) -> None:
        selected = self._runs_table.selectedItems()
        if not selected:
            self._error_text.clear()
            return

        run_id = selected[0].data(Qt.ItemDataRole.UserRole)
        if run_id is None:
            return

        from app.data.database import get_session
        from app.data.repositories import ImportErrorRepository

        session = get_session()
        try:
            errors = ImportErrorRepository(session).get_by_run(run_id)
        finally:
            session.close()

        if not errors:
            self._error_text.setPlainText("No errors for this run.")
            return

        lines = []
        for e in errors:
            lines.append(f"[{e.occurred_at.strftime('%H:%M:%S')}] {e.error_type}")
            if e.file_path:
                lines.append(f"  File: {e.file_path}")
            lines.append(f"  {e.error_message}")
            lines.append("")
        self._error_text.setPlainText("\n".join(lines))

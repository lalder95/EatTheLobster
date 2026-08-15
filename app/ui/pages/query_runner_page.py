from __future__ import annotations

import logging
import pathlib
import threading

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    "success": "#4caf50",
    "failed": "#f44336",
    "running": "#2196f3",
}


class QueryRunnerPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(5000)
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Query Automation")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self._service_status = QLabel("")
        self._service_status.setStyleSheet("font-size: 12px; color: #aaaaaa;")
        header.addWidget(self._service_status)
        layout.addLayout(header)

        subtitle = QLabel(
            "Watch a folder for .sql files, run each query against the selected database, and write the results back into the same folder."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(subtitle)

        config_box = QGroupBox("Automation Settings")
        config_layout = QVBoxLayout(config_box)

        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("\\\\network-share\\queries or C:/queries")
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self._folder_edit, stretch=1)
        folder_row.addWidget(browse_btn)
        config_layout.addWidget(QLabel("Query Folder *"))
        config_layout.addLayout(folder_row)

        conn_row = QHBoxLayout()
        self._conn_combo = QComboBox()
        self._conn_combo.setMinimumWidth(280)
        conn_refresh_btn = QPushButton("↺")
        conn_refresh_btn.setFixedWidth(32)
        conn_refresh_btn.clicked.connect(self._load_connections)
        conn_row.addWidget(self._conn_combo, stretch=1)
        conn_row.addWidget(conn_refresh_btn)
        config_layout.addWidget(QLabel("Default Database Connection *"))
        config_layout.addLayout(conn_row)

        self._enabled_chk = QCheckBox("Enable automatic scanning")
        self._enabled_chk.setChecked(True)
        config_layout.addWidget(self._enabled_chk)

        cadence = QLabel("Scan cadence: every 30 seconds")
        cadence.setStyleSheet("color: #888888; font-size: 12px;")
        config_layout.addWidget(cadence)

        button_row = QHBoxLayout()
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 12px;")
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_settings)
        scan_btn = QPushButton("Scan Now")
        scan_btn.clicked.connect(self._scan_now)
        button_row.addWidget(save_btn)
        button_row.addWidget(scan_btn)
        button_row.addWidget(self._status_label, stretch=1)
        config_layout.addLayout(button_row)

        layout.addWidget(config_box)

        runs_box = QGroupBox("Recent Query Runs")
        runs_layout = QVBoxLayout(runs_box)
        self._runs_table = QTableWidget(0, 7)
        self._runs_table.setHorizontalHeaderLabels(
            ["File", "Started", "Completed", "Status", "Rows", "Output", "Archive"]
        )
        self._runs_table.setAlternatingRowColors(True)
        self._runs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._runs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._runs_table.verticalHeader().setVisible(False)
        hdr = self._runs_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        runs_layout.addWidget(self._runs_table)

        self._error_text = QTextEdit()
        self._error_text.setReadOnly(True)
        self._error_text.setPlaceholderText("Select a failed run to view details…")
        self._error_text.setStyleSheet(
            "background: #1a1a1a; color: #dddddd; border: 1px solid #3a3a3a; font-family: Consolas, monospace;"
        )
        self._runs_table.itemSelectionChanged.connect(self._on_run_selected)
        runs_layout.addWidget(self._error_text)
        layout.addWidget(runs_box, stretch=1)

    def refresh(self) -> None:
        self._load_settings()
        self._load_runs()
        from app.core.query_automation_service import QueryAutomationService

        service = QueryAutomationService.get_instance()
        if service.is_running:
            self._service_status.setText("Service: Running")
            self._service_status.setStyleSheet("font-size: 12px; color: #4caf50;")
        else:
            self._service_status.setText("Service: Stopped")
            self._service_status.setStyleSheet("font-size: 12px; color: #f44336;")

    def _load_connections(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import DbConnectionRepository

        current_id = self._conn_combo.currentData()
        session = get_session()
        try:
            connections = DbConnectionRepository(session).get_all()
        finally:
            session.close()

        self._conn_combo.blockSignals(True)
        self._conn_combo.clear()
        for conn in connections:
            self._conn_combo.addItem(
                f"{conn.name} ({conn.database_name})",
                userData=conn.id,
            )

        if self._conn_combo.count() == 0:
            self._conn_combo.addItem("No connections available", userData=None)

        for index in range(self._conn_combo.count()):
            if self._conn_combo.itemData(index) == current_id:
                self._conn_combo.setCurrentIndex(index)
                break
        self._conn_combo.blockSignals(False)

    def _load_settings(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import QueryAutomationSettingsRepository

        session = get_session()
        try:
            settings = QueryAutomationSettingsRepository(session).get()
        finally:
            session.close()

        self._folder_edit.setText(settings.query_folder_path or "")
        self._enabled_chk.setChecked(bool(settings.enabled))
        self._load_connections()
        for index in range(self._conn_combo.count()):
            if self._conn_combo.itemData(index) == settings.default_db_connection_id:
                self._conn_combo.setCurrentIndex(index)
                break

    def _load_runs(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import QueryRunRepository

        session = get_session()
        try:
            runs = QueryRunRepository(session).get_recent(limit=50)
        finally:
            session.close()

        self._runs_table.setRowCount(0)
        self._error_text.clear()
        for run in runs:
            row = self._runs_table.rowCount()
            self._runs_table.insertRow(row)

            started = run.started_at.strftime("%Y-%m-%d %H:%M:%S")
            completed = run.completed_at.strftime("%Y-%m-%d %H:%M:%S") if run.completed_at else "—"
            values = [
                pathlib.Path(run.query_file_path).name,
                started,
                completed,
                run.status,
                str(run.row_count),
                run.output_file_path or "—",
                run.archived_file_path or "—",
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, run.id)
                if col == 3 and run.status in _STATUS_COLORS:
                    item.setForeground(Qt.GlobalColor.white)
                    item.setBackground(Qt.GlobalColor.transparent)
                    item.setForeground(
                        __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(
                            _STATUS_COLORS[run.status]
                        )
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
        from app.data.repositories import QueryRunRepository

        session = get_session()
        try:
            runs = QueryRunRepository(session).get_recent(limit=500)
        finally:
            session.close()

        for run in runs:
            if run.id == run_id:
                if run.error_message:
                    self._error_text.setPlainText(run.error_message)
                else:
                    self._error_text.setPlainText("No error details for this run.")
                return

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Query Folder")
        if folder:
            self._folder_edit.setText(folder)

    def _save_settings(self) -> None:
        folder = self._folder_edit.text().strip()
        conn_id = self._conn_combo.currentData()

        if not folder:
            QMessageBox.warning(self, "Validation", "Query Folder is required.")
            return
        if conn_id is None:
            QMessageBox.warning(
                self,
                "Validation",
                "Please select a database connection first.",
            )
            return

        from app.data.database import get_session
        from app.data.repositories import QueryAutomationSettingsRepository

        session = get_session()
        try:
            repo = QueryAutomationSettingsRepository(session)
            repo.save(
                query_folder_path=folder,
                default_db_connection_id=conn_id,
                enabled=self._enabled_chk.isChecked(),
            )
        finally:
            session.close()

        self._status_label.setText("Saved")
        self._status_label.setStyleSheet("font-size: 12px; color: #4caf50;")
        self.refresh()

    def _scan_now(self) -> None:
        self._status_label.setText("Scan requested")
        self._status_label.setStyleSheet("font-size: 12px; color: #aaaaaa;")

        from app.core.query_automation_service import QueryAutomationService

        threading.Thread(
            target=QueryAutomationService.get_instance().scan_now,
            daemon=True,
        ).start()

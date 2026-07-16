import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


def _format_frequency(job) -> str:
    try:
        cfg = job.frequency_config_dict
        if job.frequency_type == "interval":
            mins = int(cfg.get("minutes", 0))
            if mins >= 60 and mins % 60 == 0:
                h = mins // 60
                return f"Every {h} hour{'s' if h != 1 else ''}"
            return f"Every {mins} min{'s' if mins != 1 else ''}"
        if job.frequency_type == "daily":
            return f"Daily at {cfg.get('time', '?')}"
        if job.frequency_type == "weekly":
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            day = days[int(cfg.get("weekday", 0))]
            return f"Weekly {day} at {cfg.get('time', '?')}"
    except Exception:
        pass
    return "—"


_STATUS_COLORS = {
    "success": "#4caf50",
    "partial": "#ff9800",
    "failed": "#f44336",
    "running": "#2196f3",
    "cancelled": "#9e9e9e",
}


class JobsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._main_win = parent
        self._setup_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(3000)
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Import Jobs")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        new_btn = QPushButton("+ New Job")
        new_btn.setObjectName("primary")
        new_btn.setFixedWidth(110)
        new_btn.clicked.connect(self._new_job)
        toolbar.addWidget(new_btn)
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "Name", "Type", "Source", "Target Table",
            "Frequency", "Last Run", "Status", "Next Run", "Actions",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(8, 292)

        layout.addWidget(self._table, stretch=1)

        self._empty_label = QLabel(
            "No jobs yet. Click '+ New Job' to create one."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #666666; font-size: 14px;")
        layout.addWidget(self._empty_label)
        self._empty_label.hide()

    def refresh(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import ImportJobRepository, ImportRunRepository
        from app.scheduler.scheduler_service import SchedulerService

        session = get_session()
        try:
            jobs = ImportJobRepository(session).get_all()
            run_repo = ImportRunRepository(session)
            svc = SchedulerService.get_instance()

            self._table.setRowCount(0)
            self._table.setVisible(bool(jobs))
            self._empty_label.setVisible(not jobs)

            for job in jobs:
                row = self._table.rowCount()
                self._table.insertRow(row)
                is_running = svc.is_job_running(job.id)

                last_run = run_repo.get_last_run(job.id)
                last_run_str = (
                    last_run.started_at.strftime("%Y-%m-%d %H:%M")
                    if last_run
                    else "Never"
                )
                last_status = "running" if is_running else (last_run.status if last_run else "—")
                next_run = svc.get_next_run_time(job.id)
                next_run_str = (
                    next_run.strftime("%Y-%m-%d %H:%M") if next_run else "—"
                )
                if not job.enabled:
                    next_run_str = "Disabled"
                elif is_running:
                    next_run_str = "In progress"

                cells = [
                    job.name,
                    job.source_type.capitalize(),
                    job.source_path,
                    job.target_table,
                    _format_frequency(job),
                    last_run_str,
                    last_status,
                    next_run_str,
                ]
                for col, text in enumerate(cells):
                    item = QTableWidgetItem(str(text))
                    item.setFlags(
                        item.flags() & ~Qt.ItemFlag.ItemIsEditable
                    )
                    if col == 6 and last_status in _STATUS_COLORS:
                        item.setForeground(
                            Qt.GlobalColor.white
                        )
                        item.setBackground(
                            Qt.GlobalColor.transparent
                        )
                        item.setForeground(
                            __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(
                                _STATUS_COLORS[last_status]
                            )
                        )
                    self._table.setItem(row, col, item)

                self._table.setCellWidget(
                    row, 8, self._make_actions(job, is_running)
                )

        finally:
            session.close()

    def _make_actions(self, job, is_running: bool) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        compact_style = (
            "QPushButton {"
            "padding: 2px 6px;"
            "min-height: 22px;"
            "font-size: 12px;"
            "}"
        )

        run_btn = QPushButton("Stop" if is_running else "Run")
        run_btn.setFixedWidth(44)
        if is_running:
            run_btn.setObjectName("danger")
        else:
            run_btn.setObjectName("primary")
        run_btn.setStyleSheet(compact_style)
        run_btn.setToolTip("Stop running job" if is_running else "Run now")
        if is_running:
            run_btn.clicked.connect(lambda: self._stop_job(job.id))
        else:
            run_btn.clicked.connect(lambda: self._run_now(job.id))

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedWidth(40)
        edit_btn.setStyleSheet(compact_style)
        edit_btn.setEnabled(not is_running)
        edit_btn.clicked.connect(lambda: self._edit_job(job.id))

        reset_btn = QPushButton("Reset")
        reset_btn.setFixedWidth(48)
        reset_btn.setStyleSheet(compact_style)
        reset_btn.setEnabled(not is_running)
        reset_btn.setToolTip("Purge target table and reimport all source files")
        reset_btn.clicked.connect(lambda: self._reset_job(job.id, job.name))

        toggle_label = "Disable" if job.enabled else "Enable"
        toggle_btn = QPushButton(toggle_label)
        toggle_btn.setFixedWidth(52)
        toggle_btn.setStyleSheet(compact_style)
        toggle_btn.setEnabled(not is_running)
        toggle_btn.clicked.connect(
            lambda: self._toggle_job(job.id, job.enabled)
        )

        del_btn = QPushButton("Delete")
        del_btn.setFixedWidth(48)
        del_btn.setObjectName("danger")
        del_btn.setStyleSheet(compact_style)
        del_btn.setEnabled(not is_running)
        del_btn.clicked.connect(lambda: self._delete_job(job.id, job.name))

        layout.addWidget(run_btn)
        layout.addWidget(edit_btn)
        layout.addWidget(reset_btn)
        layout.addWidget(toggle_btn)
        layout.addWidget(del_btn)
        return widget

    def _new_job(self) -> None:
        from app.ui.pages.job_editor_page import JobEditorDialog

        dlg = JobEditorDialog(parent=self)
        if dlg.exec():
            self.refresh()

    def _edit_job(self, job_id: int) -> None:
        from app.ui.pages.job_editor_page import JobEditorDialog

        dlg = JobEditorDialog(job_id=job_id, parent=self)
        if dlg.exec():
            self.refresh()

    def _run_now(self, job_id: int) -> None:
        from app.scheduler.scheduler_service import SchedulerService

        if SchedulerService.get_instance().is_job_running(job_id):
            QMessageBox.information(
                self,
                "Already Running",
                "This job is already running.",
            )
            return

        if self._main_win:
            self._main_win.run_job_async(job_id)
        else:
            SchedulerService.get_instance().trigger_now(job_id)
        QMessageBox.information(
            self,
            "Run Started",
            "The job has been queued. Check the Logs page for results.",
        )
        self.refresh()

    def _reset_job(self, job_id: int, job_name: str) -> None:
        from app.scheduler.scheduler_service import SchedulerService

        reply = QMessageBox.question(
            self,
            "Purge And Reimport",
            f"Purge the target table and reimport all files for '{job_name}'?\n\n"
            "This clears the job's imported-file history and reloads from the source.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if SchedulerService.get_instance().is_job_running(job_id):
            QMessageBox.information(
                self,
                "Already Running",
                "This job is already running.",
            )
            return

        if self._main_win:
            self._main_win.run_job_async(job_id, force_full_refresh=True)
        else:
            SchedulerService.get_instance().trigger_now(
                job_id,
                force_full_refresh=True,
            )
        QMessageBox.information(
            self,
            "Reimport Started",
            "The table purge and reimport has started. Check the Logs page for results.",
        )
        self.refresh()

    def _stop_job(self, job_id: int) -> None:
        from app.scheduler.scheduler_service import SchedulerService

        if SchedulerService.get_instance().request_stop(job_id):
            QMessageBox.information(
                self,
                "Stop Requested",
                "The job will stop after the current step completes.",
            )
        else:
            QMessageBox.information(
                self,
                "Not Running",
                "That job is not currently running.",
            )
        self.refresh()

    def _toggle_job(self, job_id: int, currently_enabled: bool) -> None:
        from app.data.database import get_session
        from app.data.repositories import ImportJobRepository
        from app.scheduler.scheduler_service import SchedulerService

        session = get_session()
        try:
            repo = ImportJobRepository(session)
            job = repo.get_by_id(job_id)
            if job:
                job.enabled = not currently_enabled
                repo.update(job)
                SchedulerService.get_instance().schedule_job(job)
        finally:
            session.close()
        self.refresh()

    def _delete_job(self, job_id: int, job_name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Job",
            f"Delete job '{job_name}'? This also removes all run history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from app.data.database import get_session
        from app.data.repositories import ImportJobRepository
        from app.scheduler.scheduler_service import SchedulerService

        session = get_session()
        try:
            ImportJobRepository(session).delete(job_id)
            SchedulerService.get_instance().unschedule_job(job_id)
        finally:
            session.close()
        self.refresh()

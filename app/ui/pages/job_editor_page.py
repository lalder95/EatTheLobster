import json
import logging
import pathlib
import re
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QTime

logger = logging.getLogger(__name__)
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


class JobEditorDialog(QDialog):
    def __init__(self, job_id: Optional[int] = None, parent=None) -> None:
        super().__init__(parent)
        self._job_id = job_id
        self._is_edit = job_id is not None
        self.setWindowTitle("Edit Job" if self._is_edit else "New Job")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._setup_ui()
        if self._is_edit:
            self._load_job()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── General ──────────────────────────────────────────────────────────
        gen_box = QGroupBox("General")
        gen_form = QFormLayout(gen_box)
        gen_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("My Import Job")
        gen_form.addRow("Job Name *", self._name_edit)

        self._job_type_combo = QComboBox()
        self._job_type_combo.addItem("Import Job", userData="import")
        self._job_type_combo.addItem(
            "Schema Export Job", userData="schema_export"
        )
        self._job_type_combo.currentIndexChanged.connect(
            self._sync_job_mode_ui
        )
        gen_form.addRow("Job Type *", self._job_type_combo)

        # Source type
        type_row = QHBoxLayout()
        self._radio_file = QRadioButton("Single File")
        self._radio_dir = QRadioButton("Directory")
        self._radio_file.setChecked(True)
        self._radio_file.toggled.connect(self._on_source_type_changed)
        type_row.addWidget(self._radio_file)
        type_row.addWidget(self._radio_dir)
        type_row.addStretch()
        gen_form.addRow("Source Type *", type_row)

        # Source path
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select a file or directory…")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.setFixedWidth(80)
        self._browse_btn.clicked.connect(self._browse_source)
        path_row.addWidget(self._path_edit, stretch=1)
        path_row.addWidget(self._browse_btn)
        gen_form.addRow("Source Path *", path_row)

        export_row = QHBoxLayout()
        self._export_path_edit = QLineEdit()
        self._export_path_edit.setPlaceholderText("C:/exports/schema.json")
        self._export_browse_btn = QPushButton("Browse…")
        self._export_browse_btn.setFixedWidth(80)
        self._export_browse_btn.clicked.connect(self._browse_export_output)
        export_row.addWidget(self._export_path_edit, stretch=1)
        export_row.addWidget(self._export_browse_btn)
        gen_form.addRow("Export File *", export_row)

        self._export_format_combo = QComboBox()
        self._export_format_combo.addItem("JSON", userData="json")
        gen_form.addRow("Export Format *", self._export_format_combo)

        # Connection
        conn_row = QHBoxLayout()
        self._conn_combo = QComboBox()
        self._conn_combo.setMinimumWidth(200)
        self._refresh_connections()
        refresh_conn_btn = QPushButton("↺")
        refresh_conn_btn.setFixedWidth(32)
        refresh_conn_btn.setToolTip("Reload connections")
        refresh_conn_btn.clicked.connect(self._refresh_connections)
        conn_row.addWidget(self._conn_combo, stretch=1)
        conn_row.addWidget(refresh_conn_btn)
        gen_form.addRow("DB Connection *", conn_row)

        self._table_edit = QLineEdit()
        self._table_edit.setPlaceholderText("target_table_name")
        table_row = QHBoxLayout()
        table_row.addWidget(self._table_edit, stretch=1)
        self._create_table_btn = QPushButton("Create From File Template")
        self._create_table_btn.clicked.connect(self._create_table_from_template)
        table_row.addWidget(self._create_table_btn)
        gen_form.addRow("Target Table *", table_row)

        layout.addWidget(gen_box)

        # ── Schedule ─────────────────────────────────────────────────────────
        sched_box = QGroupBox("Schedule")
        sched_layout = QVBoxLayout(sched_box)

        freq_row = QHBoxLayout()
        freq_row.addWidget(QLabel("Frequency:"))
        self._freq_combo = QComboBox()
        self._freq_combo.addItems([
            "Every X minutes/hours",
            "Daily at time",
            "Weekly at time",
        ])
        self._freq_combo.currentIndexChanged.connect(
            self._on_freq_changed
        )
        freq_row.addWidget(self._freq_combo)
        freq_row.addStretch()
        sched_layout.addLayout(freq_row)

        self._freq_stack = QStackedWidget()

        # Page 0: interval
        interval_page = QWidget()
        iv = QHBoxLayout(interval_page)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.addWidget(QLabel("Every"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 1440)
        self._interval_spin.setValue(60)
        self._interval_spin.setFixedWidth(80)
        iv.addWidget(self._interval_spin)
        iv.addWidget(QLabel("minute(s)"))
        iv.addStretch()
        self._freq_stack.addWidget(interval_page)

        # Page 1: daily
        daily_page = QWidget()
        dv = QHBoxLayout(daily_page)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.addWidget(QLabel("At"))
        self._daily_time = QTimeEdit()
        self._daily_time.setDisplayFormat("HH:mm")
        self._daily_time.setFixedWidth(80)
        dv.addWidget(self._daily_time)
        dv.addStretch()
        self._freq_stack.addWidget(daily_page)

        # Page 2: weekly
        weekly_page = QWidget()
        wv = QHBoxLayout(weekly_page)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.addWidget(QLabel("Every"))
        self._weekday_combo = QComboBox()
        self._weekday_combo.addItems([
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ])
        wv.addWidget(self._weekday_combo)
        wv.addWidget(QLabel("at"))
        self._weekly_time = QTimeEdit()
        self._weekly_time.setDisplayFormat("HH:mm")
        self._weekly_time.setFixedWidth(80)
        wv.addWidget(self._weekly_time)
        wv.addStretch()
        self._freq_stack.addWidget(weekly_page)

        sched_layout.addWidget(self._freq_stack)
        layout.addWidget(sched_box)

        # ── Import Options ────────────────────────────────────────────────────
        opts_box = QGroupBox("Import Options")
        opts_layout = QVBoxLayout(opts_box)

        mode_row = QHBoxLayout()
        self._radio_append = QRadioButton("Append rows")
        self._radio_overwrite = QRadioButton("Overwrite (truncate table first)")
        self._radio_append.setChecked(True)
        mode_row.addWidget(self._radio_append)
        mode_row.addWidget(self._radio_overwrite)
        mode_row.addStretch()
        opts_layout.addLayout(mode_row)

        # File-created-date
        date_row = QHBoxLayout()
        self._date_chk = QCheckBox("Stamp rows with file-created date in column:")
        self._date_col_edit = QLineEdit()
        self._date_col_edit.setPlaceholderText("imported_at")
        self._date_col_edit.setFixedWidth(160)
        self._date_col_edit.setEnabled(False)
        self._date_chk.toggled.connect(self._date_col_edit.setEnabled)
        date_row.addWidget(self._date_chk)
        date_row.addWidget(self._date_col_edit)
        date_row.addStretch()
        opts_layout.addLayout(date_row)

        # Ignore previously imported
        self._ignore_chk = QCheckBox(
            "Ignore previously imported files (directory jobs only)"
        )
        self._ignore_chk.setChecked(True)
        opts_layout.addWidget(self._ignore_chk)

        # Enabled
        self._enabled_chk = QCheckBox("Job enabled")
        self._enabled_chk.setChecked(True)
        opts_layout.addWidget(self._enabled_chk)

        layout.addWidget(opts_box)

        self._export_group = QGroupBox("Schema Export")
        export_layout = QVBoxLayout(self._export_group)
        export_note = QLabel(
            "Export the connected database schema as tables and foreign-key relationships."
        )
        export_note.setWordWrap(True)
        export_note.setStyleSheet("color: #888888;")
        export_layout.addWidget(export_note)
        layout.addWidget(self._export_group)

        # ── Column Mappings ──────────────────────────────────────────────────
        map_box = QGroupBox("Column Mappings")
        map_layout = QHBoxLayout(map_box)
        map_info = QLabel(
            "Define which source columns map to target columns. "
            "Leave empty to import all columns as-is."
        )
        map_info.setWordWrap(True)
        map_info.setStyleSheet("color: #888888;")
        map_layout.addWidget(map_info, stretch=1)
        self._mapping_btn = QPushButton("Edit Mappings…")
        self._mapping_btn.clicked.connect(self._open_mappings)
        map_layout.addWidget(self._mapping_btn)
        layout.addWidget(map_box)

        self._import_widgets = [
            self._radio_file,
            self._radio_dir,
            self._path_edit,
            self._browse_btn,
            self._table_edit,
            self._create_table_btn,
            self._radio_append,
            self._radio_overwrite,
            self._date_chk,
            self._date_col_edit,
            self._ignore_chk,
            self._mapping_btn,
        ]

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.StandardButton.Save).setObjectName(
            "primary"
        )
        layout.addWidget(btn_box)

        self._sync_job_mode_ui()

    def _on_source_type_changed(self) -> None:
        is_file = self._radio_file.isChecked()
        self._ignore_chk.setEnabled(not is_file)
        if is_file:
            self._ignore_chk.setChecked(False)

    def _browse_source(self) -> None:
        if self._radio_file.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Source File",
                "",
                "Data Files (*.csv *.xlsx *.xls);;All Files (*)",
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Select Source Directory"
            )
        if path:
            self._path_edit.setText(path)

    def _browse_export_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Export File",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self._export_path_edit.setText(path)

    def _refresh_connections(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import DbConnectionRepository

        self._conn_combo.clear()
        session = get_session()
        try:
            conns = DbConnectionRepository(session).get_all()
            for c in conns:
                self._conn_combo.addItem(
                    f"{c.name} ({c.host}/{c.database_name})", userData=c.id
                )
        finally:
            session.close()

        if self._conn_combo.count() == 0:
            self._conn_combo.addItem("No connections — add one in Settings", userData=None)

    def _on_freq_changed(self, index: int) -> None:
        self._freq_stack.setCurrentIndex(index)

    def _sync_job_mode_ui(self) -> None:
        is_export = self._job_type_combo.currentData() == "schema_export"
        for widget in self._import_widgets:
            widget.setEnabled(not is_export)
        self._export_group.setVisible(is_export)
        self._export_path_edit.setEnabled(is_export)
        self._export_browse_btn.setEnabled(is_export)
        self._export_format_combo.setEnabled(is_export)
        self._conn_combo.setEnabled(True)
        self._date_col_edit.setEnabled(is_export and self._date_chk.isChecked() or self._date_col_edit.isEnabled())
        self._mapping_btn.setEnabled(not is_export)

    def _open_mappings(self) -> None:
        from app.ui.pages.mapping_page import MappingDialog

        source_path = self._path_edit.text().strip() or None
        dlg = MappingDialog(
            job_id=self._job_id,
            source_path=source_path,
            parent=self,
        )
        dlg.exec()

    def _load_job(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import ImportJobRepository

        session = get_session()
        try:
            job = ImportJobRepository(session).get_by_id(self._job_id)
            if not job:
                return

            self._name_edit.setText(job.name)
            self._path_edit.setText(job.source_path)
            self._table_edit.setText(job.target_table)
            self._export_path_edit.setText(job.export_output_path or "")

            export_format = (job.export_format or "json").lower()
            for i in range(self._export_format_combo.count()):
                if self._export_format_combo.itemData(i) == export_format:
                    self._export_format_combo.setCurrentIndex(i)
                    break

            job_type = (getattr(job, "job_type", "import") or "import")
            for i in range(self._job_type_combo.count()):
                if self._job_type_combo.itemData(i) == job_type:
                    self._job_type_combo.setCurrentIndex(i)
                    break

            if job.source_type == "directory":
                self._radio_dir.setChecked(True)
            else:
                self._radio_file.setChecked(True)

            # Connection
            for i in range(self._conn_combo.count()):
                if self._conn_combo.itemData(i) == job.db_connection_id:
                    self._conn_combo.setCurrentIndex(i)
                    break

            # Frequency
            cfg = job.frequency_config_dict
            if job.frequency_type == "interval":
                self._freq_combo.setCurrentIndex(0)
                self._interval_spin.setValue(int(cfg.get("minutes", 60)))
            elif job.frequency_type == "daily":
                self._freq_combo.setCurrentIndex(1)
                h, m = cfg["time"].split(":")
                self._daily_time.setTime(QTime(int(h), int(m)))
            elif job.frequency_type == "weekly":
                self._freq_combo.setCurrentIndex(2)
                self._weekday_combo.setCurrentIndex(int(cfg.get("weekday", 0)))
                h, m = cfg["time"].split(":")
                self._weekly_time.setTime(QTime(int(h), int(m)))

            self._radio_append.setChecked(job.append_mode)
            self._radio_overwrite.setChecked(not job.append_mode)

            self._date_chk.setChecked(job.use_file_created_date)
            if job.file_created_date_column:
                self._date_col_edit.setText(job.file_created_date_column)

            self._ignore_chk.setChecked(job.ignore_previously_imported)
            self._enabled_chk.setChecked(job.enabled)
            self._sync_job_mode_ui()
        finally:
            session.close()

    def _build_frequency_config(self) -> tuple[str, str]:
        idx = self._freq_combo.currentIndex()
        if idx == 0:
            return "interval", json.dumps(
                {"minutes": self._interval_spin.value()}
            )
        if idx == 1:
            t = self._daily_time.time()
            return "daily", json.dumps(
                {"time": f"{t.hour():02d}:{t.minute():02d}"}
            )
        # weekly
        t = self._weekly_time.time()
        return "weekly", json.dumps(
            {
                "weekday": self._weekday_combo.currentIndex(),
                "time": f"{t.hour():02d}:{t.minute():02d}",
            }
        )

    def _find_template_file(self, source_type: str, source_path: str) -> pathlib.Path:
        path = pathlib.Path(source_path)
        if source_type == "file":
            if not path.exists():
                raise FileNotFoundError("Selected source file does not exist.")
            if path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
                raise ValueError("Source file must be CSV or Excel.")
            return path

        if source_type != "directory":
            raise ValueError("Source type must be file or directory.")
        if not path.is_dir():
            raise ValueError("Source directory does not exist.")

        files = []
        for pattern in ("*.csv", "*.xlsx", "*.xls"):
            files.extend(path.glob(pattern))
        files = sorted(files)
        if not files:
            raise ValueError("No CSV/XLSX/XLS files found in selected directory.")
        return files[0]

    def _normalize_identifier(self, name: str) -> str:
        value = (name or "").strip().lower()
        value = re.sub(r"[^a-zA-Z0-9_]", "_", value)
        value = re.sub(r"_+", "_", value).strip("_")
        if not value:
            value = "column"
        if value[0].isdigit():
            value = f"col_{value}"
        return value[:64]

    def _make_unique_identifiers(self, raw_names: list[str]) -> list[str]:
        names: list[str] = []
        used: set[str] = set()
        for raw in raw_names:
            base = self._normalize_identifier(raw)
            candidate = base
            index = 2
            while candidate in used:
                suffix = f"_{index}"
                candidate = f"{base[:64-len(suffix)]}{suffix}"
                index += 1
            used.add(candidate)
            names.append(candidate)
        return names

    def _create_table_from_template(self) -> None:
        source_path = self._path_edit.text().strip()
        target_table = self._table_edit.text().strip()
        conn_id = self._conn_combo.currentData()
        source_type = "directory" if self._radio_dir.isChecked() else "file"

        if not source_path:
            QMessageBox.warning(self, "Validation", "Source Path is required.")
            return
        if not target_table:
            QMessageBox.warning(self, "Validation", "Target Table is required.")
            return
        if conn_id is None:
            QMessageBox.warning(
                self,
                "Validation",
                "Please select a database connection first.",
            )
            return
        if not _IDENTIFIER_RE.match(target_table):
            QMessageBox.warning(
                self,
                "Validation",
                "Target table name must start with a letter or underscore "
                "and contain only letters, digits, and underscores.",
            )
            return

        try:
            from sqlalchemy import inspect, text

            from app.core.file_reader import FileReader
            from app.data.database import get_target_engine, get_session, quote_name
            from app.data.repositories import DbConnectionRepository

            template_file = self._find_template_file(source_type, source_path)
            source_columns = FileReader().get_columns(template_file)
            if not source_columns:
                raise ValueError("No columns found in template file.")

            final_columns = self._make_unique_identifiers(source_columns)

            # Include date-stamp column if enabled and not already present.
            if self._date_chk.isChecked():
                date_col = (self._date_col_edit.text().strip() or "imported_at")
                date_col = self._normalize_identifier(date_col)
                if date_col not in final_columns:
                    final_columns.append(date_col)

            session = get_session()
            try:
                conn_obj = DbConnectionRepository(session).get_by_id(conn_id)
                if conn_obj is None:
                    raise ValueError("Selected database connection was not found.")
            finally:
                session.close()

            engine = get_target_engine(conn_obj)
            inspector = inspect(engine)
            if inspector.has_table(target_table):
                QMessageBox.information(
                    self,
                    "Table Exists",
                    f"Table '{target_table}' already exists.",
                )
                return

            if engine.dialect.name == "mssql":
                column_lines = [
                    f"{quote_name(engine, c)} NVARCHAR(MAX) NULL"
                    for c in final_columns
                ]
                ddl = (
                    f"CREATE TABLE {quote_name(engine, target_table)} (\n"
                    + ",\n".join(column_lines)
                    + "\n)"
                )
            else:
                column_lines = [
                    f"{quote_name(engine, c)} TEXT NULL"
                    for c in final_columns
                ]
                ddl = (
                    f"CREATE TABLE {quote_name(engine, target_table)} (\n"
                    + ",\n".join(column_lines)
                    + "\n) ENGINE=InnoDB "
                    "DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
                )

            with engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
            engine.dispose()

            source_label = str(template_file.name)
            QMessageBox.information(
                self,
                "Table Created",
                f"Created table '{target_table}' from template file '{source_label}' "
                f"with {len(final_columns)} column(s).",
            )
        except Exception as exc:
            logger.exception("Create table from template failed: %s", exc)
            QMessageBox.critical(
                self,
                "Create Table Failed",
                str(exc),
            )

    def _save(self) -> None:
        name = self._name_edit.text().strip()
        source_path = self._path_edit.text().strip()
        target_table = self._table_edit.text().strip()
        conn_id = self._conn_combo.currentData()
        job_type = self._job_type_combo.currentData() or "import"
        export_output_path = self._export_path_edit.text().strip()
        export_format = self._export_format_combo.currentData() or "json"

        if not name:
            QMessageBox.warning(self, "Validation", "Job Name is required.")
            return
        if conn_id is None:
            QMessageBox.warning(
                self,
                "Validation",
                "Please add a database connection in Settings first.",
            )
            return

        source_type = "directory" if self._radio_dir.isChecked() else "file"
        append_mode = self._radio_append.isChecked()
        use_date = self._date_chk.isChecked()
        date_col = self._date_col_edit.text().strip() if use_date else None
        ignore = self._ignore_chk.isChecked()
        enabled = self._enabled_chk.isChecked()
        freq_type, freq_cfg = self._build_frequency_config()

        if job_type == "schema_export":
            if not export_output_path:
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Export File is required for schema export jobs.",
                )
                return
            target_table = target_table or "schema_export"
            source_path = source_path or ""
        else:
            if not source_path:
                QMessageBox.warning(
                    self, "Validation", "Source Path is required."
                )
                return
            if not target_table:
                QMessageBox.warning(
                    self, "Validation", "Target Table is required."
                )
                return

            if not _IDENTIFIER_RE.match(target_table):
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Target table name must start with a letter or underscore "
                    "and contain only letters, digits, and underscores.",
                )
                return

        from app.data.database import get_session
        from app.data.repositories import ImportJobRepository
        from app.scheduler.scheduler_service import SchedulerService

        session = get_session()
        try:
            repo = ImportJobRepository(session)
            if self._is_edit:
                job = repo.get_by_id(self._job_id)
                if job:
                    job.name = name
                    job.job_type = job_type
                    job.source_type = source_type
                    job.source_path = source_path
                    job.db_connection_id = conn_id
                    job.target_table = target_table
                    job.append_mode = append_mode
                    job.use_file_created_date = use_date
                    job.file_created_date_column = date_col
                    job.ignore_previously_imported = ignore
                    job.export_output_path = export_output_path or None
                    job.export_format = export_format
                    job.frequency_type = freq_type
                    job.frequency_config = freq_cfg
                    job.enabled = enabled
                    repo.update(job)
                    SchedulerService.get_instance().schedule_job(job)
            else:
                job = repo.create(
                    name=name,
                    job_type=job_type,
                    source_type=source_type,
                    source_path=source_path,
                    db_connection_id=conn_id,
                    target_table=target_table,
                    append_mode=append_mode,
                    use_file_created_date=use_date,
                    file_created_date_column=date_col,
                    ignore_previously_imported=ignore,
                    export_output_path=export_output_path or None,
                    export_format=export_format,
                    frequency_type=freq_type,
                    frequency_config=freq_cfg,
                    enabled=enabled,
                )
                self._job_id = job.id
                SchedulerService.get_instance().schedule_job(job)
        finally:
            session.close()

        self.accept()

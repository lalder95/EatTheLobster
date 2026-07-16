import logging
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


class MappingDialog(QDialog):
    def __init__(
        self,
        job_id: Optional[int] = None,
        source_path: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._job_id = job_id
        self._source_path = source_path
        self.setWindowTitle("Column Mappings")
        self.setMinimumSize(560, 420)
        self.setModal(True)
        self._setup_ui()
        self._load_existing()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        info = QLabel(
            "Map source file columns to destination table columns. "
            "Only mapped columns will be imported."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888888;")
        layout.addWidget(info)

        # Toolbar
        toolbar = QHBoxLayout()
        add_btn = QPushButton("+ Add Row")
        add_btn.clicked.connect(self._add_row)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        suggest_btn = QPushButton("Auto-Suggest from File")
        suggest_btn.clicked.connect(self._auto_suggest)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addWidget(suggest_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(
            ["Source Column (file)", "Target Column (table)"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        layout.addWidget(self._table, stretch=1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Save).setObjectName(
            "primary"
        )
        layout.addWidget(btns)

    def _load_existing(self) -> None:
        if self._job_id is None:
            return
        from app.data.database import get_session
        from app.data.repositories import ColumnMappingRepository

        session = get_session()
        try:
            mappings = ColumnMappingRepository(session).get_by_job(
                self._job_id
            )
            for m in mappings:
                self._append_row(m.source_column, m.target_column)
        finally:
            session.close()

    def _append_row(self, source: str = "", target: str = "") -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(source))
        self._table.setItem(row, 1, QTableWidgetItem(target))

    def _add_row(self) -> None:
        self._append_row()

    def _remove_selected(self) -> None:
        selected = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        for row in selected:
            self._table.removeRow(row)

    def _auto_suggest(self) -> None:
        if not self._source_path:
            QMessageBox.information(
                self,
                "Auto-Suggest",
                "Please set a source path in the job editor first, "
                "then re-open mappings.",
            )
            return
        try:
            from app.core.file_reader import FileReader
            from app.core.mapping_service import MappingService

            cols = FileReader().get_columns(self._source_path)
            suggestions = MappingService().suggest_mappings(cols, [])
            self._table.setRowCount(0)
            for s in suggestions:
                self._append_row(s["source"], s["target"])
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Could not read source file:\n{exc}"
            )

    def _collect_mappings(self) -> List[dict]:
        mappings: List[dict] = []
        for row in range(self._table.rowCount()):
            src_item = self._table.item(row, 0)
            tgt_item = self._table.item(row, 1)
            src = (src_item.text().strip() if src_item else "")
            tgt = (tgt_item.text().strip() if tgt_item else "")
            if src and tgt:
                mappings.append({"source": src, "target": tgt})
        return mappings

    def _save(self) -> None:
        if self._job_id is None:
            QMessageBox.information(
                self,
                "Note",
                "Save the job first, then re-open mappings to persist them.",
            )
            self.accept()
            return

        mappings = self._collect_mappings()
        from app.data.database import get_session
        from app.data.repositories import ColumnMappingRepository

        session = get_session()
        try:
            ColumnMappingRepository(session).replace_for_job(
                self._job_id, mappings
            )
        finally:
            session.close()
        self.accept()

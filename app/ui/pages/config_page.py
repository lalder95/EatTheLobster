import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


class _ConnectionForm(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Production DB")
        layout.addRow("Name *", self.name_edit)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("localhost")
        layout.addRow("Host *", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(3306)
        self.port_spin.setFixedWidth(90)
        layout.addRow("Port *", self.port_spin)

        self.db_edit = QLineEdit()
        self.db_edit.setPlaceholderText("my_database")
        layout.addRow("Database *", self.db_edit)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("db_user")
        layout.addRow("Username *", self.user_edit)

        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setPlaceholderText("••••••••")
        layout.addRow("Password *", self.pass_edit)

    def clear(self) -> None:
        for widget in (
            self.name_edit, self.host_edit, self.db_edit,
            self.user_edit, self.pass_edit, self.instance_edit,
        ):
            widget.clear()
        self.port_spin.setValue(3306)
        self.db_type_combo.setCurrentIndex(0)
        self.windows_auth_chk.setChecked(False)

    def populate(self, conn) -> None:
        self.name_edit.setText(conn.name)
        self.host_edit.setText(conn.host)
        self.port_spin.setValue(conn.port)
        self.db_edit.setText(conn.database_name)
        self.user_edit.setText(conn.username)
        self.pass_edit.clear()

        db_type = getattr(conn, "db_type", "mysql") or "mysql"
        idx = self.db_type_combo.findData(db_type)
        self.db_type_combo.setCurrentIndex(idx if idx >= 0 else 0)

        instance_name = getattr(conn, "instance_name", "") or ""
        self.instance_edit.setText(instance_name)

        use_windows_auth = getattr(conn, "use_windows_auth", False) or False
        self.windows_auth_chk.setChecked(use_windows_auth)


class ConfigPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._editing_id: int | None = None
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        title = QLabel("Database Connections")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(20)

        # Left: connection list
        list_box = QGroupBox("Saved Connections")
        list_layout = QVBoxLayout(list_box)

        self._conn_table = QTableWidget(0, 3)
        self._conn_table.setHorizontalHeaderLabels(["Name", "Host / Database", "Type"])
        hdr = self._conn_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._conn_table.setAlternatingRowColors(True)
        self._conn_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._conn_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._conn_table.verticalHeader().setVisible(False)
        self._conn_table.itemSelectionChanged.connect(self._on_conn_selected)
        list_layout.addWidget(self._conn_table, stretch=1)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("+ New")
        new_btn.clicked.connect(self._new_conn)
        del_btn = QPushButton("Delete")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_conn)
        btn_row.addWidget(new_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        list_layout.addLayout(btn_row)

        body.addWidget(list_box, stretch=1)

        # Right: form
        form_box = QGroupBox("Connection Details")
        form_layout = QVBoxLayout(form_box)
        self._form = _ConnectionForm()
        form_layout.addWidget(self._form)

        action_row = QHBoxLayout()
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        self._test_result = QLabel("")
        self._test_result.setStyleSheet("font-size: 12px;")
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_conn)
        action_row.addWidget(test_btn)
        action_row.addWidget(self._test_result, stretch=1)
        action_row.addWidget(save_btn)
        form_layout.addLayout(action_row)
        form_layout.addStretch()

        body.addWidget(form_box, stretch=2)
        root.addLayout(body, stretch=1)

    def _refresh_list(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import DbConnectionRepository

        session = get_session()
        try:
            conns = DbConnectionRepository(session).get_all()
        finally:
            session.close()

        self._conn_table.setRowCount(0)
        for c in conns:
            row = self._conn_table.rowCount()
            self._conn_table.insertRow(row)
            name_item = QTableWidgetItem(c.name)
            name_item.setData(Qt.ItemDataRole.UserRole, c.id)
            self._conn_table.setItem(row, 0, name_item)
            self._conn_table.setItem(
                row, 1,
                QTableWidgetItem(f"{c.host}:{c.port}/{c.database_name}"),
            )
            db_type = getattr(c, "db_type", "mysql") or "mysql"
            type_label = "SQL Server" if db_type == "mssql" else "MySQL"
            self._conn_table.setItem(row, 2, QTableWidgetItem(type_label))

    def _new_conn(self) -> None:
        self._editing_id = None
        self._form.clear()
        self._conn_table.clearSelection()
        self._test_result.setText("")

    def _on_conn_selected(self) -> None:
        selected = self._conn_table.selectedItems()
        if not selected:
            return
        conn_id = selected[0].data(Qt.ItemDataRole.UserRole)
        if conn_id is None:
            return

        from app.data.database import get_session
        from app.data.repositories import DbConnectionRepository

        session = get_session()
        try:
            conn = DbConnectionRepository(session).get_by_id(conn_id)
            if conn:
                self._editing_id = conn_id
                self._form.populate(conn)
                self._test_result.setText("")
        finally:
            session.close()

    def _delete_conn(self) -> None:
        selected = self._conn_table.selectedItems()
        if not selected:
            QMessageBox.information(
                self, "Delete", "Select a connection to delete."
            )
            return

        conn_id = selected[0].data(Qt.ItemDataRole.UserRole)
        name = selected[0].text()

        reply = QMessageBox.question(
            self,
            "Delete Connection",
            f"Delete connection '{name}'? "
            "Any jobs using this connection will also be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from app.data.database import get_session
        from app.data.repositories import DbConnectionRepository

        session = get_session()
        try:
            DbConnectionRepository(session).delete(conn_id)
        finally:
            session.close()

        self._editing_id = None
        self._form.clear()
        self._refresh_list()

    def _test_connection(self) -> None:
        host = self._form.host_edit.text().strip()
        port = self._form.port_spin.value()
        database_name = self._form.db_edit.text().strip()
        username = self._form.user_edit.text().strip()
        password = self._form.pass_edit.text()
        db_type = self._form.db_type_combo.currentData()
        instance_name = self._form.instance_edit.text().strip()
        windows_auth = self._form.windows_auth_chk.isChecked()

        if db_type == "mssql" and windows_auth:
            if not all([host, database_name]):
                self._test_result.setText("Fill in host and database.")
                self._test_result.setStyleSheet("color: #ff9800; font-size: 12px;")
                return
        else:
            if not all([host, database_name, username]):
                self._test_result.setText("Fill in host, database, and username.")
                self._test_result.setStyleSheet("color: #ff9800; font-size: 12px;")
                return

        self._test_result.setText("Testing…")
        self._test_result.setStyleSheet("color: #888888; font-size: 12px;")

        try:
            import urllib.parse
            from sqlalchemy import create_engine, text

            if db_type == "mssql":
                driver = "ODBC Driver 18 for SQL Server"
                server = (
                    f"{host}\\{instance_name}" if instance_name
                    else f"{host},{port}"
                )
                parts = [
                    f"DRIVER={{{driver}}}",
                    f"SERVER={server}",
                    f"DATABASE={database_name}",
                    "TrustServerCertificate=yes",
                ]
                if windows_auth:
                    parts.append("Trusted_Connection=yes")
                else:
                    parts += [f"UID={username}", f"PWD={password}"]
                odbc_str = ";".join(parts)
                url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(odbc_str)}"
            else:
                url = (
                    f"mysql+pymysql://{username}:{password}"
                    f"@{host}:{port}/{database_name}"
                )

            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            self._test_result.setText("Connection successful!")
            self._test_result.setStyleSheet("color: #4caf50; font-size: 12px;")
        except Exception as exc:
            self._test_result.setText(f"Failed: {exc}")
            self._test_result.setStyleSheet("color: #f44336; font-size: 12px;")

    def _save_conn(self) -> None:
        name = self._form.name_edit.text().strip()
        host = self._form.host_edit.text().strip()
        port = self._form.port_spin.value()
        database_name = self._form.db_edit.text().strip()
        username = self._form.user_edit.text().strip()
        password = self._form.pass_edit.text()
        db_type = self._form.db_type_combo.currentData()
        instance_name = self._form.instance_edit.text().strip() or None
        windows_auth = self._form.windows_auth_chk.isChecked()

        requires_credentials = not (db_type == "mssql" and windows_auth)
        if requires_credentials:
            if not all([name, host, database_name, username]):
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Name, Host, Database, and Username are required.",
                )
                return
        else:
            if not all([name, host, database_name]):
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Name, Host, and Database are required.",
                )
                return

        from app.config import encrypt
        from app.data.database import get_session
        from app.data.repositories import DbConnectionRepository

        session = get_session()
        try:
            repo = DbConnectionRepository(session)
            if self._editing_id is not None:
                conn = repo.get_by_id(self._editing_id)
                if conn:
                    conn.name = name
                    conn.host = host
                    conn.port = port
                    conn.database_name = database_name
                    conn.username = username
                    conn.db_type = db_type
                    conn.use_windows_auth = windows_auth
                    conn.instance_name = instance_name
                    if password:
                        conn.encrypted_password = encrypt(password)
                    repo.update(conn)
            else:
                if requires_credentials and not password:
                    QMessageBox.warning(
                        self, "Validation", "Password is required for new connections."
                    )
                    return
                new_conn = repo.create(
                    name=name,
                    host=host,
                    port=port,
                    database_name=database_name,
                    username=username,
                    encrypted_password=encrypt(password) if password else "",
                    db_type=db_type,
                    use_windows_auth=windows_auth,
                    instance_name=instance_name,
                )
                self._editing_id = new_conn.id
        finally:
            session.close()

        self._refresh_list()
        QMessageBox.information(self, "Saved", "Connection saved successfully.")

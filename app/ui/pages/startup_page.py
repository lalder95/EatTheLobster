import logging
import pathlib
import sys

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)
_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE_NAME = "ETLImporter"


class StartupPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        title = QLabel("Startup")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(title)

        subtitle = QLabel(
            "Control whether ETL Importer launches automatically when you sign in."
        )
        subtitle.setStyleSheet("color: #aaaaaa;")
        root.addWidget(subtitle)

        box = QGroupBox("Startup Applications")
        box_layout = QVBoxLayout(box)

        row = QHBoxLayout()
        self._enable_btn = QPushButton("Add To Startup")
        self._enable_btn.setObjectName("primary")
        self._enable_btn.clicked.connect(self._enable_startup)

        self._disable_btn = QPushButton("Remove From Startup")
        self._disable_btn.clicked.connect(self._disable_startup)

        self._status = QLabel("")
        self._status.setStyleSheet("font-size: 12px;")

        row.addWidget(self._enable_btn)
        row.addWidget(self._disable_btn)
        row.addWidget(self._status, stretch=1)
        box_layout.addLayout(row)

        details = QLabel(
            "Uses per-user Windows startup (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)."
        )
        details.setStyleSheet("font-size: 12px; color: #888888;")
        details.setWordWrap(True)
        box_layout.addWidget(details)

        root.addWidget(box)
        root.addStretch()

    def _get_startup_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'

        python_exec = pathlib.Path(sys.executable)
        pythonw_exec = python_exec.with_name("pythonw.exe")
        launcher = pythonw_exec if pythonw_exec.exists() else python_exec
        main_py = pathlib.Path(__file__).resolve().parents[2] / "main.py"
        return f'"{launcher}" "{main_py}"'

    def _is_startup_enabled(self) -> bool:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH) as key:
                _value, _value_type = winreg.QueryValueEx(key, _RUN_VALUE_NAME)
                return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def refresh(self) -> None:
        enabled = self._is_startup_enabled()
        if enabled:
            self._status.setText("Enabled for current user")
            self._status.setStyleSheet("font-size: 12px; color: #4caf50;")
            self._enable_btn.setEnabled(False)
            self._disable_btn.setEnabled(True)
        else:
            self._status.setText("Not enabled")
            self._status.setStyleSheet("font-size: 12px; color: #888888;")
            self._enable_btn.setEnabled(True)
            self._disable_btn.setEnabled(False)

    def _enable_startup(self) -> None:
        try:
            import winreg

            command = self._get_startup_command()
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH) as key:
                winreg.SetValueEx(key, _RUN_VALUE_NAME, 0, winreg.REG_SZ, command)

            self.refresh()
            QMessageBox.information(
                self,
                "Startup Enabled",
                "ETL Importer will start automatically when you sign in.",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Startup Error",
                f"Could not enable startup: {exc}",
            )

    def _disable_startup(self) -> None:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _RUN_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, _RUN_VALUE_NAME)
        except FileNotFoundError:
            pass
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Startup Error",
                f"Could not disable startup: {exc}",
            )
            return

        self.refresh()
        QMessageBox.information(
            self,
            "Startup Disabled",
            "ETL Importer has been removed from startup applications.",
        )

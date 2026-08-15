from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from chatbot_app.config import SCHEMA_SOURCE_PATH
from chatbot_app.core.chatbot_service import ChatbotResult, ChatbotService
from chatbot_app.core.report_status_service import ReportStatus, get_report_status
from chatbot_app.core.sql_utils import extract_final_sql
from chatbot_app.data.database import get_session
from chatbot_app.data.repositories import (
    ChatbotConversationRepository,
    ChatbotMessageRepository,
    ChatbotSettingsRepository,
)
from chatbot_app.security import get_openai_api_key, save_openai_api_key
from chatbot_app.system import get_windows_username, is_admin_user

logger = logging.getLogger(__name__)

_APP_STYLE = """
QMainWindow, QWidget {
    background: #f6f7fb;
    color: #182230;
    font-family: "Segoe UI";
    font-size: 13px;
}
QFrame#TopBar {
    background: #ffffff;
    border-bottom: 1px solid #e6e9f0;
}
QFrame#Composer {
    background: #ffffff;
    border-top: 1px solid #e6e9f0;
}
QLabel#BrandTitle {
    font-size: 20px;
    font-weight: 700;
    color: #162033;
}
QLabel#SubtleText, QLabel#StatusText {
    color: #748094;
}
QLineEdit, QPlainTextEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #dfe4ec;
    border-radius: 8px;
    padding: 7px 10px;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border: 1px solid #4f46e5;
}
QPushButton {
    background: #ffffff;
    color: #384152;
    border: 1px solid #dfe4ec;
    border-radius: 8px;
    padding: 7px 12px;
}
QPushButton:hover { background: #f2f3f7; }
QPushButton#PrimaryButton {
    background: #4f46e5;
    color: white;
    border: 1px solid #4f46e5;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover { background: #4338ca; }
QScrollArea { border: none; background: #f6f7fb; }
"""


class ApiKeyDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OpenAI API Key")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter the OpenAI API key for this Windows user."))
        note = QLabel("The key is validated first and stored securely on this device.")
        note.setObjectName("SubtleText")
        layout.addWidget(note)

        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("sk-...")
        layout.addWidget(self._key_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def api_key(self) -> str:
        return self._key_edit.text().strip()


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chatbot Settings")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._is_admin = is_admin_user()

        self._output_edit = QLineEdit()
        output_browse = QPushButton("Browse…")
        output_browse.clicked.connect(self._browse_output_folder)

        self._model_combo = QComboBox()
        self._model_combo.addItems(["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "gpt-4o"])
        self._enabled_check = QCheckBox("Enable chatbot")

        layout = QVBoxLayout(self)
        if not self._is_admin:
            warning = QLabel("The OpenAI model is managed by an administrator. You can update the SQL output folder.")
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #9a6700; background: #fff8c5; border-radius: 6px; padding: 8px;")
            layout.addWidget(warning)

        form = QFormLayout()
        output_row = QHBoxLayout()
        output_row.addWidget(self._output_edit, stretch=1)
        output_row.addWidget(output_browse)
        form.addRow("SQL output folder", output_row)
        form.addRow("OpenAI model", self._model_combo)
        form.addRow("", self._enabled_check)
        layout.addLayout(form)

        if not self._is_admin:
            self._model_combo.setEnabled(False)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_from_settings(self, settings) -> None:
        self._output_edit.setText(settings.output_folder_path or "")
        self._enabled_check.setChecked(bool(settings.enabled))
        index = self._model_combo.findText(settings.model_name)
        if index >= 0:
            self._model_combo.setCurrentIndex(index)

    def _browse_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select SQL Output Folder")
        if folder:
            self._output_edit.setText(folder)

    def output_folder_path(self) -> str:
        return self._output_edit.text().strip()

    def model_name(self) -> str:
        return self._model_combo.currentText().strip() or "gpt-4o-mini"

    def enabled(self) -> bool:
        return self._enabled_check.isChecked()

    def is_admin(self) -> bool:
        return self._is_admin


class ChatComposer(QPlainTextEdit):
    send_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            event.accept()
            self.send_requested.emit()
            return
        super().keyPressEvent(event)


class ChatBubble(QWidget):
    def __init__(self, role: str, content: str, parent=None) -> None:
        super().__init__(parent)
        is_user = role == "user"
        is_alert = role == "alert"
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(8)

        bubble = QFrame()
        bubble.setMaximumWidth(720)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(13, 9, 13, 9)
        bubble_layout.setSpacing(4)

        sender = QLabel(
            "You" if is_user else "Query Generation" if is_alert else "SQL Assistant"
        )
        sender.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: "
            + ("#e0e7ff;" if is_user else "#b42318;" if is_alert else "#667085;")
        )
        body = QLabel(content)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            "color: " + ("#ffffff;" if is_user else "#b42318;" if is_alert else "#243044;") + ";"
        )
        bubble_layout.addWidget(sender)
        bubble_layout.addWidget(body)

        if is_user:
            bubble.setStyleSheet("QFrame { background: #4f46e5; border-radius: 14px; }")
            row.addStretch()
            row.addWidget(bubble)
        elif is_alert:
            bubble.setStyleSheet(
                "QFrame { background: #fff1f0; border: 1px solid #fecdca; border-radius: 14px; }"
            )
            row.addWidget(bubble)
            row.addStretch()
        else:
            bubble.setStyleSheet("QFrame { background: #ffffff; border: 1px solid #e6e9f0; border-radius: 14px; }")
            row.addWidget(bubble)
            row.addStretch()


class ReportStatusCard(QFrame):
    open_report_requested = Signal(Path)

    def __init__(self, sql_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._sql_path = sql_path
        self._report_path: Path | None = None
        self.setStyleSheet(
            "QFrame { background: #fff1f0; border: 1px solid #fecdca; border-radius: 14px; }"
        )
        self.setMaximumWidth(720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(5)

        title = QLabel("Query Generation Began")
        title.setStyleSheet("font-size: 11px; font-weight: 700; color: #b42318;")
        layout.addWidget(title)

        self._state_label = QLabel()
        self._state_label.setWordWrap(True)
        self._state_label.setStyleSheet("font-weight: 600; color: #b42318;")
        layout.addWidget(self._state_label)

        self._detail_label = QLabel()
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet("color: #7a271a;")
        layout.addWidget(self._detail_label)

        self._open_button = QPushButton("Open Report")
        self._open_button.setVisible(False)
        self._open_button.clicked.connect(self._request_open_report)
        layout.addWidget(self._open_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.update_status(get_report_status(sql_path))

    @property
    def sql_path(self) -> Path:
        return self._sql_path

    def update_status(self, status: ReportStatus) -> None:
        self._report_path = status.report_path
        if status.state == "finished" and status.report_path is not None:
            self.setStyleSheet(
                "QFrame { background: #ecfdf3; border: 1px solid #abefc6; border-radius: 14px; }"
            )
            self._state_label.setText("Finished")
            self._state_label.setStyleSheet("font-weight: 600; color: #067647;")
            self._detail_label.setStyleSheet("color: #05603a;")
            self._detail_label.setText(
                "Your report is ready. If you need further adjustments to this report, "
                "continue this conversation with the report generator."
            )
            self._open_button.setVisible(True)
            return

        self.setStyleSheet(
            "QFrame { background: #fff1f0; border: 1px solid #fecdca; border-radius: 14px; }"
        )
        self._state_label.setText("Starting…")
        self._state_label.setStyleSheet("font-weight: 600; color: #b42318;")
        self._detail_label.setStyleSheet("color: #7a271a;")
        expected_xlsx = self._sql_path.with_suffix(".xlsx").name
        expected_csv = self._sql_path.with_suffix(".csv").name
        self._detail_label.setText(
            "The generated SQL is waiting for the report automation service to create "
            f"{expected_xlsx} or {expected_csv}."
        )
        self._open_button.setVisible(False)

    def _request_open_report(self) -> None:
        if self._report_path is not None:
            self.open_report_requested.emit(self._report_path)


class _SendWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: ChatbotService,
        user_message: str,
        history: list[dict[str, str]],
        model_name: str,
        output_folder: Path | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._user_message = user_message
        self._history = history
        self._model_name = model_name
        self._output_folder = output_folder

    def run(self) -> None:
        try:
            result = self._service.generate_sql(
                user_message=self._user_message,
                history=self._history,
                model_name=self._model_name,
                output_folder=self._output_folder,
            )
            self.completed.emit(result)
        except Exception as exc:
            logger.exception("Chatbot request failed")
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ETL Importer - SQL Chatbot")
        self.resize(1080, 800)
        self.setMinimumSize(760, 580)
        self.setStyleSheet(_APP_STYLE)
        self._service = ChatbotService()
        self._history: list[dict[str, str]] = []
        self._current_conversation_id: int | None = None
        self._worker: _SendWorker | None = None
        self._tracked_sql_path: Path | None = None
        self._report_status_card: ReportStatusCard | None = None
        self._setup_ui()
        self._load_settings()
        self._load_recent_conversation()
        self._ensure_api_key()
        self._report_timer = QTimer(self)
        self._report_timer.timeout.connect(self._refresh_report_status)
        self._report_timer.start(3000)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_layout = QVBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 16, 24, 14)
        top_layout.setSpacing(6)
        title_row = QHBoxLayout()
        title = QLabel("SQL Chatbot")
        title.setObjectName("BrandTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self._api_status = QLabel()
        self._api_status.setObjectName("SubtleText")
        title_row.addWidget(self._api_status)
        self._api_key_btn = QPushButton("Set API Key")
        self._api_key_btn.clicked.connect(self._prompt_for_api_key)
        title_row.addWidget(self._api_key_btn)
        self._settings_button = QPushButton("Settings")
        self._settings_button.clicked.connect(self._open_settings_dialog)
        title_row.addWidget(self._settings_button)
        top_layout.addLayout(title_row)

        self._settings_summary = QLabel()
        self._settings_summary.setObjectName("SubtleText")
        self._settings_summary.setWordWrap(True)
        top_layout.addWidget(self._settings_summary)
        root.addWidget(top_bar)

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._chat_content = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_content)
        self._chat_layout.setContentsMargins(12, 16, 12, 16)
        self._chat_layout.setSpacing(3)
        self._chat_layout.addStretch()
        self._chat_scroll.setWidget(self._chat_content)
        root.addWidget(self._chat_scroll, stretch=1)

        composer = QFrame()
        composer.setObjectName("Composer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(20, 12, 20, 16)
        composer_layout.setSpacing(8)

        self._status = QLabel("Ask about a report, then ask for final SQL when the requirements are complete.")
        self._status.setObjectName("StatusText")
        composer_layout.addWidget(self._status)

        input_row = QHBoxLayout()
        self._message_edit = ChatComposer()
        self._message_edit.setPlaceholderText("Describe the report you need…  (Enter to send, Shift+Enter for a new line)")
        self._message_edit.setFixedHeight(72)
        self._message_edit.send_requested.connect(self._send_message)
        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("PrimaryButton")
        self._send_btn.setMinimumWidth(88)
        self._send_btn.clicked.connect(self._send_message)
        self._new_chat_btn = QPushButton("New chat")
        self._new_chat_btn.clicked.connect(self._new_conversation)
        input_row.addWidget(self._message_edit, stretch=1)
        input_row.addWidget(self._new_chat_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        input_row.addWidget(self._send_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        composer_layout.addLayout(input_row)
        root.addWidget(composer)

    def _load_settings(self) -> None:
        session = get_session()
        try:
            self._settings = ChatbotSettingsRepository(session).get()
        finally:
            session.close()
        self._refresh_settings_summary()
        try:
            self._api_status.setText("API key configured" if get_openai_api_key() else "API key missing")
        except Exception as exc:
            self._api_status.setText(f"Secure key store unavailable: {exc}")

    def _refresh_settings_summary(self) -> None:
        folder = self._settings.output_folder_path or "Output folder not configured"
        enabled = "Ready" if self._settings.enabled else "Disabled"
        self._settings_summary.setText(
            f"{enabled}  •  Model: {self._settings.model_name}  •  {folder}  •  Schema: {SCHEMA_SOURCE_PATH}"
        )

    def _open_settings_dialog(self) -> None:
        session = get_session()
        try:
            settings = ChatbotSettingsRepository(session).get()
        finally:
            session.close()
        dialog = SettingsDialog(self)
        dialog.load_from_settings(settings)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        session = get_session()
        try:
            repo = ChatbotSettingsRepository(session)
            self._settings = repo.save(
                output_folder_path=dialog.output_folder_path(),
                model_name=dialog.model_name() if dialog.is_admin() else settings.model_name,
                enabled=dialog.enabled(),
            )
        finally:
            session.close()
        self._refresh_settings_summary()
        self._status.setText("Settings saved.")

    def _ensure_api_key(self) -> None:
        try:
            if get_openai_api_key():
                return
        except Exception as exc:
            QMessageBox.warning(self, "API Key Store", f"The secure key store is unavailable: {exc}")
            return
        while True:
            dialog = ApiKeyDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._status.setText("Set an OpenAI API key to start chatting.")
                return
            api_key = dialog.api_key()
            if not api_key:
                QMessageBox.warning(self, "Validation", "API key cannot be empty.")
                continue
            try:
                self._service.validate_api_key(api_key, self._settings.model_name)
                save_openai_api_key(api_key)
                self._api_status.setText("API key configured")
                return
            except Exception as exc:
                QMessageBox.critical(self, "API Key Error", f"The key could not be validated: {exc}")

    def _prompt_for_api_key(self) -> None:
        self._ensure_api_key()

    def _new_conversation(self) -> None:
        self._history.clear()
        self._current_conversation_id = None
        self._tracked_sql_path = None
        self._report_status_card = None
        self._clear_bubbles()
        self._status.setText("New conversation started. Describe the report you need.")

    def _load_recent_conversation(self) -> None:
        session = get_session()
        try:
            convo_repo = ChatbotConversationRepository(session)
            msg_repo = ChatbotMessageRepository(session)
            conversation = convo_repo.get_most_recent()
            if conversation is None:
                return
            self._current_conversation_id = conversation.id
            last_sql_path = conversation.last_sql_path
            messages = msg_repo.get_for_conversation(conversation.id)
            self._history = [{"role": item.role, "content": item.content} for item in messages]
        finally:
            session.close()
        for message in self._history:
            if message["role"] == "assistant" and extract_final_sql(message["content"]):
                continue
            else:
                self._add_bubble(message["role"], message["content"])
        if last_sql_path:
            self._start_report_tracking(Path(last_sql_path))

    def _send_message(self) -> None:
        message = self._message_edit.toPlainText().strip()
        if not message:
            return
        if not self._settings.enabled:
            QMessageBox.warning(self, "Chatbot Disabled", "An administrator has disabled the chatbot.")
            return

        output_folder = Path(self._settings.output_folder_path) if self._settings.output_folder_path.strip() else None
        session = get_session()
        try:
            convo_repo = ChatbotConversationRepository(session)
            msg_repo = ChatbotMessageRepository(session)
            if self._current_conversation_id is None:
                conversation = convo_repo.create(
                    title=message[:120] or "Conversation",
                    model_name=self._settings.model_name,
                    output_folder_path=str(output_folder or ""),
                    schema_source_path=str(SCHEMA_SOURCE_PATH),
                )
                self._current_conversation_id = conversation.id
            msg_repo.add_message(self._current_conversation_id, "user", message)
        finally:
            session.close()

        self._history.append({"role": "user", "content": message})
        self._message_edit.clear()
        self._add_bubble("user", message)
        self._set_sending_state(True)
        self._status.setText("Thinking…")
        self._worker = _SendWorker(
            service=self._service,
            user_message=message,
            history=list(self._history),
            model_name=self._settings.model_name,
            output_folder=output_folder,
            parent=self,
        )
        self._worker.completed.connect(self._handle_result)
        self._worker.failed.connect(self._handle_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _handle_result(self, result: ChatbotResult) -> None:
        self._history.append({"role": "assistant", "content": result.assistant_text})
        session = get_session()
        try:
            convo_repo = ChatbotConversationRepository(session)
            msg_repo = ChatbotMessageRepository(session)
            if self._current_conversation_id is not None:
                msg_repo.add_message(self._current_conversation_id, "assistant", result.assistant_text)
                if result.output_path is not None:
                    convo_repo.update_metadata(
                        self._current_conversation_id,
                        last_sql_path=str(result.output_path),
                    )
        finally:
            session.close()
        if result.output_path is not None:
            self._start_report_tracking(result.output_path)
            self._status.setText(f"Final SQL saved to {result.output_path}")
        else:
            self._add_bubble("assistant", result.assistant_text)
            self._status.setText("Continue the conversation, or ask for the final SQL when ready.")
        self._set_sending_state(False)
        self._worker = None

    def _handle_error(self, message: str) -> None:
        self._add_bubble("assistant", f"Unable to complete that request: {message}")
        self._status.setText(message)
        self._set_sending_state(False)
        self._worker = None

    def _set_sending_state(self, sending: bool) -> None:
        self._send_btn.setEnabled(not sending)
        self._new_chat_btn.setEnabled(not sending)
        self._message_edit.setEnabled(not sending)

    def _start_report_tracking(self, sql_path: Path) -> None:
        self._tracked_sql_path = sql_path
        if self._report_status_card is not None:
            self._report_status_card.deleteLater()
        self._report_status_card = ReportStatusCard(sql_path, self._chat_content)
        self._report_status_card.open_report_requested.connect(self._open_report)
        self._chat_layout.insertWidget(
            self._chat_layout.count() - 1,
            self._report_status_card,
        )
        self._scroll_to_latest()
        self._refresh_report_status()

    def _refresh_report_status(self) -> None:
        if self._tracked_sql_path is None or self._report_status_card is None:
            return
        status = get_report_status(self._tracked_sql_path)
        self._report_status_card.update_status(status)

    def _open_report(self, report_path: Path) -> None:
        if not report_path.is_file():
            QMessageBox.warning(self, "Report Not Found", "The completed report file is no longer available.")
            self._refresh_report_status()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(report_path))):
            QMessageBox.warning(self, "Open Report", f"Windows could not open the report:\n{report_path}")

    def _add_bubble(self, role: str, content: str) -> None:
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, ChatBubble(role, content, self._chat_content))
        self._scroll_to_latest()

    def _clear_bubbles(self) -> None:
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _scroll_to_latest(self) -> None:
        scrollbar = self._chat_scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: scrollbar.setValue(scrollbar.maximum()))

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from agent_switcher.core.store import Store, StoreError
from agent_switcher.core.providers.base import LoginMode

from .workers import LoginWorker
from .icons import set_action_icon
from .window_surface import create_shadowed_surface
from .i18n import tr
from .help import add_context_help


class AddAccountDialog(QDialog):
    def __init__(self, store: Store, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.worker: Optional[LoginWorker] = None
        self.result_name: Optional[str] = None

        self.setWindowTitle(tr("Add account"))
        self.setModal(True)
        self.setMinimumWidth(500)

        _surface, root = create_shadowed_surface(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        self.help_button = add_context_help(root, "add_account", self)

        intro = QLabel(tr("Give the account a name, then choose how to sign in."))
        intro.setWordWrap(True)
        root.addWidget(intro)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("Name")))
        self.name_edit = QLineEdit(self._default_profile_name())
        self.name_edit.setPlaceholderText(tr("work"))
        name_row.addWidget(self.name_edit, 1)
        root.addLayout(name_row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(tr("Sign-in method")))
        self.browser_radio = QRadioButton(tr("Browser"))
        self.browser_radio.setChecked(True)
        self.browser_radio.setToolTip(tr("Open browser OAuth sign-in on this computer"))
        mode_row.addWidget(self.browser_radio)
        self.device_radio = QRadioButton(tr("Device code"))
        self.device_radio.setToolTip(tr("Show a link and one-time code"))
        mode_row.addWidget(self.device_radio)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        self.start_button = QPushButton(tr("Start sign-in"))
        set_action_icon(self.start_button, "fa5s.sign-in-alt")
        self.start_button.clicked.connect(self.start_login)
        root.addWidget(self.start_button)

        self.steps_widget = QWidget()
        steps = QVBoxLayout(self.steps_widget)
        steps.setContentsMargins(0, 0, 0, 0)
        steps.setSpacing(8)

        self.url_widget = QWidget()
        url_layout = QVBoxLayout(self.url_widget)
        url_layout.setContentsMargins(0, 0, 0, 0)
        self.url_heading = QLabel(tr("Manual fallback link"))
        url_layout.addWidget(self.url_heading)
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setReadOnly(True)
        url_row.addWidget(self.url_edit, 1)
        self.copy_url_button = QPushButton(tr("Copy"))
        set_action_icon(self.copy_url_button, "fa5s.copy")
        self.copy_url_button.clicked.connect(lambda: self.copy_text(self.url_edit.text()))
        url_row.addWidget(self.copy_url_button)
        self.open_url_button = QPushButton(tr("Open"))
        set_action_icon(self.open_url_button, "fa5s.external-link-alt")
        self.open_url_button.clicked.connect(self.open_url)
        url_row.addWidget(self.open_url_button)
        url_layout.addLayout(url_row)
        steps.addWidget(self.url_widget)

        self.code_widget = QWidget()
        code_layout = QVBoxLayout(self.code_widget)
        code_layout.setContentsMargins(0, 0, 0, 0)
        self.code_heading = QLabel(tr("2. Enter this code"))
        code_layout.addWidget(self.code_heading)
        code_frame = QFrame()
        code_frame.setFrameShape(QFrame.Shape.StyledPanel)
        code_row = QHBoxLayout(code_frame)
        self.code_label = QLabel("------")
        self.code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = self.code_label.font()
        font.setFamily("monospace")
        font.setPointSize(24)
        font.setBold(True)
        self.code_label.setFont(font)
        code_row.addWidget(self.code_label, 1, Qt.AlignmentFlag.AlignCenter)
        self.copy_code_button = QPushButton(tr("Copy"))
        set_action_icon(self.copy_code_button, "fa5s.copy")
        self.copy_code_button.clicked.connect(lambda: self.copy_text(self.code_label.text()))
        code_row.addWidget(self.copy_code_button)
        code_layout.addWidget(code_frame)
        steps.addWidget(self.code_widget)
        self.steps_widget.hide()
        root.addWidget(self.steps_widget)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.raw_toggle = QPushButton(tr("Show raw output"))
        set_action_icon(self.raw_toggle, "fa5s.terminal")
        self.raw_toggle.clicked.connect(self.toggle_raw_output)
        root.addWidget(self.raw_toggle)
        self.raw_output = QTextEdit()
        self.raw_output.setReadOnly(True)
        self.raw_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.raw_output.hide()
        root.addWidget(self.raw_output)

        self.close_button = QPushButton(tr("Close"))
        set_action_icon(self.close_button, "fa5s.times")
        self.close_button.clicked.connect(self.reject)
        root.addWidget(self.close_button)

    def _default_profile_name(self) -> str:
        existing = set(self.store.profiles())
        index = 1
        while f"account{index}" in existing:
            index += 1
        return f"account{index}"

    def start_login(self) -> None:
        name = self.name_edit.text().strip()
        try:
            self.store.validate_name(name)
        except StoreError as exc:
            self.status_label.setText(tr(str(exc)))
            return
        if name in self.store.profiles():
            self.status_label.setText(tr("{name} already exists. Pick another name.", name=name))
            return

        self.result_name = name
        mode: LoginMode = "browser" if self.browser_radio.isChecked() else "device"
        self.name_edit.setEnabled(False)
        self.browser_radio.setEnabled(False)
        self.device_radio.setEnabled(False)
        self.start_button.setEnabled(False)
        self.url_edit.clear()
        self.code_label.setText("------")
        if mode == "browser":
            self.start_button.setText(tr("Waiting for browser..."))
            self.steps_widget.hide()
            self.status_label.setText(tr("Waiting for browser sign-in to complete..."))
        else:
            self.start_button.setText(tr("Waiting for device sign-in..."))
            self.url_heading.setText(tr("1. Open this link"))
            self.url_widget.show()
            self.code_widget.show()
            self.steps_widget.show()
            self.status_label.setText(tr("Starting device sign-in..."))

        self.worker = LoginWorker(self.store, name, mode)
        self.worker.url_ready.connect(self.on_url)
        self.worker.code_ready.connect(self.on_code)
        self.worker.line_ready.connect(self.on_line)
        self.worker.succeeded.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def on_url(self, url: str) -> None:
        self.url_edit.setText(url)
        self.url_widget.show()
        self.steps_widget.show()
        if self.browser_radio.isChecked():
            self.url_heading.setText(tr("Browser did not open? Use this link"))
            self.code_widget.hide()
            self.status_label.setText(
                tr("Waiting for browser sign-in. The link is available as a manual fallback.")
            )
        else:
            self.status_label.setText(tr("Open the link and enter the code."))

    def on_code(self, code: str) -> None:
        self.code_label.setText(code)

    def on_line(self, line: str) -> None:
        self.raw_output.append(line)

    def on_success(self, _profile: object, _result: object) -> None:
        self.worker = None
        self.accept()

    def on_failure(self, error: str) -> None:
        self.worker = None
        self.status_label.setText(tr(error or "Sign-in failed."))
        self.start_button.setEnabled(True)
        self.start_button.setText(tr("Try again"))
        self.name_edit.setEnabled(True)
        self.browser_radio.setEnabled(True)
        self.device_radio.setEnabled(True)

    def toggle_raw_output(self) -> None:
        visible = not self.raw_output.isVisible()
        self.raw_output.setVisible(visible)
        self.raw_toggle.setText(tr("Hide raw output" if visible else "Show raw output"))

    def copy_text(self, text: str) -> None:
        if not text or text.startswith("-"):
            return
        QApplication.clipboard().setText(text)
        self.status_label.setText(tr("Copied."))

    def open_url(self) -> None:
        url = self.url_edit.text()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        super().reject()

    def closeEvent(self, event) -> None:
        self.reject()
        event.accept()

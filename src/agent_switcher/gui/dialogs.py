from __future__ import annotations

from datetime import datetime
from typing import Optional

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from agent_switcher.core.activity_log import ActivityLog
from agent_switcher.core.proxy import ProxyConfig, ProxyConfigError
from agent_switcher import __version__

from .window_surface import create_shadowed_surface
from .i18n import tr
from .help import add_context_help


class AboutDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("About Agent Switcher"))
        self.resize(480, 300)
        _surface, layout = create_shadowed_surface(self)

        title = QLabel(tr("Agent Switcher"))
        title_font = title.font()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.version_label = QLabel(tr("Version {version}", version=__version__))
        layout.addWidget(self.version_label)
        description = QLabel(
            tr("Switch saved CLI coding-agent accounts without revoking refresh tokens.")
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addWidget(QLabel(tr("Released under the MIT License.")))
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TransparencyDialog(QDialog):
    def __init__(self, activity_log: ActivityLog, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Network activity"))
        self.resize(760, 440)

        _surface, layout = create_shadowed_surface(self)
        self.help_button = add_context_help(layout, "network", self)
        table = QTableWidget(0, 4)
        self.table = table
        table.setHorizontalHeaderLabels([tr("When"), tr("Purpose"), tr("Endpoint"), tr("Result")])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        events = activity_log.recent_network_calls(200)
        table.setRowCount(len(events))
        for row, event in enumerate(events):
            payload = event.get("payload", {})
            result = (
                tr("Success")
                if payload.get("success")
                else tr("Failed: {error}", error=payload.get("error") or tr("unknown error"))
            )
            values = [
                _local_time(event.get("timestamp")),
                tr(str(payload.get("purpose") or "unknown")),
                str(payload.get("endpoint") or "unknown"),
                result,
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        layout.addWidget(table)

        if not events:
            layout.addWidget(QLabel(tr("No network calls recorded.")))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SettingsDialog(QDialog):
    def __init__(
        self,
        offline_mode: bool,
        low_quota_threshold_pct: int,
        smart_pick_stale_minutes: int,
        smart_pick_headroom_pct: int,
        global_hotkey_enabled: bool,
        global_hotkey: str,
        theme: str,
        language: str,
        proxy_mode: str,
        proxy_url: str,
        ip_guard_enabled: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.resize(640, 720)
        self.setMinimumSize(580, 620)
        _surface, root = create_shadowed_surface(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        heading_row = QHBoxLayout()
        heading_copy = QVBoxLayout()
        heading_copy.setSpacing(2)
        heading = QLabel(tr("Settings"))
        heading_font = heading.font()
        heading_font.setPointSize(18)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading_copy.addWidget(heading)
        subtitle = QLabel(tr("Customize appearance, network, quota checks, and quick switching."))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: palette(placeholder-text);")
        heading_copy.addWidget(subtitle)
        heading_row.addLayout(heading_copy, 1)
        help_holder = QVBoxLayout()
        self.help_button = add_context_help(help_holder, "settings", self)
        heading_row.addLayout(help_holder)
        root.addLayout(heading_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(12)

        appearance, appearance_layout = self._section(
            tr("Appearance"),
            tr("Choose how Agent Switcher looks and reads."),
            "fa5s.palette",
            "#8b5cf6",
        )
        appearance_form = QFormLayout()
        appearance_form.setHorizontalSpacing(18)
        appearance_form.setVerticalSpacing(10)
        self.offline_checkbox = QCheckBox(tr("Offline mode (disable usage checks)"))
        self.offline_checkbox.setChecked(offline_mode)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("System"), "system")
        self.theme_combo.addItem(tr("Dark"), "dark")
        self.theme_combo.addItem(tr("Light"), "light")
        selected_theme = self.theme_combo.findData(theme)
        self.theme_combo.setCurrentIndex(max(0, selected_theme))
        appearance_form.addRow(tr("Theme"), self.theme_combo)
        self.language_combo = QComboBox()
        self.language_combo.addItem(tr("English"), "en")
        self.language_combo.addItem(tr("Persian"), "fa")
        selected_language = self.language_combo.findData(language)
        self.language_combo.setCurrentIndex(max(0, selected_language))
        appearance_form.addRow(tr("Language"), self.language_combo)
        appearance_layout.addLayout(appearance_form)
        language_note = QLabel(
            tr("Restart the app after changing language to fully apply text direction and translations.")
        )
        language_note.setWordWrap(True)
        language_note.setStyleSheet("color: palette(placeholder-text);")
        appearance_layout.addWidget(language_note)
        layout.addWidget(appearance)

        network, network_layout = self._section(
            tr("Network & privacy"),
            tr("Control whether and how Agent Switcher connects."),
            "fa5s.shield-alt",
            "#2f80ed",
        )
        network_layout.addWidget(self.offline_checkbox)
        self.ip_guard_checkbox = QCheckBox(
            tr("Warn before sensitive OpenAI activity when the public IP changes")
        )
        self.ip_guard_checkbox.setChecked(ip_guard_enabled)
        network_layout.addWidget(self.ip_guard_checkbox)
        network_form = QFormLayout()
        network_form.setHorizontalSpacing(18)
        network_form.setVerticalSpacing(10)
        self.proxy_mode_combo = QComboBox()
        self.proxy_mode_combo.addItem(tr("No proxy"), "none")
        self.proxy_mode_combo.addItem(tr("Custom HTTP proxy"), "custom")
        selected_proxy_mode = self.proxy_mode_combo.findData(proxy_mode)
        self.proxy_mode_combo.setCurrentIndex(max(0, selected_proxy_mode))
        network_form.addRow(tr("Proxy"), self.proxy_mode_combo)
        self.proxy_url_label = QLabel(tr("HTTP proxy URL"))
        self.proxy_url_edit = QLineEdit(proxy_url)
        self.proxy_url_edit.setPlaceholderText("http://127.0.0.1:8080")
        network_form.addRow(self.proxy_url_label, self.proxy_url_edit)
        network_layout.addLayout(network_form)
        proxy_note = QLabel(
            tr("The proxy is used for sign-in, quota checks, and token refresh. Proxy credentials are stored locally in settings.")
        )
        proxy_note.setWordWrap(True)
        proxy_note.setStyleSheet("color: palette(placeholder-text);")
        network_layout.addWidget(proxy_note)
        ip_guard_note = QLabel(
            tr(
                "IP Guard checks the public route before sign-in, usage checks, and account switching. "
                "Only a local fingerprint is saved; the raw IP is not stored."
            )
        )
        ip_guard_note.setWordWrap(True)
        ip_guard_note.setStyleSheet("color: palette(placeholder-text);")
        network_layout.addWidget(ip_guard_note)
        self.proxy_error = QLabel("")
        self.proxy_error.setWordWrap(True)
        self.proxy_error.setStyleSheet("color: #d64545;")
        network_layout.addWidget(self.proxy_error)
        self.proxy_mode_combo.currentIndexChanged.connect(self._update_proxy_fields)
        self._update_proxy_fields()
        layout.addWidget(network)

        quota, quota_layout = self._section(
            tr("Quota & Smart Pick"),
            tr("Tune warnings and how Smart Pick evaluates accounts."),
            "fa5s.chart-pie",
            "#2e9d55",
        )
        quota_form = QFormLayout()
        quota_form.setHorizontalSpacing(18)
        quota_form.setVerticalSpacing(10)
        self.low_quota_threshold = QSpinBox()
        self.low_quota_threshold.setRange(0, 100)
        self.low_quota_threshold.setSuffix(tr("% remaining"))
        self.low_quota_threshold.setValue(low_quota_threshold_pct)
        quota_form.addRow(tr("Low-quota warning threshold"), self.low_quota_threshold)
        self.smart_pick_stale = QSpinBox()
        self.smart_pick_stale.setRange(1, 1440)
        self.smart_pick_stale.setSuffix(tr(" minutes"))
        self.smart_pick_stale.setValue(smart_pick_stale_minutes)
        quota_form.addRow(tr("Smart pick data freshness"), self.smart_pick_stale)
        self.smart_pick_headroom = QSpinBox()
        self.smart_pick_headroom.setRange(0, 100)
        self.smart_pick_headroom.setSuffix(tr("% remaining"))
        self.smart_pick_headroom.setValue(smart_pick_headroom_pct)
        quota_form.addRow(tr("Smart pick minimum headroom"), self.smart_pick_headroom)
        quota_layout.addLayout(quota_form)
        layout.addWidget(quota)

        shortcut, shortcut_layout = self._section(
            tr("Quick switch"),
            tr("Open the account picker from anywhere with a shortcut."),
            "fa5s.keyboard",
            "#e5902f",
        )
        self.hotkey_enabled = QCheckBox(tr("Enable global quick-switch hotkey"))
        self.hotkey_enabled.setChecked(global_hotkey_enabled)
        shortcut_layout.addWidget(self.hotkey_enabled)
        shortcut_form = QFormLayout()
        self.hotkey_edit = QLineEdit(global_hotkey)
        self.hotkey_edit.setPlaceholderText("<ctrl>+<alt>+<space>")
        shortcut_form.addRow(tr("Shortcut"), self.hotkey_edit)
        shortcut_layout.addLayout(shortcut_form)
        self.hotkey_enabled.toggled.connect(self.hotkey_edit.setEnabled)
        self.hotkey_edit.setEnabled(global_hotkey_enabled)
        layout.addWidget(shortcut)
        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _section(title: str, subtitle: str, icon_name: str, icon_color: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("settingsSection")
        frame.setStyleSheet(
            "QFrame#settingsSection { border: 1px solid palette(mid); border-radius: 12px; "
            "background: palette(base); }"
        )
        section_layout = QVBoxLayout(frame)
        section_layout.setContentsMargins(16, 14, 16, 15)
        section_layout.setSpacing(10)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(22, 22))
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        heading = QLabel(title)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSize(heading_font.pointSize() + 1)
        heading.setFont(heading_font)
        copy.addWidget(heading)
        description = QLabel(subtitle)
        description.setWordWrap(True)
        description.setStyleSheet("color: palette(placeholder-text);")
        copy.addWidget(description)
        header.addLayout(copy, 1)
        section_layout.addLayout(header)
        return frame, section_layout

    def proxy_config(self) -> ProxyConfig:
        return ProxyConfig.from_values(
            self.proxy_mode_combo.currentData(),
            self.proxy_url_edit.text(),
        )

    def accept(self) -> None:
        try:
            self.proxy_config()
        except ProxyConfigError as exc:
            self.proxy_error.setText(tr(str(exc)))
            self.proxy_url_edit.setFocus()
            return
        self.proxy_error.clear()
        super().accept()

    def _update_proxy_fields(self) -> None:
        custom = self.proxy_mode_combo.currentData() == "custom"
        self.proxy_url_label.setEnabled(custom)
        self.proxy_url_edit.setEnabled(custom)
        if not custom:
            self.proxy_error.clear()


class HistoryDialog(QDialog):
    def __init__(self, activity_log: ActivityLog, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Switch history"))
        self.resize(560, 400)
        _surface, layout = create_shadowed_surface(self)
        self.help_button = add_context_help(layout, "history", self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("When"), tr("From"), tr("To")])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        events = activity_log.recent_switches(200)
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            payload = event.get("payload", {})
            values = [
                _local_time(event.get("timestamp")),
                tr(str(payload.get("from") or "none")),
                tr(str(payload.get("to") or "none")),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        layout.addWidget(self.table)
        if not events:
            layout.addWidget(QLabel(tr("No switches recorded.")))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def _local_time(value: object) -> str:
    if not isinstance(value, str):
        return tr("unknown")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from agent_switcher.core.activity_log import ActivityLog
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
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        _surface, layout = create_shadowed_surface(self)
        self.help_button = add_context_help(layout, "settings", self)
        self.offline_checkbox = QCheckBox(tr("Offline mode (disable usage checks)"))
        self.offline_checkbox.setChecked(offline_mode)
        layout.addWidget(self.offline_checkbox)
        layout.addWidget(QLabel(tr("Theme")))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("System"), "system")
        self.theme_combo.addItem(tr("Dark"), "dark")
        self.theme_combo.addItem(tr("Light"), "light")
        selected_theme = self.theme_combo.findData(theme)
        self.theme_combo.setCurrentIndex(max(0, selected_theme))
        layout.addWidget(self.theme_combo)
        layout.addWidget(QLabel(tr("Language")))
        self.language_combo = QComboBox()
        self.language_combo.addItem(tr("English"), "en")
        self.language_combo.addItem(tr("Persian"), "fa")
        selected_language = self.language_combo.findData(language)
        self.language_combo.setCurrentIndex(max(0, selected_language))
        layout.addWidget(self.language_combo)
        language_note = QLabel(
            tr("Restart the app after changing language to fully apply text direction and translations.")
        )
        language_note.setWordWrap(True)
        layout.addWidget(language_note)
        layout.addWidget(QLabel(tr("Low-quota warning threshold")))
        self.low_quota_threshold = QSpinBox()
        self.low_quota_threshold.setRange(0, 100)
        self.low_quota_threshold.setSuffix(tr("% remaining"))
        self.low_quota_threshold.setValue(low_quota_threshold_pct)
        layout.addWidget(self.low_quota_threshold)
        layout.addWidget(QLabel(tr("Smart pick data freshness")))
        self.smart_pick_stale = QSpinBox()
        self.smart_pick_stale.setRange(1, 1440)
        self.smart_pick_stale.setSuffix(tr(" minutes"))
        self.smart_pick_stale.setValue(smart_pick_stale_minutes)
        layout.addWidget(self.smart_pick_stale)
        layout.addWidget(QLabel(tr("Smart pick minimum headroom")))
        self.smart_pick_headroom = QSpinBox()
        self.smart_pick_headroom.setRange(0, 100)
        self.smart_pick_headroom.setSuffix(tr("% remaining"))
        self.smart_pick_headroom.setValue(smart_pick_headroom_pct)
        layout.addWidget(self.smart_pick_headroom)
        self.hotkey_enabled = QCheckBox(tr("Enable global quick-switch hotkey"))
        self.hotkey_enabled.setChecked(global_hotkey_enabled)
        layout.addWidget(self.hotkey_enabled)
        self.hotkey_edit = QLineEdit(global_hotkey)
        self.hotkey_edit.setPlaceholderText("<ctrl>+<alt>+<space>")
        layout.addWidget(self.hotkey_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


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

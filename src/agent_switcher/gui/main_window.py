from __future__ import annotations

import sys
from typing import Optional
from dataclasses import replace
from datetime import timedelta

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from agent_switcher.core.store import Profile, Store, StoreError
from agent_switcher.core.usage import Usage
from agent_switcher.core.smart_pick import choose_smart_profile, stale_usage_profiles
from agent_switcher.core.proxy import ProxyConfig
from agent_switcher.core.updater import automatic_install_supported, launch_update_helper
from agent_switcher import __version__

from .add_dialog import AddAccountDialog
from .icons import set_action_icon
from .platform import PlatformIntegration
from .profile_row import ProfileRow
from .settings import DEFAULT_SETTINGS, GuiSettings, SettingsStore
from .dialogs import AboutDialog, HistoryDialog, SettingsDialog, TransparencyDialog
from .tray import TrayController
from .workers import EgressCheckWorker, UpdateCheckWorker, UpdateDownloadWorker, UsageRefreshWorker
from .hotkey import GlobalHotkeyController
from .quick_switch import QuickSwitchPopup
from .window_surface import create_shadowed_surface
from .theme import apply_theme
from .onboarding import OnboardingDialog
from .privacy_notice import PrivacyNoticeDialog
from .update_dialog import UpdateAvailableDialog, UpdateProgressDialog
from .i18n import tr
from .message_box import ask_restart, show_message
from .egress_prompt import confirm_egress


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: Store,
        platform: PlatformIntegration,
        settings: GuiSettings = DEFAULT_SETTINGS,
        settings_store: Optional[SettingsStore] = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.platform = platform
        self.settings = settings
        self.settings_store = settings_store or SettingsStore(store.activity_log.path.parent / "settings.json")
        self.store.set_proxy_config(ProxyConfig.from_values(settings.proxy_mode, settings.proxy_url))
        self.store.set_egress_guard_enabled(settings.ip_guard_enabled)
        self.rows: dict[str, ProfileRow] = {}
        self.usage_cache: dict[str, Usage] = {}
        self.usage_inflight: set[str] = set()
        self.usage_worker: Optional[UsageRefreshWorker] = None
        self.smart_pick_pending = False
        self.hotkey_controller: Optional[GlobalHotkeyController] = None
        self.quick_switch_popup: Optional[QuickSwitchPopup] = None
        self.onboarding_dialog: Optional[OnboardingDialog] = None
        self.update_check_worker: Optional[UpdateCheckWorker] = None
        self.update_download_worker: Optional[UpdateDownloadWorker] = None
        self.update_progress_dialog: Optional[UpdateProgressDialog] = None
        self.switch_egress_worker: Optional[EgressCheckWorker] = None
        self.pending_switch: Optional[str] = None

        self.setWindowTitle(tr("Agent Switcher"))
        self.setWindowIcon(platform.app_icon())
        available = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        width = max(480, min(1000, available.width() - 40)) if available else 1000
        height = max(420, min(760, available.height() - 40)) if available else 760
        self.setFixedSize(width, height)

        central = QWidget()
        root, layout = create_shadowed_surface(central)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(tr("Agent Switcher"))
        title_font = title.font()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title_box.addWidget(title)
        home = QLabel(str(self.store.home))
        home.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        home.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        title_box.addWidget(home)
        header.addLayout(title_box, 1)

        self.refresh_button = QToolButton()
        set_action_icon(self.refresh_button, "fa5s.sync-alt")
        self.refresh_button.setToolTip(tr("Refresh usage for all accounts"))
        self.refresh_button.setAccessibleName(tr("Refresh all usage"))
        self.refresh_button.setAutoRaise(True)
        self.refresh_button.clicked.connect(self.refresh_all_usage)
        header.addWidget(self.refresh_button)

        smart_button = QToolButton()
        set_action_icon(smart_button, "fa5s.magic")
        smart_button.setText(tr("Smart pick"))
        smart_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        smart_button.setToolTip(tr("Switch to the account with the most usable remaining quota"))
        smart_button.clicked.connect(self.smart_pick)
        header.addWidget(smart_button)

        self.update_button = QToolButton()
        set_action_icon(self.update_button, "fa5s.cloud-download-alt")
        self.update_button.setText(tr("Check updates"))
        self.update_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.update_button.setToolTip(tr("Check GitHub for a newer Agent Switcher release"))
        self.update_button.clicked.connect(self.check_for_updates)
        header.addWidget(self.update_button)

        transparency_button = QToolButton()
        set_action_icon(transparency_button, "fa5s.network-wired")
        transparency_button.setToolTip(tr("View network activity"))
        transparency_button.setAccessibleName(tr("Network activity"))
        transparency_button.setAutoRaise(True)
        transparency_button.clicked.connect(self.show_transparency)
        header.addWidget(transparency_button)

        history_button = QToolButton()
        set_action_icon(history_button, "fa5s.history")
        history_button.setToolTip(tr("View switch history"))
        history_button.setAccessibleName(tr("Switch history"))
        history_button.setAutoRaise(True)
        history_button.clicked.connect(self.show_history)
        header.addWidget(history_button)

        settings_button = QToolButton()
        set_action_icon(settings_button, "fa5s.cog")
        settings_button.setToolTip(tr("Settings"))
        settings_button.setAccessibleName(tr("Settings"))
        settings_button.setAutoRaise(True)
        settings_button.clicked.connect(self.show_settings)
        header.addWidget(settings_button)

        self.help_button = QToolButton()
        set_action_icon(self.help_button, "fa5s.question-circle")
        self.help_button.setToolTip(tr("Replay onboarding"))
        self.help_button.setAccessibleName(tr("Replay onboarding"))
        self.help_button.setAutoRaise(True)
        self.help_button.clicked.connect(self.show_onboarding)
        header.addWidget(self.help_button)

        about_button = QToolButton()
        set_action_icon(about_button, "fa5s.info-circle")
        about_button.setToolTip(tr("About"))
        about_button.setAccessibleName(tr("About"))
        about_button.setAutoRaise(True)
        about_button.clicked.connect(self.show_about)
        header.addWidget(about_button)

        add_button = QToolButton()
        set_action_icon(add_button, "fa5s.plus")
        add_button.setText(tr("Add account"))
        add_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        add_button.setToolTip(tr("Add account"))
        add_button.clicked.connect(self.add_profile)
        header.addWidget(add_button)
        layout.addLayout(header)

        self.banner = QFrame()
        self.banner.setFrameShape(QFrame.Shape.StyledPanel)
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(10, 8, 10, 8)
        self.banner_label = QLabel("")
        self.banner_label.setWordWrap(True)
        banner_layout.addWidget(self.banner_label)
        self.banner.hide()
        layout.addWidget(self.banner)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(9)
        self.scroll_area.setWidget(self.list_widget)
        layout.addWidget(self.scroll_area, 1)

        self.footer = QLabel("")
        self.footer.setWordWrap(True)
        self.footer.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        layout.addWidget(self.footer)
        self.setCentralWidget(central)

        self.tray = TrayController(
            self.store,
            self.platform,
            self,
            show_window=self.show_window,
            switch_profile=self.switch_profile,
            add_profile=self.add_profile,
            smart_pick=self.smart_pick,
            show_about=self.show_about,
            quit_app=self.quit_app,
        )
        self.tray.show()
        self.reload()
        self._apply_offline_state()

        self.relative_timer = QTimer(self)
        self.relative_timer.setInterval(60 * 1000)
        self.relative_timer.timeout.connect(self.update_relative_times)
        self.relative_timer.start()

        self.usage_timer = QTimer(self)
        self.usage_timer.setInterval(self.settings.auto_refresh_interval_ms)
        self.usage_timer.timeout.connect(self.refresh_all_usage)
        self.usage_timer.start()
        self.configure_hotkey()
        QTimer.singleShot(0, self.maybe_show_startup_notices)

    def reload(self) -> None:
        expanded = {name for name, row in self.rows.items() if row.expanded}
        self._clear_profiles()
        profiles = self.store.profile_list()
        active = self.store.active()

        if not profiles:
            empty = QLabel(tr("No accounts yet. Add an account to sign in."))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setForegroundRole(QPalette.ColorRole.PlaceholderText)
            self.list_layout.addWidget(empty)
        else:
            for profile in profiles:
                row = ProfileRow(
                    profile,
                    self.switch_profile,
                    self.rename_profile,
                    self.remove_profile,
                    self.copy_debug_info,
                    self.refresh_profile_usage,
                    usage=self.usage_cache.get(profile.name),
                    expanded=profile.name in expanded,
                    offline_mode=self.settings.offline_mode,
                    usage_history=self.store.activity_log.usage_history(profile.name, 20),
                )
                row.set_loading(profile.name in self.usage_inflight)
                self.rows[profile.name] = row
                self.list_layout.addWidget(row)
        self.list_layout.addStretch(1)

        self.footer.setText(
            tr("{count} account(s) | active: {active}", count=len(profiles), active=active or tr("none"))
            + "\n"
            + tr("After switching, close and reopen VS Code.")
        )
        self.tray.rebuild()
        self.update_tray_tooltip()

    def refresh_all_usage(self) -> None:
        if self.settings.offline_mode:
            return
        if self.usage_worker is not None:
            return
        profiles = self.store.profile_list()
        if not profiles:
            return

        self._start_usage_refresh(profiles)

    def refresh_profile_usage(self, name: str) -> None:
        if self.settings.offline_mode:
            self.notify(tr("Offline mode is on. Turn it off in settings to check usage."))
            return
        if self.usage_worker is not None:
            return
        try:
            profile = self.store.profile(name)
        except StoreError as exc:
            self.notify(str(exc))
            return
        self._start_usage_refresh([profile])

    def _start_usage_refresh(self, profiles: list[Profile]) -> None:
        self.refresh_button.setEnabled(False)
        worker = UsageRefreshWorker(self.store, profiles, self.settings.request_delay_ms)
        self.usage_worker = worker
        worker.profile_started.connect(self.on_usage_started)
        worker.egress_attention.connect(self.on_usage_egress_attention)
        worker.usage_ready.connect(self.on_usage_ready)
        worker.finished.connect(self.on_usage_refresh_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def on_usage_egress_attention(self, result: object) -> None:
        if self.usage_worker is not None:
            self.usage_worker.resolve_egress(
                confirm_egress(self.store, result, self, self.suppress_ip_guard_warnings)
            )

    def on_usage_started(self, name: str) -> None:
        self.usage_inflight.add(name)
        row = self.rows.get(name)
        if row is not None:
            row.set_loading(True)

    def on_usage_ready(self, name: str, usage: Usage) -> None:
        self.usage_inflight.discard(name)
        previous_usage = self.usage_cache.get(name)
        self.usage_cache[name] = usage
        self.maybe_warn_low_quota(name, previous_usage, usage)
        row = self.rows.get(name)
        if row is not None:
            row.set_loading(False)
            row.update_usage(usage)
            row.update_usage_history(self.store.activity_log.usage_history(name, 20))
        if name == self.store.active():
            self.update_tray_tooltip()

    def on_usage_refresh_finished(self) -> None:
        for name in self.usage_inflight:
            row = self.rows.get(name)
            if row is not None:
                row.set_loading(False)
        self.usage_inflight.clear()
        self.refresh_button.setEnabled(True)
        self.usage_worker = None
        self._apply_offline_state()
        self.update_tray_tooltip()
        if self.smart_pick_pending:
            self.smart_pick_pending = False
            self.complete_smart_pick()

    def update_relative_times(self) -> None:
        for row in self.rows.values():
            row.update_relative_time()

    def update_tray_tooltip(self) -> None:
        active = self.store.active()
        self.tray.update_tooltip(active, self.usage_cache.get(active) if active else None)

    def switch_profile(self, name: str) -> None:
        if self.switch_egress_worker is not None:
            self.notify(tr("A network safety check is already in progress."))
            return
        running = self.store.running_processes()
        if running:
            answer = show_message(
                self,
                QMessageBox.Icon.Warning,
                tr("Codex is still running"),
                tr(
                    "Codex or its VS Code extension is still open. It may restore the previous login after the switch.\n\n"
                    "For a reliable switch, close Codex and VS Code first. You can also continue if you understand the risk."
                ),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
                {
                    QMessageBox.StandardButton.Ok: "Switch anyway",
                    QMessageBox.StandardButton.Cancel: "Cancel",
                },
            )
            if answer != QMessageBox.StandardButton.Ok:
                return

        self.pending_switch = name
        worker = EgressCheckWorker(self.store, name, "account_switch")
        self.switch_egress_worker = worker
        worker.checked.connect(self.on_switch_egress_checked)
        worker.finished.connect(self.on_switch_egress_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def on_switch_egress_checked(self, result: object) -> None:
        name = self.pending_switch
        if name is None or result.profile != name:
            return
        if not confirm_egress(self.store, result, self, self.suppress_ip_guard_warnings):
            self.pending_switch = None
            return
        self._complete_switch(name)
        self.pending_switch = None

    def on_switch_egress_finished(self) -> None:
        self.switch_egress_worker = None

    def _complete_switch(self, name: str) -> None:

        try:
            previous = self.store.switch(name)
        except StoreError as exc:
            show_message(self, QMessageBox.Icon.Critical, tr("Switch failed"), tr(str(exc)))
            return

        self.reload()
        self.notify(
            tr(
                "Switched {previous} to {profile}. Close and reopen VS Code to pick it up.",
                previous=previous or tr("none"),
                profile=name,
            )
        )

    def add_profile(self) -> None:
        dialog = AddAccountDialog(
            self.store,
            self,
            on_suppress_ip_guard=self.suppress_ip_guard_warnings,
        )
        if dialog.exec() == AddAccountDialog.DialogCode.Accepted:
            name = dialog.result_name or tr("new account")
            self.reload()
            self.notify(tr("Added {profile} and made it active. Reopen VS Code to use it.", profile=name))
            self.refresh_all_usage()

    def rename_profile(self, name: str) -> None:
        new_name, ok = TextPrompt.get_text(self, tr("Rename account"), tr("New name:"), name)
        if not ok or not new_name or new_name == name:
            return
        try:
            self.store.rename(name, new_name)
        except StoreError as exc:
            show_message(self, QMessageBox.Icon.Critical, tr("Rename failed"), tr(str(exc)))
            return
        if name in self.usage_cache:
            self.usage_cache[new_name] = self.usage_cache.pop(name)
        self.reload()

    def remove_profile(self, name: str) -> None:
        answer = show_message(
            self,
            QMessageBox.Icon.Question,
            tr("Remove {profile}?", profile=name),
            tr("This deletes the saved credential file only. The upstream account is untouched."),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        try:
            self.store.delete(name)
        except StoreError as exc:
            show_message(self, QMessageBox.Icon.Critical, tr("Remove failed"), tr(str(exc)))
            return
        self.usage_cache.pop(name, None)
        self.reload()

    def copy_debug_info(self, profile: Profile) -> None:
        debug = self.store.profile_debug_info(profile)
        account_id = debug.account_id or tr("unavailable")
        QApplication.clipboard().setText(f"account_id: {account_id}\nprofile_path: {debug.path}")
        self.notify(tr("Copied debug info for {profile}.", profile=profile.name))

    def show_transparency(self) -> None:
        TransparencyDialog(self.store.activity_log, self).exec()

    def show_history(self) -> None:
        HistoryDialog(self.store.activity_log, self).exec()

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def check_for_updates(self) -> None:
        if self.update_check_worker is not None or self.update_download_worker is not None:
            return
        self.update_button.setEnabled(False)
        self.update_button.setText(tr("Checking..."))
        self.notify(tr("Checking for Agent Switcher updates..."))
        worker = UpdateCheckWorker(self.store)
        self.update_check_worker = worker
        worker.checked.connect(self.on_update_checked)
        worker.failed.connect(self.on_update_check_failed)
        worker.finished.connect(self.on_update_check_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def on_update_checked(self, info: object) -> None:
        if info is None:
            self.notify(tr("Agent Switcher {version} is up to date.", version=__version__))
            return
        dialog = UpdateAvailableDialog(info, automatic_install_supported(), self)
        dialog.exec()
        if dialog.action == "install":
            self.start_update_download(info)
        elif dialog.action == "open_release" and info.release_url:
            QDesktopServices.openUrl(QUrl(info.release_url))

    def on_update_check_failed(self, error: str) -> None:
        show_message(
            self,
            QMessageBox.Icon.Warning,
            tr("Update check failed"),
            tr("Agent Switcher could not check for updates.\n\n{error}", error=error),
        )

    def on_update_check_finished(self) -> None:
        self.update_check_worker = None
        self.update_button.setEnabled(True)
        self.update_button.setText(tr("Check updates"))

    def start_update_download(self, info: object) -> None:
        if self.update_download_worker is not None:
            return
        progress = UpdateProgressDialog(info.latest_version, self)
        self.update_progress_dialog = progress
        progress.show()
        worker = UpdateDownloadWorker(self.store, info)
        self.update_download_worker = worker
        worker.progress_changed.connect(progress.set_progress)
        worker.prepared.connect(self.on_update_prepared)
        worker.failed.connect(self.on_update_download_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def on_update_prepared(self, prepared: object) -> None:
        if self.update_progress_dialog is not None:
            self.update_progress_dialog.set_installing()
        try:
            launch_update_helper(prepared)
        except Exception as exc:
            self.on_update_download_failed(str(exc) or type(exc).__name__)
            return
        QTimer.singleShot(0, self.quit_app)

    def on_update_download_failed(self, error: str) -> None:
        if self.update_progress_dialog is not None:
            self.update_progress_dialog.close()
            self.update_progress_dialog = None
        self.update_download_worker = None
        show_message(
            self,
            QMessageBox.Icon.Critical,
            tr("Update installation failed"),
            tr("The update was not installed. Your current version is unchanged.\n\n{error}", error=error),
        )

    def show_settings(self) -> None:
        dialog = SettingsDialog(
            self.settings.offline_mode,
            self.settings.low_quota_threshold_pct,
            self.settings.smart_pick_stale_minutes,
            self.settings.smart_pick_headroom_pct,
            self.settings.global_hotkey_enabled,
            self.settings.global_hotkey,
            self.settings.theme,
            self.settings.language,
            self.settings.proxy_mode,
            self.settings.proxy_url,
            self.settings.ip_guard_enabled,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        previous = self.settings.offline_mode
        previous_language = self.settings.language
        proxy_config = dialog.proxy_config()
        self.settings = replace(
            self.settings,
            offline_mode=dialog.offline_checkbox.isChecked(),
            ip_guard_enabled=dialog.ip_guard_checkbox.isChecked(),
            low_quota_threshold_pct=dialog.low_quota_threshold.value(),
            smart_pick_stale_minutes=dialog.smart_pick_stale.value(),
            smart_pick_headroom_pct=dialog.smart_pick_headroom.value(),
            global_hotkey_enabled=dialog.hotkey_enabled.isChecked(),
            global_hotkey=dialog.hotkey_edit.text().strip() or self.settings.global_hotkey,
            theme=str(dialog.theme_combo.currentData()),
            language=str(dialog.language_combo.currentData()),
            proxy_mode=proxy_config.mode,
            proxy_url=proxy_config.url,
        )
        self.store.set_proxy_config(proxy_config)
        self.store.set_egress_guard_enabled(self.settings.ip_guard_enabled)
        self.settings_store.save(self.settings)
        apply_theme(QApplication.instance(), self.settings.theme)
        self.configure_hotkey()
        if self.settings.offline_mode and self.usage_worker is not None:
            self.usage_worker.requestInterruption()
        self._apply_offline_state()
        self.reload()
        if previous_language != self.settings.language:
            if ask_restart(
                self,
                tr("Restart required"),
                tr("Restart the app after changing language to fully apply text direction and translations."),
            ):
                self.restart_app()
                return
        if previous and not self.settings.offline_mode:
            self.refresh_all_usage()

    def suppress_ip_guard_warnings(self) -> None:
        self.settings = replace(self.settings, ip_guard_enabled=False)
        self.store.set_egress_guard_enabled(False)
        self.settings_store.save(self.settings)

    def maybe_warn_low_quota(
        self,
        name: str,
        previous_usage: Optional[Usage],
        current_usage: Usage,
    ) -> None:
        if name != self.store.active():
            return
        current = self.minimum_remaining(current_usage)
        previous = self.minimum_remaining(previous_usage)
        if previous is None:
            history = self.store.activity_log.usage_history(name, 2)
            if len(history) > 1:
                previous = self.remaining_from_payload(history[1].get("payload", {}))
        if self.crossed_below(previous, current, self.settings.low_quota_threshold_pct):
            self.tray.show_low_quota_warning(name, current)

    @staticmethod
    def minimum_remaining(usage: Optional[Usage]) -> Optional[float]:
        if usage is None or not usage.available:
            return None
        values = [
            100.0 - value
            for value in (usage.five_hour_used_pct, usage.weekly_used_pct)
            if value is not None
        ]
        return min(values) if values else None

    @staticmethod
    def remaining_from_payload(payload: dict) -> Optional[float]:
        values = [
            100.0 - float(value)
            for value in (payload.get("five_hour_used_pct"), payload.get("weekly_used_pct"))
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        return min(values) if values else None

    @staticmethod
    def crossed_below(previous: Optional[float], current: Optional[float], threshold: float) -> bool:
        return previous is not None and current is not None and previous >= threshold and current < threshold

    def smart_pick(self) -> None:
        if self.usage_worker is not None:
            self.notify(tr("A usage refresh is already in progress. Try Smart pick again when it finishes."))
            return
        active = self.store.active()
        candidates = [name for name in self.store.profiles() if name != active]
        if not candidates:
            self.notify(tr("No other saved profile is available for Smart pick."))
            return
        max_age = timedelta(minutes=self.settings.smart_pick_stale_minutes)
        stale = stale_usage_profiles(self.store.activity_log, candidates, max_age=max_age)
        if stale:
            if self.settings.offline_mode:
                self.notify(tr("Offline mode is on, so stale usage data cannot be refreshed for Smart pick."))
                return
            profiles = [self.store.profile(name) for name in stale]
            self.smart_pick_pending = True
            self.notify(tr("Refreshing stale usage data before Smart pick..."))
            self._start_usage_refresh(profiles)
            return
        self.complete_smart_pick()

    def complete_smart_pick(self) -> None:
        result = choose_smart_profile(
            self.store.activity_log,
            self.store.profiles(),
            active=self.store.active(),
            minimum_headroom_pct=self.settings.smart_pick_headroom_pct,
            max_age=timedelta(minutes=self.settings.smart_pick_stale_minutes),
        )
        if result.profile_name is None:
            self.notify(tr(result.reason or "No profile has usable usage data for Smart pick."))
            return
        self.switch_profile(result.profile_name)

    def configure_hotkey(self) -> None:
        if self.hotkey_controller is not None:
            self.hotkey_controller.stop()
            self.hotkey_controller.deleteLater()
            self.hotkey_controller = None
        if not self.settings.global_hotkey_enabled:
            return
        controller = GlobalHotkeyController(
            self.store.activity_log,
            self.show_quick_switch,
            self.settings.global_hotkey,
            parent=self,
        )
        self.hotkey_controller = controller
        if not controller.start():
            self.notify(
                tr("The global hotkey could not be registered. Check the shortcut or desktop permissions.")
            )

    def show_quick_switch(self) -> None:
        if self.quick_switch_popup is not None:
            self.quick_switch_popup.close()
        popup = QuickSwitchPopup(self.store, self.tray.tray, self.switch_profile)
        self.quick_switch_popup = popup
        popup.finished.connect(lambda _result: setattr(self, "quick_switch_popup", None))
        popup.show()

    def _apply_offline_state(self) -> None:
        offline = self.settings.offline_mode
        self.refresh_button.setEnabled(not offline and self.usage_worker is None)
        self.refresh_button.setToolTip(
            tr("Offline mode is on - turn it off in settings to check usage")
            if offline
            else tr("Refresh usage for all accounts")
        )
        for row in self.rows.values():
            row.set_offline_mode(offline)

    def notify(self, text: str) -> None:
        self.banner_label.setText(text)
        self.banner.show()

    def show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def maybe_show_onboarding(self) -> None:
        if self.settings.onboarding_seen or self.store.profiles():
            return
        self.settings = replace(self.settings, onboarding_seen=True)
        self.settings_store.save(self.settings)

        self.show_onboarding()

    def maybe_show_startup_notices(self) -> None:
        if not self.settings.privacy_notice_suppressed:
            dialog = PrivacyNoticeDialog(self)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            if accepted and dialog.dont_show_again.isChecked():
                self.settings = replace(self.settings, privacy_notice_suppressed=True)
                self.settings_store.save(self.settings)
        QTimer.singleShot(0, self.maybe_show_onboarding)

    def show_onboarding(self) -> None:
        if self.onboarding_dialog is not None:
            self.onboarding_dialog.show()
            self.onboarding_dialog.raise_()
            self.onboarding_dialog.activateWindow()
            return
        dialog = OnboardingDialog(
            self.store,
            self.reload,
            self,
            on_suppress_ip_guard=self.suppress_ip_guard_warnings,
        )
        self.onboarding_dialog = dialog
        dialog.finished.connect(self._onboarding_finished)
        dialog.show()

    def _onboarding_finished(self, _result: int) -> None:
        self.onboarding_dialog = None
        self.reload()

    def quit_app(self) -> None:
        if self.hotkey_controller is not None:
            self.hotkey_controller.stop()
        if self.usage_worker is not None and self.usage_worker.isRunning():
            self.usage_worker.requestInterruption()
            self.usage_worker.wait(6000)
        if self.switch_egress_worker is not None and self.switch_egress_worker.isRunning():
            self.switch_egress_worker.requestInterruption()
            self.switch_egress_worker.wait(9000)
        self.tray.tray.hide()
        QApplication.quit()

    def restart_app(self) -> None:
        if getattr(sys, "frozen", False):
            program = sys.executable
            arguments = []
        else:
            program = sys.executable
            arguments = ["-m", "agent_switcher.gui"]
        result = QProcess.startDetached(program, arguments)
        started = result[0] if isinstance(result, tuple) else bool(result)
        if not started:
            show_message(
                self,
                QMessageBox.Icon.Critical,
                tr("Restart failed"),
                tr("The app could not start a new process. Please restart it manually."),
            )
            return
        self.quit_app()

    def closeEvent(self, event) -> None:
        self.platform.handle_main_window_close(self, event)

    def _clear_profiles(self) -> None:
        self.rows.clear()
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()


class TextPrompt(QDialog):
    def __init__(self, title: str, label: str, value: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.edit = QLineEdit(value)

        _surface, layout = create_shadowed_surface(self)
        layout.addWidget(QLabel(label))
        layout.addWidget(self.edit)
        buttons = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        set_action_icon(cancel, "fa5s.times")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        ok = QPushButton(tr("Rename"))
        set_action_icon(ok, "fa5s.pen")
        ok.clicked.connect(self.accept)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    @classmethod
    def get_text(cls, parent: QWidget, title: str, label: str, value: str) -> tuple[str, bool]:
        dialog = cls(title, label, value, parent)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.edit.text().strip(), accepted

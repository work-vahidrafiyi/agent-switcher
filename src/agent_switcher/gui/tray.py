from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from agent_switcher.core.store import Store
from agent_switcher.core.usage import Usage

from .platform import PlatformIntegration
from .icons import set_action_icon
from .i18n import tr


class TrayController:
    def __init__(
        self,
        store: Store,
        platform: PlatformIntegration,
        parent: QWidget,
        show_window: Callable[[], None],
        switch_profile: Callable[[str], None],
        add_profile: Callable[[], None],
        smart_pick: Callable[[], None],
        show_about: Callable[[], None],
        quit_app: Callable[[], None],
    ) -> None:
        self.store = store
        self.platform = platform
        self.parent = parent
        self.show_window = show_window
        self.switch_profile = switch_profile
        self.add_profile = add_profile
        self.smart_pick = smart_pick
        self.show_about = show_about
        self.quit_app = quit_app
        self.tray = QSystemTrayIcon(platform.app_icon(), parent)
        self.tray.setToolTip(tr("Agent Switcher"))
        self.tray.activated.connect(self.on_activated)

    def show(self) -> None:
        if self.platform.tray_available():
            self.rebuild()
            self.tray.show()

    def rebuild(self) -> None:
        menu = QMenu(self.parent)
        active = self.store.active()

        for profile in self.store.profile_list():
            action = QAction(profile.name, menu)
            action.setCheckable(True)
            action.setChecked(profile.name == active)
            action.setEnabled(profile.name != active)
            action.triggered.connect(lambda _checked=False, name=profile.name: self.switch_profile(name))
            menu.addAction(action)

        if self.store.profiles():
            menu.addSeparator()

        add_action = QAction(tr("Add account..."), menu)
        set_action_icon(add_action, "fa5s.plus")
        add_action.triggered.connect(self.add_profile)
        menu.addAction(add_action)

        smart_action = QAction(tr("Smart pick"), menu)
        set_action_icon(smart_action, "fa5s.magic")
        smart_action.triggered.connect(self.smart_pick)
        menu.addAction(smart_action)

        open_action = QAction(tr("Open Agent Switcher"), menu)
        set_action_icon(open_action, "fa5s.window-restore")
        open_action.triggered.connect(self.show_window)
        menu.addAction(open_action)

        about_action = QAction(tr("About"), menu)
        set_action_icon(about_action, "fa5s.info-circle")
        about_action.triggered.connect(self.show_about)
        menu.addAction(about_action)

        menu.addSeparator()
        quit_action = QAction(tr("Quit"), menu)
        set_action_icon(quit_action, "fa5s.power-off")
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)

    def on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def update_tooltip(self, active: Optional[str], usage: Optional[Usage]) -> None:
        self.tray.setToolTip(self.tooltip_text(active, usage))

    def show_low_quota_warning(self, profile: str, remaining: float) -> None:
        self.tray.showMessage(
            tr("Low Codex quota"),
            tr(
                "{profile} has {remaining}% remaining. Consider checking another account.",
                profile=profile,
                remaining=f"{remaining:g}",
            ),
            QSystemTrayIcon.MessageIcon.Warning,
            8000,
        )

    @staticmethod
    def tooltip_text(active: Optional[str], usage: Optional[Usage]) -> str:
        if not active:
            return tr("Agent Switcher - no active profile")
        if (
            usage is None
            or not usage.available
            or usage.five_hour_used_pct is None
            or usage.weekly_used_pct is None
        ):
            return tr("{profile} - usage unknown", profile=active)
        five_hour_left = max(0.0, min(100.0, 100.0 - usage.five_hour_used_pct))
        weekly_left = max(0.0, min(100.0, 100.0 - usage.weekly_used_pct))
        return tr(
            "{profile} - {five}% left (5h), {weekly}% left (weekly)",
            profile=active,
            five=f"{five_hour_left:g}",
            weekly=f"{weekly_left:g}",
        )

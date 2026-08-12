from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget

from agent_switcher.core.store import Store

from .i18n import tr


class QuickSwitchPopup(QDialog):
    def __init__(
        self,
        store: Store,
        tray: QSystemTrayIcon,
        switch_profile: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setWindowTitle(tr("Quick switch"))
        self.setObjectName("quickSwitchPopup")
        self.setMinimumWidth(280)
        self.setStyleSheet(
            "#quickSwitchPopup { border: 1px solid palette(mid); border-radius: 12px; }"
            " QToolButton { min-height: 34px; padding: 5px 10px; text-align: left; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(7)
        heading = QLabel(tr("Switch account"))
        font = heading.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        heading.setFont(font)
        layout.addWidget(heading)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)
        active = store.active()
        profiles = store.profile_list()
        if not profiles:
            empty = QLabel(tr("No accounts yet. Add an account to sign in."))
            empty.setWordWrap(True)
            layout.addWidget(empty)
        for profile in profiles:
            button = QToolButton()
            marker = "  ✓" if profile.name == active else ""
            button.setText(profile.name + marker)
            button.setToolTip(tr("Active") if profile.name == active else tr("Switch to this account"))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setEnabled(profile.name != active)
            button.clicked.connect(lambda _checked=False, name=profile.name: self._choose(name, switch_profile))
            layout.addWidget(button)
        self.adjustSize()
        geometry = tray.geometry()
        anchor = geometry.center() if not geometry.isNull() else QCursor.pos()
        self.move(QPoint(anchor.x() - self.width() // 2, anchor.y() - self.height()))
        self.activateWindow()

    def _choose(self, name: str, switch_profile: Callable[[str], None]) -> None:
        self.close()
        switch_profile(name)

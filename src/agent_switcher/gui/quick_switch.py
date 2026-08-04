from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QDialog, QLabel, QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget

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
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(tr("Quick switch"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(QLabel(tr("Switch account")))
        active = store.active()
        for profile in store.profile_list():
            button = QToolButton()
            button.setText(profile.name + (f" ({tr('Active')})" if profile.name == active else ""))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setEnabled(profile.name != active)
            button.clicked.connect(lambda _checked=False, name=profile.name: self._choose(name, switch_profile))
            layout.addWidget(button)
        self.adjustSize()
        geometry = tray.geometry()
        anchor = geometry.center() if not geometry.isNull() else QCursor.pos()
        self.move(QPoint(anchor.x() - self.width() // 2, anchor.y() - self.height()))

    def _choose(self, name: str, switch_profile: Callable[[str], None]) -> None:
        self.close()
        switch_profile(name)

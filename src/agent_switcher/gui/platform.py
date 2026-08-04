from __future__ import annotations

from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QStyle, QSystemTrayIcon, QWidget


class PlatformIntegration:
    """Swappable desktop integration points for future platform overrides."""

    def __init__(self, app: QApplication) -> None:
        self.app = app

    def configure_application(self) -> None:
        self.app.setQuitOnLastWindowClosed(False)

    def tray_available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def app_icon(self) -> QIcon:
        return self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def handle_main_window_close(self, window: QWidget, event: QCloseEvent) -> None:
        if self.tray_available():
            window.hide()
            event.ignore()
        else:
            event.accept()


def create_platform(app: QApplication) -> PlatformIntegration:
    return PlatformIntegration(app)

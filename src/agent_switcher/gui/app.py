from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QApplication

from agent_switcher.core.providers.codex import CodexProvider
from agent_switcher.core.store import Store

from .main_window import MainWindow
from .platform import create_platform
from .settings import SettingsStore
from .theme import apply_theme
from .i18n import configure_i18n


def main(argv: Optional[list[str]] = None) -> int:
    app = QApplication(list(sys.argv if argv is None else argv))
    store = Store(CodexProvider())
    store.home.mkdir(parents=True, exist_ok=True)
    settings_store = SettingsStore(store.activity_log.path.parent / "settings.json")
    settings = settings_store.load()
    configure_i18n(app, settings.language)
    apply_theme(app, settings.theme)
    platform = create_platform(app)
    platform.configure_application()

    window = MainWindow(store, platform, settings=settings, settings_store=settings_store)
    window.show()
    return app.exec()

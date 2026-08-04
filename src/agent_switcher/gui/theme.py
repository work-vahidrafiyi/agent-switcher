from __future__ import annotations

import re
from typing import Literal

import qdarktheme
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


ThemePreference = Literal["system", "dark", "light"]

_CHECKABLE_HOVER_BORDER = re.compile(
    r"QCheckBox:hover,QRadioButton:hover\s*\{[^}]*border-bottom:[^;}]+;?[^}]*\}"
)
_current_theme: ThemePreference = "system"


def apply_theme(app: QApplication, theme: ThemePreference = "system") -> None:
    global _current_theme
    _current_theme = theme
    qdarktheme.setup_theme("auto" if theme == "system" else theme)

    # qdarktheme draws a bottom border across hovered checkbox/radio labels.
    # Remove that source rule instead of layering another widget override on top.
    stylesheet = _CHECKABLE_HOVER_BORDER.sub("", app.styleSheet())
    app.setStyleSheet(stylesheet)

    # Existing QIcons keep their old pixmaps after a live theme change.
    from .icons import refresh_action_icons

    refresh_action_icons(app)


def action_icon_color() -> QColor:
    palette = qdarktheme.load_palette("auto" if _current_theme == "system" else _current_theme)
    return palette.color(QPalette.ColorRole.Text)

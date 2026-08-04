from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .theme import action_icon_color


_ICON_PROPERTY = "agentSwitcherIconName"


def action_icon(name: str) -> QIcon:
    return qta.icon(name, color=action_icon_color())


def set_action_icon(target: QObject, name: str) -> None:
    target.setProperty(_ICON_PROPERTY, name)
    target.setIcon(action_icon(name))


def refresh_action_icons(app: QApplication) -> None:
    for widget in app.allWidgets():
        name = widget.property(_ICON_PROPERTY)
        if isinstance(name, str) and name:
            widget.setIcon(action_icon(name))

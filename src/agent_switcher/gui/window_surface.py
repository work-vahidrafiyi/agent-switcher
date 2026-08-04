from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QVBoxLayout,
    QWidget,
)


def create_shadowed_surface(
    parent: QWidget,
    *,
    outer_margin: int = 10,
) -> tuple[QFrame, QVBoxLayout]:
    outer = QVBoxLayout(parent)
    outer.setContentsMargins(outer_margin, outer_margin, outer_margin, outer_margin)

    surface = QFrame(parent)
    surface.setFrameShape(QFrame.Shape.StyledPanel)
    shadow = QGraphicsDropShadowEffect(surface)
    shadow_color = surface.palette().color(QPalette.ColorRole.Shadow)
    shadow.setColor(QColor(shadow_color.red(), shadow_color.green(), shadow_color.blue(), 125))
    shadow.setBlurRadius(18)
    shadow.setOffset(0, 3)
    surface.setGraphicsEffect(shadow)
    outer.addWidget(surface)

    return surface, QVBoxLayout(surface)

from __future__ import annotations

from typing import Mapping, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .window_surface import create_shadowed_surface


_BUTTON_LABELS = {
    QMessageBox.StandardButton.Ok: "OK",
    QMessageBox.StandardButton.Cancel: "Cancel",
    QMessageBox.StandardButton.Yes: "Yes",
    QMessageBox.StandardButton.No: "No",
}

_ICON_PIXMAPS = {
    QMessageBox.Icon.Information: QStyle.StandardPixmap.SP_MessageBoxInformation,
    QMessageBox.Icon.Warning: QStyle.StandardPixmap.SP_MessageBoxWarning,
    QMessageBox.Icon.Critical: QStyle.StandardPixmap.SP_MessageBoxCritical,
    QMessageBox.Icon.Question: QStyle.StandardPixmap.SP_MessageBoxQuestion,
}


class MessageDialog(QDialog):
    """A compact themed alternative to platform-dependent QMessageBox UI."""

    def __init__(
        self,
        parent: QWidget,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton,
        default: Optional[QMessageBox.StandardButton],
        labels: Optional[Mapping[QMessageBox.StandardButton, str]] = None,
        checkbox_label: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setMaximumWidth(640)
        self.selected = self._close_result(buttons)

        _surface, root = create_shadowed_surface(self, outer_margin=8)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        content = QHBoxLayout()
        content.setSpacing(14)
        icon_label = QLabel()
        standard_pixmap = _ICON_PIXMAPS.get(icon)
        if standard_pixmap is not None:
            icon_label.setPixmap(self.style().standardIcon(standard_pixmap).pixmap(36, 36))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            content.addWidget(icon_label)

        copy = QVBoxLayout()
        copy.setSpacing(6)
        heading = QLabel(title)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSize(heading_font.pointSize() + 2)
        heading.setFont(heading_font)
        copy.addWidget(heading)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        copy.addWidget(body)
        content.addLayout(copy, 1)
        root.addLayout(content)

        self.checkbox: Optional[QCheckBox] = None
        if checkbox_label:
            self.checkbox = QCheckBox(tr(checkbox_label))
            root.addWidget(self.checkbox)

        actions = QHBoxLayout()
        actions.addStretch(1)
        default_widget: Optional[QPushButton] = None
        for standard in _BUTTON_LABELS:
            if not (buttons & standard):
                continue
            button = QPushButton(tr((labels or {}).get(standard, _BUTTON_LABELS[standard])))
            button.setMinimumWidth(92)
            button.clicked.connect(lambda _checked=False, value=standard: self._choose(value))
            actions.addWidget(button)
            if standard == default:
                default_widget = button
        root.addLayout(actions)
        if default_widget is not None:
            default_widget.setDefault(True)
            default_widget.setFocus()

    @staticmethod
    def _close_result(buttons: QMessageBox.StandardButton) -> QMessageBox.StandardButton:
        for fallback in (
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Yes,
        ):
            if buttons & fallback:
                return fallback
        return QMessageBox.StandardButton.NoButton

    def _choose(self, value: QMessageBox.StandardButton) -> None:
        self.selected = value
        self.accept()

    def checkbox_checked(self) -> bool:
        return self.checkbox is not None and self.checkbox.isChecked()


def show_message(
    parent: QWidget,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default: Optional[QMessageBox.StandardButton] = None,
    labels: Optional[Mapping[QMessageBox.StandardButton, str]] = None,
) -> QMessageBox.StandardButton:
    dialog = MessageDialog(parent, icon, title, text, buttons, default, labels)
    dialog.exec()
    return dialog.selected


def ask_restart(parent: QWidget, title: str, text: str) -> bool:
    dialog = MessageDialog(
        parent,
        QMessageBox.Icon.Information,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
        {
            QMessageBox.StandardButton.Yes: "Restart now",
            QMessageBox.StandardButton.No: "Later",
        },
    )
    dialog.exec()
    return dialog.selected == QMessageBox.StandardButton.Yes

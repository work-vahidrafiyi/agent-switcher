from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from .i18n import tr


def show_message(
    parent: QWidget,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default: Optional[QMessageBox.StandardButton] = None,
) -> QMessageBox.StandardButton:
    box = QMessageBox(icon, title, text, buttons, parent)
    if default is not None:
        box.setDefaultButton(default)
    labels = {
        QMessageBox.StandardButton.Ok: tr("OK"),
        QMessageBox.StandardButton.Cancel: tr("Cancel"),
        QMessageBox.StandardButton.Yes: tr("Yes"),
        QMessageBox.StandardButton.No: tr("No"),
    }
    for standard_button, label in labels.items():
        button = box.button(standard_button)
        if button is not None:
            button.setText(label)
    return QMessageBox.StandardButton(box.exec())


def ask_restart(parent: QWidget, title: str, text: str) -> bool:
    box = QMessageBox(QMessageBox.Icon.Information, title, text, parent=parent)
    restart_button = box.addButton(tr("Restart now"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(tr("Later"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(restart_button)
    box.exec()
    return box.clickedButton() is restart_button

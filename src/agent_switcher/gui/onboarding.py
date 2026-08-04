from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agent_switcher.core.store import Store

from .add_dialog import AddAccountDialog
from .icons import set_action_icon
from .window_surface import create_shadowed_surface
from .i18n import tr


class OnboardingDialog(QDialog):
    def __init__(
        self,
        store: Store,
        on_account_added: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.on_account_added = on_account_added
        self.setWindowTitle(tr("Welcome to Agent Switcher"))
        self.setModal(False)
        self.resize(620, 420)

        _surface, root = create_shadowed_surface(self)
        root.setContentsMargins(24, 22, 24, 20)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._welcome_page())
        self.pages.addWidget(self._account_page())
        self.pages.addWidget(self._done_page())
        root.addWidget(self.pages)

    def _welcome_page(self) -> QWidget:
        page, layout = self._page(
            tr("Welcome"),
            tr("Switch between saved Codex accounts without replacing credentials by hand."),
        )
        layout.addStretch(1)
        buttons = QHBoxLayout()
        skip = QPushButton(tr("Skip"))
        skip.clicked.connect(self.reject)
        buttons.addWidget(skip)
        buttons.addStretch(1)
        start = QPushButton(tr("Get started"))
        set_action_icon(start, "fa5s.arrow-right")
        start.clicked.connect(self.show_account_step)
        buttons.addWidget(start)
        layout.addLayout(buttons)
        return page

    def _account_page(self) -> QWidget:
        page, layout = self._page(
            tr("Add your first account"),
            tr("Sign in through your browser or use a device code. You can add more accounts later."),
        )
        layout.addStretch(1)
        add = QPushButton(tr("Add account"))
        set_action_icon(add, "fa5s.plus")
        add.clicked.connect(self.launch_add_account)
        layout.addWidget(add)
        skip = QPushButton(tr("Skip for now"))
        skip.clicked.connect(self.reject)
        layout.addWidget(skip)
        return page

    def _done_page(self) -> QWidget:
        page, layout = self._page(
            tr("You're set up"),
            tr("Use the account rows or tray menu to switch. Settings and usage refresh are available from the header."),
        )
        layout.addStretch(1)
        done = QPushButton(tr("Done"))
        set_action_icon(done, "fa5s.check")
        done.clicked.connect(self.accept)
        layout.addWidget(done, 0, Qt.AlignmentFlag.AlignTrailing)
        return page

    @staticmethod
    def _page(title: str, body: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        font = heading.font()
        font.setPointSize(20)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        description = QLabel(body)
        description.setWordWrap(True)
        layout.addWidget(description)
        return page, layout

    def show_account_step(self) -> None:
        self.pages.setCurrentIndex(1)

    def show_done_step(self) -> None:
        self.pages.setCurrentIndex(2)

    def launch_add_account(self) -> None:
        dialog = AddAccountDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.on_account_added()
            self.show_done_step()

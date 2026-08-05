from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .icons import set_action_icon
from .window_surface import create_shadowed_surface


_GUIDES = {
    "settings": (
        "Settings",
        [
            ("Usage controls", "Offline mode stops quota checks without disabling login or switching."),
            ("Network route", "Choose a direct connection or set an HTTP proxy for app requests."),
            ("Appearance", "Theme changes apply immediately. Language changes fully apply after restart."),
            ("Automation", "Warning thresholds, Smart pick freshness, and the global hotkey are configured here."),
        ],
    ),
    "add_account": (
        "Add account",
        [
            ("Choose a sign-in method", "Browser sign-in is the default. Device code is available for remote sessions."),
            ("Manual fallback", "If the browser does not open, use the captured link. Device mode also shows a one-time code."),
            ("Troubleshooting", "Raw output shows the underlying Codex login process without changing the login logic."),
        ],
    ),
    "network": (
        "Network activity",
        [
            ("What this view shows", "Each row records an outbound request made by the app."),
            ("Why a request happened", "Purpose identifies login, usage checks, or token refresh. Endpoint shows where it went."),
            ("Check the result", "Success or failure is recorded locally so unexpected network activity can be reviewed."),
        ],
    ),
    "history": (
        "Switch history",
        [
            ("Recent switches", "This view lists account switches from newest to oldest."),
            ("From and to", "Each row shows the previous and selected profile with its local timestamp."),
        ],
    ),
}


class SectionGuideDialog(QDialog):
    def __init__(self, topic: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        section, steps = _GUIDES[topic]
        self.setWindowTitle(tr("Guide: {section}", section=tr(section)))
        self.setModal(True)
        self.resize(560, 360)

        _surface, root = create_shadowed_surface(self)
        root.setContentsMargins(22, 20, 22, 18)
        self.pages = QStackedWidget()
        for title, body in steps:
            self.pages.addWidget(self._page(tr(title), tr(body)))
        root.addWidget(self.pages, 1)

        footer = QHBoxLayout()
        self.position_label = QLabel()
        footer.addWidget(self.position_label)
        footer.addStretch(1)
        self.back_button = QPushButton(tr("Back"))
        set_action_icon(self.back_button, "fa5s.arrow-left")
        self.back_button.clicked.connect(self.back)
        footer.addWidget(self.back_button)
        self.next_button = QPushButton()
        self.next_button.clicked.connect(self.next)
        footer.addWidget(self.next_button)
        root.addLayout(footer)
        self._update_navigation()

    @staticmethod
    def _page(title: str, body: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        font = heading.font()
        font.setPointSize(17)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        description = QLabel(body)
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addStretch(1)
        return page

    def back(self) -> None:
        self.pages.setCurrentIndex(max(0, self.pages.currentIndex() - 1))
        self._update_navigation()

    def next(self) -> None:
        if self.pages.currentIndex() == self.pages.count() - 1:
            self.accept()
            return
        self.pages.setCurrentIndex(self.pages.currentIndex() + 1)
        self._update_navigation()

    def _update_navigation(self) -> None:
        index = self.pages.currentIndex()
        self.position_label.setText(
            tr("Step {current} of {total}", current=index + 1, total=self.pages.count())
        )
        self.back_button.setEnabled(index > 0)
        is_last = index == self.pages.count() - 1
        self.next_button.setText(tr("Done") if is_last else tr("Next"))
        set_action_icon(self.next_button, "fa5s.check" if is_last else "fa5s.arrow-right")


def add_context_help(layout: QVBoxLayout, topic: str, parent: QWidget) -> QToolButton:
    button = QToolButton(parent)
    set_action_icon(button, "fa5s.question-circle")
    button.setToolTip(tr("Show guide for this page"))
    button.setAccessibleName(tr("Show guide for this page"))
    button.setAutoRaise(True)
    button.clicked.connect(lambda: SectionGuideDialog(topic, parent).exec())
    layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTrailing)
    return button

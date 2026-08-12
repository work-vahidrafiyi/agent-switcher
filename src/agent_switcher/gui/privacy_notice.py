from __future__ import annotations

from typing import Optional

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .window_surface import create_shadowed_surface


class PrivacyNoticeDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Your login stays private"))
        self.setModal(True)
        self.setFixedWidth(540)

        _surface, root = create_shadowed_surface(self, outer_margin=8)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(16)

        hero = QHBoxLayout()
        hero.setSpacing(16)
        icon = QLabel()
        icon.setPixmap(qta.icon("fa5s.shield-alt", color="#2f80ed").pixmap(58, 58))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        hero.addWidget(icon)

        copy = QVBoxLayout()
        copy.setSpacing(7)
        title = QLabel(tr("Your login stays private"))
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title.setFont(title_font)
        copy.addWidget(title)

        intro = QLabel(
            tr(
                "Your Codex login tokens and saved accounts stay on this device. "
                "Agent Switcher does not upload them to its own server or share them with anyone."
            )
        )
        intro.setWordWrap(True)
        copy.addWidget(intro)
        hero.addLayout(copy, 1)
        root.addLayout(hero)

        facts = QWidget()
        facts.setObjectName("privacyFacts")
        facts.setStyleSheet(
            "#privacyFacts { background: rgba(47, 128, 237, 0.08); "
            "border: 1px solid rgba(47, 128, 237, 0.30); border-radius: 10px; }"
        )
        facts_layout = QVBoxLayout(facts)
        facts_layout.setContentsMargins(14, 12, 14, 12)
        facts_layout.setSpacing(7)
        for text in (
            tr("Login files are stored only in your local Codex folder."),
            tr("Credentials are never sent to an Agent Switcher server."),
            tr(
                "Network requests go only to OpenAI/Codex, GitHub for updates, the public-IP "
                "verification service, or the proxy you configured."
            ),
            tr("IP Guard stores only a local fingerprint, never your raw public IP."),
        ):
            row = QLabel("✓  " + text)
            row.setWordWrap(True)
            row.setStyleSheet("color: #2e9d55;")
            facts_layout.addWidget(row)
        root.addWidget(facts)

        self.dont_show_again = QCheckBox(tr("Don't show this again"))
        self.dont_show_again.setChecked(False)
        root.addWidget(self.dont_show_again)

        actions = QHBoxLayout()
        actions.addStretch(1)
        understood = QPushButton(tr("Got it"))
        understood.setMinimumWidth(120)
        understood.setDefault(True)
        understood.clicked.connect(self.accept)
        actions.addWidget(understood)
        root.addLayout(actions)

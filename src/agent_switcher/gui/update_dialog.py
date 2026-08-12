from __future__ import annotations

from typing import Optional

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from agent_switcher.core.updater import UpdateInfo

from .i18n import tr
from .window_surface import create_shadowed_surface


class UpdateAvailableDialog(QDialog):
    def __init__(
        self,
        info: UpdateInfo,
        automatic_install: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.info = info
        self.action = "later"
        self.setWindowTitle(tr("Update available"))
        self.setModal(True)
        self.resize(560, 440)

        _surface, root = create_shadowed_surface(self, outer_margin=8)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        hero = QHBoxLayout()
        hero.setSpacing(15)
        icon = QLabel()
        icon.setPixmap(qta.icon("fa5s.cloud-download-alt", color="#2f80ed").pixmap(52, 52))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        hero.addWidget(icon)
        copy = QVBoxLayout()
        copy.setSpacing(4)
        title = QLabel(tr("A new Agent Switcher update is ready"))
        font = title.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 4)
        title.setFont(font)
        copy.addWidget(title)
        versions = QLabel(
            tr(
                "Installed: {current}   •   Available: {latest}",
                current=info.current_version,
                latest=info.latest_version,
            )
        )
        versions.setStyleSheet("color: palette(placeholder-text);")
        copy.addWidget(versions)
        hero.addLayout(copy, 1)
        root.addLayout(hero)

        notes_heading = QLabel(tr("What's new"))
        notes_font = notes_heading.font()
        notes_font.setBold(True)
        notes_heading.setFont(notes_font)
        root.addWidget(notes_heading)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(False)
        notes.setMarkdown(info.notes[:12000] if info.notes.strip() else tr("No release notes were provided."))
        root.addWidget(notes, 1)

        if not automatic_install:
            explanation = QLabel(
                tr(
                    "Automatic installation is available in the standalone app. "
                    "This Python installation can open the release page instead."
                )
            )
            explanation.setWordWrap(True)
            explanation.setStyleSheet("color: #d17b20;")
            root.addWidget(explanation)

        actions = QHBoxLayout()
        actions.addStretch(1)
        later = QPushButton(tr("Later"))
        later.clicked.connect(self.reject)
        actions.addWidget(later)
        primary = QPushButton(
            tr("Download and install") if automatic_install else tr("Open release page")
        )
        primary.setMinimumWidth(160)
        primary.setDefault(True)
        primary.clicked.connect(
            lambda: self._finish("install" if automatic_install else "open_release")
        )
        actions.addWidget(primary)
        root.addLayout(actions)

    def _finish(self, action: str) -> None:
        self.action = action
        self.accept()


class UpdateProgressDialog(QDialog):
    def __init__(self, version: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Installing update"))
        self.setModal(True)
        self.setFixedWidth(480)

        _surface, root = create_shadowed_surface(self, outer_margin=8)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        title = QLabel(tr("Downloading Agent Switcher {version}", version=version))
        font = title.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        title.setFont(font)
        root.addWidget(title)
        self.status_label = QLabel(tr("Verifying and preparing the update..."))
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

    def set_progress(self, value: int) -> None:
        self.progress.setValue(value)
        self.status_label.setText(tr("Downloaded {value}%", value=value))

    def set_installing(self) -> None:
        self.progress.setValue(100)
        self.status_label.setText(tr("Update verified. Restarting to finish installation..."))

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from agent_switcher.core.store import Profile
from agent_switcher.core.usage import Usage

from .icons import set_action_icon
from .i18n import is_rtl, tr


class ClickableHeader(QWidget):
    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ProfileRow(QFrame):
    def __init__(
        self,
        profile: Profile,
        on_switch: Callable[[str], None],
        on_rename: Callable[[str], None],
        on_remove: Callable[[str], None],
        on_copy_debug: Callable[[Profile], None],
        on_refresh: Callable[[str], None],
        usage: Optional[Usage] = None,
        expanded: bool = False,
        offline_mode: bool = False,
        usage_history: Optional[list[dict]] = None,
    ) -> None:
        super().__init__()
        self.profile = profile
        self.usage = usage
        self.expanded = expanded
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken if profile.active else QFrame.Shadow.Raised)
        self.setLineWidth(2 if profile.active else 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        self.header = ClickableHeader()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)

        self.status_dot = QFrame()
        self.status_dot.setFrameShape(QFrame.Shape.Box)
        self.status_dot.setFixedSize(11, 11)
        self.status_dot.setAutoFillBackground(True)
        header.addWidget(self.status_dot)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title_row = QHBoxLayout()
        name = QLabel(profile.name)
        font = name.font()
        font.setBold(True)
        name.setFont(font)
        title_row.addWidget(name)
        if profile.active:
            active = QLabel(tr("Active"))
            active.setForegroundRole(QPalette.ColorRole.Highlight)
            active_font = active.font()
            active_font.setBold(True)
            active.setFont(active_font)
            title_row.addWidget(active)
        title_row.addStretch(1)
        text_box.addLayout(title_row)

        meta = QLabel(self._metadata(profile))
        meta.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_box.addWidget(meta)
        header.addLayout(text_box, 1)

        self.loading = QProgressBar()
        self.loading.setRange(0, 0)
        self.loading.setFixedSize(72, 8)
        self.loading.setTextVisible(False)
        self.loading.setToolTip(tr("Checking usage"))
        self.loading.hide()
        header.addWidget(self.loading)

        self.refresh_button = self._icon_button("fa5s.sync-alt", tr("Refresh this account"))
        self.refresh_button.clicked.connect(lambda: on_refresh(profile.name))
        header.addWidget(self.refresh_button)

        if not profile.active:
            switch_button = self._icon_button("fa5s.exchange-alt", tr("Switch to this account"))
            switch_button.clicked.connect(lambda: on_switch(profile.name))
            header.addWidget(switch_button)

        rename_button = self._icon_button("fa5s.pen", tr("Rename account"))
        rename_button.clicked.connect(lambda: on_rename(profile.name))
        header.addWidget(rename_button)

        remove_button = self._icon_button("fa5s.trash-alt", tr("Remove account"))
        remove_button.clicked.connect(lambda: on_remove(profile.name))
        header.addWidget(remove_button)

        self.expand_button = self._icon_button("fa5s.chevron-down", tr("Expand usage details"))
        self.expand_button.clicked.connect(self.toggle_expanded)
        header.addWidget(self.expand_button)
        self.header.clicked.connect(self.toggle_expanded)
        root.addWidget(self.header)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)

        self.details = QWidget()
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0 if is_rtl() else 20, 0, 20 if is_rtl() else 0, 0)
        details_layout.setSpacing(8)
        details_layout.addWidget(separator)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(1, 1)
        grid.addWidget(QLabel(tr("Five-hour window")), 0, 0)
        self.five_hour_bar = self._usage_bar()
        grid.addWidget(self.five_hour_bar, 0, 1)
        self.five_hour_reset = QLabel()
        self.five_hour_reset.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        grid.addWidget(self.five_hour_reset, 0, 2)

        grid.addWidget(QLabel(tr("Weekly window")), 1, 0)
        self.weekly_bar = self._usage_bar()
        grid.addWidget(self.weekly_bar, 1, 1)
        self.weekly_reset = QLabel()
        self.weekly_reset.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        grid.addWidget(self.weekly_reset, 1, 2)
        details_layout.addLayout(grid)

        self.sparkline = UsageSparkline(usage_history or [])
        details_layout.addWidget(self.sparkline)

        detail_footer = QHBoxLayout()
        self.checked_label = QLabel()
        self.checked_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        detail_footer.addWidget(self.checked_label, 1)
        copy_button = QToolButton()
        set_action_icon(copy_button, "fa5s.copy")
        copy_button.setText(tr("Copy debug info"))
        copy_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        copy_button.setToolTip(tr("Copy account id and saved profile path"))
        copy_button.clicked.connect(lambda: on_copy_debug(profile))
        detail_footer.addWidget(copy_button)
        details_layout.addLayout(detail_footer)
        root.addWidget(self.details)

        self.set_expanded(expanded)
        self.set_offline_mode(offline_mode)
        self.update_usage(usage)

    def set_offline_mode(self, offline: bool) -> None:
        self.refresh_button.setEnabled(not offline)
        self.refresh_button.setToolTip(
            tr("Offline mode is on - turn it off in settings to check usage")
            if offline
            else tr("Refresh this account")
        )

    def update_usage_history(self, history: list[dict]) -> None:
        self.sparkline.set_history(history)

    def set_loading(self, loading: bool) -> None:
        self.loading.setVisible(loading)
        if loading:
            self.loading.setToolTip(tr("Checking usage for {profile}", profile=self.profile.name))

    def update_usage(self, usage: Optional[Usage]) -> None:
        self.usage = usage
        status, color = self._status(usage)
        self.status_dot.setStyleSheet(
            f"background-color: {color.name()}; border: none; border-radius: 5px;"
        )
        self.status_dot.setToolTip(status)

        if usage is None:
            self._set_bar_unavailable(self.five_hour_bar)
            self._set_bar_unavailable(self.weekly_bar)
            self.five_hour_reset.setText(tr("Not checked"))
            self.weekly_reset.setText(tr("Not checked"))
            self.checked_label.setText(tr("Usage has not been checked"))
            return

        if not usage.available:
            self._set_bar_unavailable(self.five_hour_bar)
            self._set_bar_unavailable(self.weekly_bar)
            self.five_hour_reset.setText(tr("Unavailable"))
            self.weekly_reset.setText(tr("Unavailable"))
            self.update_relative_time()
            return

        if usage.five_hour_used_pct is None:
            self._set_bar_unavailable(self.five_hour_bar)
        else:
            self._set_bar(self.five_hour_bar, usage.five_hour_used_pct)
        if usage.weekly_used_pct is None:
            self._set_bar_unavailable(self.weekly_bar)
        else:
            self._set_bar(self.weekly_bar, usage.weekly_used_pct)
        self.five_hour_reset.setText(self._reset_text(usage.five_hour_reset_at))
        self.weekly_reset.setText(self._reset_text(usage.weekly_reset_at))
        self.update_relative_time()

    def update_relative_time(self) -> None:
        if self.usage is None:
            return
        checked = tr("Checked {relative}", relative=self._relative_time(self.usage.checked_at))
        if self.usage.available:
            self.checked_label.setText(checked)
        else:
            reason = tr(self.usage.unavailable_reason or "Usage unavailable")
            self.checked_label.setText(f"{reason} | {checked}")

    def toggle_expanded(self) -> None:
        self.set_expanded(not self.expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        self.details.setVisible(expanded)
        icon_name = "fa5s.chevron-up" if expanded else "fa5s.chevron-down"
        set_action_icon(self.expand_button, icon_name)
        self.expand_button.setToolTip(tr("Collapse usage details" if expanded else "Expand usage details"))

    @staticmethod
    def _icon_button(icon_name: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        set_action_icon(button, icon_name)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setAutoRaise(True)
        return button

    @staticmethod
    def _usage_bar() -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if is_rtl() else Qt.LayoutDirection.LeftToRight
        )
        bar.setInvertedAppearance(False)
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return bar

    @staticmethod
    def _set_bar(bar: QProgressBar, value: Optional[float]) -> None:
        number = ProfileRow._remaining(value)
        color = ProfileRow._remaining_color(number)
        bar.setEnabled(True)
        bar.setValue(round(number))
        bar.setFormat(tr("{value}% remaining", value=f"{number:g}"))
        bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color.name()}; }}")

    @staticmethod
    def _set_bar_unavailable(bar: QProgressBar) -> None:
        bar.setStyleSheet("")
        bar.setValue(0)
        bar.setFormat(tr("Unavailable"))
        bar.setEnabled(False)

    @staticmethod
    def _status(usage: Optional[Usage]) -> tuple[str, QColor]:
        if usage is None:
            return tr("Usage not checked"), QPalette().color(QPalette.ColorRole.Mid)
        if not usage.available:
            return tr("Usage unavailable"), QPalette().color(QPalette.ColorRole.Mid)
        remaining = [
            ProfileRow._remaining(value)
            for value in (usage.five_hour_used_pct, usage.weekly_used_pct)
            if value is not None
        ]
        if not remaining:
            return tr("Usage unavailable"), QPalette().color(QPalette.ColorRole.Mid)
        lowest = min(remaining)
        if lowest < 20:
            return tr("Less than 20% remaining"), ProfileRow._remaining_color(lowest)
        if lowest > 80:
            return tr("More than 80% remaining"), ProfileRow._remaining_color(lowest)
        return tr("Between 20% and 80% remaining"), ProfileRow._remaining_color(lowest)

    @staticmethod
    def _remaining(used: Optional[float]) -> float:
        return max(0.0, min(100.0, 100.0 - (used or 0.0)))

    @staticmethod
    def _remaining_color(remaining: float) -> QColor:
        if remaining < 20:
            return QColor("#c62828")
        if remaining > 80:
            return QColor("#48d94f")
        return QColor("#1976d2")

    @staticmethod
    def _reset_text(value: Optional[datetime]) -> str:
        if value is None:
            return tr("Reset unavailable")
        return tr("Resets {time}", time=value.astimezone().strftime("%Y-%m-%d %H:%M"))

    @staticmethod
    def _relative_time(value: datetime) -> str:
        now = datetime.now(timezone.utc)
        elapsed = max(0, int((now - value.astimezone(timezone.utc)).total_seconds()))
        if elapsed < 60:
            return tr("just now")
        if elapsed < 3600:
            return tr("{value}m ago", value=elapsed // 60)
        if elapsed < 86400:
            return tr("{value}h ago", value=elapsed // 3600)
        return tr("{value}d ago", value=elapsed // 86400)

    @staticmethod
    def _metadata(profile: Profile) -> str:
        identity = profile.identity
        parts = [value for value in (identity.email, identity.plan) if value]
        if identity.refreshed:
            parts.append(tr("refreshed {value}", value=identity.refreshed))
        return " | ".join(parts) if parts else tr("No account details")


class UsageSparkline(QWidget):
    def __init__(self, history: list[dict], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.history = history
        self.setMinimumHeight(72)

    def set_history(self, history: list[dict]) -> None:
        self.history = history
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(320, 72)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        five_hour, weekly = self.series(self.history)
        if max(len(five_hour), len(weekly)) < 2:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Not enough data yet"))
            return

        chart = self.rect().adjusted(6, 18, -6, -6)
        title_rect = self.rect().adjusted(6, 0, -6, 0)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeading,
            tr("Remaining trend"),
        )
        self._draw_series(painter, chart, five_hour, QColor("#1976d2"))
        self._draw_series(painter, chart, weekly, QColor("#48d94f"))

    @staticmethod
    def series(history: list[dict]) -> tuple[list[float], list[float]]:
        chronological = list(reversed(history))
        five_hour = []
        weekly = []
        for event in chronological:
            payload = event.get("payload", {})
            five = payload.get("five_hour_used_pct")
            week = payload.get("weekly_used_pct")
            if isinstance(five, (int, float)) and not isinstance(five, bool):
                five_hour.append(max(0.0, min(100.0, 100.0 - float(five))))
            if isinstance(week, (int, float)) and not isinstance(week, bool):
                weekly.append(max(0.0, min(100.0, 100.0 - float(week))))
        return five_hour, weekly

    @staticmethod
    def _draw_series(painter: QPainter, rect, values: list[float], color: QColor) -> None:
        if len(values) < 2:
            return
        painter.setPen(QPen(color, 2))
        width = max(1, rect.width())
        height = max(1, rect.height())
        points = [
            QPointF(
                (
                    rect.right() - index * width / (len(values) - 1)
                    if is_rtl()
                    else rect.left() + index * width / (len(values) - 1)
                ),
                rect.bottom() - value * height / 100,
            )
            for index, value in enumerate(values)
        ]
        painter.drawPolyline(QPolygonF(points))

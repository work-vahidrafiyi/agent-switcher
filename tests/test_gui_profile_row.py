from datetime import datetime, timezone

from agent_switcher.core.usage import Usage
from agent_switcher.gui.profile_row import ProfileRow, UsageSparkline
from agent_switcher.gui.tray import TrayController
from agent_switcher.gui.main_window import MainWindow


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def usage_with_used(five_hour, weekly):
    return Usage(five_hour, NOW, weekly, NOW, NOW)


def test_progress_value_is_remaining_percentage():
    assert ProfileRow._remaining(93) == 7
    assert ProfileRow._remaining(20) == 80
    assert ProfileRow._remaining(0) == 100


def test_status_uses_lowest_remaining_window_and_new_thresholds():
    assert ProfileRow._status(usage_with_used(81, 10))[1].name() == "#c62828"
    assert ProfileRow._status(usage_with_used(80, 20))[1].name() == "#1976d2"
    assert ProfileRow._status(usage_with_used(19, 10))[1].name() == "#48d94f"


def test_progress_bar_color_thresholds():
    assert ProfileRow._remaining_color(19).name() == "#c62828"
    assert ProfileRow._remaining_color(20).name() == "#1976d2"
    assert ProfileRow._remaining_color(80).name() == "#1976d2"
    assert ProfileRow._remaining_color(81).name() == "#48d94f"


def test_sparkline_series_uses_chronological_remaining_percentages():
    history = [
        {"payload": {"five_hour_used_pct": 80, "weekly_used_pct": 40}},
        {"payload": {"five_hour_used_pct": 20, "weekly_used_pct": None}},
    ]

    five_hour, weekly = UsageSparkline.series(history)

    assert five_hour == [80, 20]
    assert weekly == [60]


def test_tray_tooltip_shows_remaining_or_unknown():
    usage = usage_with_used(6, 12)

    assert TrayController.tooltip_text("account3", usage) == "account3 - 94% left (5h), 88% left (weekly)"
    assert TrayController.tooltip_text("account3", None) == "account3 - usage unknown"


def test_low_quota_warning_only_fires_on_downward_crossing():
    assert MainWindow.crossed_below(18, 14, 15) is True
    assert MainWindow.crossed_below(14, 10, 15) is False
    assert MainWindow.crossed_below(18, 15, 15) is False
    assert MainWindow.crossed_below(None, 10, 15) is False

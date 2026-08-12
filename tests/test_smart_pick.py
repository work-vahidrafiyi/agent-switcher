from datetime import datetime, timedelta, timezone

from agent_switcher.core.activity_log import ActivityLog
from agent_switcher.core.smart_pick import choose_smart_profile, stale_usage_profiles


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def add_usage(log, profile, five_used, weekly_used, timestamp):
    log.append(
        "network_call",
        {
            "endpoint": "usage",
            "purpose": "usage_check",
            "profile": profile,
            "success": True,
            "five_hour_used_pct": five_used,
            "weekly_used_pct": weekly_used,
        },
        timestamp=timestamp,
    )


def test_smart_pick_uses_lower_remaining_window_and_excludes_active(tmp_path):
    log = ActivityLog(tmp_path / "activity.jsonl")
    add_usage(log, "active", 1, 1, NOW)
    add_usage(log, "balanced", 20, 30, NOW)
    add_usage(log, "weak-weekly", 5, 85, NOW)
    add_usage(log, "best", 10, 20, NOW)

    result = choose_smart_profile(
        log,
        ["active", "balanced", "weak-weekly", "best"],
        active="active",
        minimum_headroom_pct=20,
        max_age=timedelta(minutes=10),
        now=NOW,
    )

    assert result.profile_name == "best"
    assert result.score == 80


def test_smart_pick_requires_both_windows_and_fresh_data(tmp_path):
    log = ActivityLog(tmp_path / "activity.jsonl")
    add_usage(log, "weekly-only", None, 10, NOW)
    add_usage(log, "stale", 10, 10, NOW - timedelta(minutes=11))

    assert stale_usage_profiles(
        log, ["weekly-only", "stale", "missing"], max_age=timedelta(minutes=10), now=NOW
    ) == ["weekly-only", "stale", "missing"]
    result = choose_smart_profile(
        log,
        ["weekly-only", "stale"],
        active=None,
        minimum_headroom_pct=20,
        max_age=timedelta(minutes=10),
        now=NOW,
    )
    assert result.profile_name is None


def test_smart_pick_refreshes_recent_but_incomplete_usage_samples(tmp_path):
    log = ActivityLog(tmp_path / "activity.jsonl")
    add_usage(log, "incomplete", 10, None, NOW)

    assert stale_usage_profiles(
        log, ["incomplete"], max_age=timedelta(minutes=10), now=NOW
    ) == ["incomplete"]

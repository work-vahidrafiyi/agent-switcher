import json
from datetime import datetime, timedelta, timezone

import pytest

from agent_switcher.core.activity_log import ActivityLog, run_network_call


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def test_append_writes_newline_delimited_json(tmp_path):
    log = ActivityLog(tmp_path / "activity.jsonl")

    log.append("switch", {"from": "work", "to": "personal"}, timestamp=NOW)
    log.append("login", {"profile": "client", "mode": "browser"}, timestamp=NOW)

    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {
        "event_type": "switch",
        "payload": {"from": "work", "to": "personal"},
        "timestamp": "2026-08-04T12:00:00Z",
    }


def test_rotation_keeps_only_recent_events_within_cap(tmp_path):
    log = ActivityLog(tmp_path / "activity.jsonl", max_events=3, max_age_days=90)
    log.append("switch", {"to": "expired"}, timestamp=NOW - timedelta(days=91))
    for index in range(4):
        log.append("switch", {"to": f"profile-{index}"}, timestamp=NOW + timedelta(seconds=index))

    retained = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
    assert [event["payload"]["to"] for event in retained] == ["profile-1", "profile-2", "profile-3"]


def test_read_functions_filter_and_return_newest_first(tmp_path):
    log = ActivityLog(tmp_path / "activity.jsonl")
    log.append("switch", {"from": "a", "to": "b"}, timestamp=NOW)
    log.append(
        "network_call",
        {"endpoint": "usage", "purpose": "usage_check", "profile": "work", "success": True,
         "five_hour_used_pct": 20, "weekly_used_pct": 40},
        timestamp=NOW + timedelta(seconds=1),
    )
    log.append(
        "network_call",
        {"endpoint": "usage", "purpose": "usage_check", "profile": "other", "success": True,
         "five_hour_used_pct": 10, "weekly_used_pct": 30},
        timestamp=NOW + timedelta(seconds=2),
    )
    log.append("switch", {"from": "b", "to": "c"}, timestamp=NOW + timedelta(seconds=3))
    log.append(
        "network_call",
        {"endpoint": "usage", "purpose": "usage_check", "profile": "work", "success": True,
         "five_hour_used_pct": 30, "weekly_used_pct": 50},
        timestamp=NOW + timedelta(seconds=4),
    )
    log.append(
        "network_call",
        {"endpoint": "usage", "purpose": "usage_check", "profile": "work", "success": False,
         "five_hour_used_pct": None, "weekly_used_pct": None},
        timestamp=NOW + timedelta(seconds=5),
    )

    assert [event["payload"]["to"] for event in log.recent_switches(2)] == ["c", "b"]
    assert len(log.recent_network_calls(3)) == 3
    assert [event["payload"]["five_hour_used_pct"] for event in log.usage_history("work", 2)] == [30, 20]


def test_network_call_wrapper_records_success_and_failure(tmp_path):
    log = ActivityLog(tmp_path / "activity.jsonl")

    assert run_network_call(log, "https://example.test", "usage_check", lambda: 42) == 42
    with pytest.raises(RuntimeError):
        run_network_call(log, "https://example.test", "token_refresh", lambda: (_ for _ in ()).throw(RuntimeError("down")))

    calls = log.recent_network_calls(2)
    assert calls[0]["payload"]["success"] is False
    assert calls[0]["payload"]["error"] == "down"
    assert calls[1]["payload"]["success"] is True

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from .activity_log import ActivityLog


@dataclass(frozen=True)
class SmartPickResult:
    profile_name: Optional[str]
    score: Optional[float]
    reason: Optional[str] = None


def stale_usage_profiles(
    activity_log: ActivityLog,
    profile_names: Iterable[str],
    *,
    max_age: timedelta,
    now: Optional[datetime] = None,
) -> list[str]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stale = []
    for name in profile_names:
        sample = _latest_sample(activity_log, name)
        if sample is None or current - sample[0] > max_age:
            stale.append(name)
    return stale


def choose_smart_profile(
    activity_log: ActivityLog,
    profile_names: Iterable[str],
    *,
    active: Optional[str],
    minimum_headroom_pct: float,
    max_age: timedelta,
    now: Optional[datetime] = None,
) -> SmartPickResult:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    candidates = []
    for name in profile_names:
        if name == active:
            continue
        sample = _latest_sample(activity_log, name)
        if sample is None or current - sample[0] > max_age:
            continue
        _, five_used, weekly_used = sample
        if five_used is None or weekly_used is None:
            continue
        five_remaining = 100.0 - five_used
        weekly_remaining = 100.0 - weekly_used
        if five_remaining < minimum_headroom_pct or weekly_remaining < minimum_headroom_pct:
            continue
        candidates.append((min(five_remaining, weekly_remaining), name))

    if not candidates:
        return SmartPickResult(None, None, "No other profile has fresh usage data with enough headroom.")
    score, name = max(candidates, key=lambda item: (item[0], item[1]))
    return SmartPickResult(name, score)


def _latest_sample(activity_log: ActivityLog, profile_name: str):
    history = activity_log.usage_history(profile_name, 1)
    if not history:
        return None
    event = history[0]
    timestamp = _parse_timestamp(event.get("timestamp"))
    if timestamp is None:
        return None
    payload = event.get("payload", {})
    return (
        timestamp,
        _number(payload.get("five_hour_used_pct")),
        _number(payload.get("weekly_used_pct")),
    )


def _parse_timestamp(value: object) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)

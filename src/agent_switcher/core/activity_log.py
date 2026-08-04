from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypeVar

from .files import atomic_write


MAX_EVENTS = 5000
MAX_AGE_DAYS = 90
T = TypeVar("T")


class NetworkCallFailure(Exception):
    pass


class ActivityLog:
    def __init__(self, path: Path, max_events: int = MAX_EVENTS, max_age_days: int = MAX_AGE_DAYS) -> None:
        self.path = Path(path)
        self.max_events = max_events
        self.max_age_days = max_age_days
        self._lock = threading.Lock()

    @classmethod
    def for_provider_home(cls, provider_home: Path) -> "ActivityLog":
        return cls(provider_home.parent / "agent-switcher" / "activity.jsonl")

    def append(self, event_type: str, payload: Mapping[str, Any], timestamp: Optional[datetime] = None) -> None:
        event = {
            "timestamp": _timestamp(timestamp or datetime.now(timezone.utc)),
            "event_type": event_type,
            "payload": dict(payload),
        }
        line = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab") as handle:
                handle.write(line)
                handle.flush()
            self._rotate(timestamp or datetime.now(timezone.utc))

    def recent_switches(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._recent("switch", limit)

    def recent_network_calls(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._recent("network_call", limit)

    def usage_history(self, profile_name: str, limit: int = 20) -> list[dict[str, Any]]:
        events = [
            event
            for event in reversed(self._read_events())
            if event.get("event_type") == "network_call"
            and event.get("payload", {}).get("purpose") == "usage_check"
            and event.get("payload", {}).get("profile") == profile_name
            and event.get("payload", {}).get("success") is True
        ]
        return events[: max(0, limit)]

    def _recent(self, event_type: str, limit: int) -> list[dict[str, Any]]:
        events = [event for event in reversed(self._read_events()) if event.get("event_type") == event_type]
        return events[: max(0, limit)]

    def _read_events(self) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        events = []
        for line in lines:
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def _rotate(self, now: datetime) -> None:
        cutoff = now.astimezone(timezone.utc) - timedelta(days=self.max_age_days)
        retained = []
        for event in self._read_events():
            timestamp = _parse_timestamp(event.get("timestamp"))
            if timestamp is not None and timestamp >= cutoff:
                retained.append(event)
        retained = retained[-self.max_events :]
        data = b"".join(
            (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            for event in retained
        )
        atomic_write(self.path, data)


def run_network_call(
    activity_log: Optional[ActivityLog],
    endpoint: str,
    purpose: str,
    operation: Callable[[], T],
    *,
    payload: Optional[Mapping[str, Any]] = None,
    describe: Optional[Callable[[T], Mapping[str, Any]]] = None,
) -> T:
    started = time.monotonic()
    base = {"endpoint": endpoint, "purpose": purpose, **dict(payload or {})}
    try:
        result = operation()
    except Exception as exc:
        if activity_log is not None:
            activity_log.append(
                "network_call",
                {
                    **base,
                    "success": False,
                    "error": str(exc) or type(exc).__name__,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                },
            )
        raise

    details = dict(describe(result)) if describe is not None else {}
    details.setdefault("success", True)
    if activity_log is not None:
        activity_log.append(
            "network_call",
            {**base, **details, "duration_ms": round((time.monotonic() - started) * 1000)},
        )
    return result


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TYPE_CHECKING
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request

from .token_refresh import refresh_profile_token_if_needed
from .activity_log import ActivityLog, NetworkCallFailure, run_network_call
from .proxy import ProxyConfig

if TYPE_CHECKING:
    from .store import Profile


USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
USAGE_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class Usage:
    five_hour_used_pct: Optional[float]
    five_hour_reset_at: Optional[datetime]
    weekly_used_pct: Optional[float]
    weekly_reset_at: Optional[datetime]
    checked_at: datetime
    available: bool = True
    unavailable_reason: Optional[str] = None

    @classmethod
    def unavailable(cls, reason: str, checked_at: Optional[datetime] = None) -> "Usage":
        return cls(
            five_hour_used_pct=None,
            five_hour_reset_at=None,
            weekly_used_pct=None,
            weekly_reset_at=None,
            checked_at=checked_at or _utc_now(),
            available=False,
            unavailable_reason=reason,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "five_hour_used_pct": self.five_hour_used_pct,
            "five_hour_reset_at": _datetime_text(self.five_hour_reset_at),
            "weekly_used_pct": self.weekly_used_pct,
            "weekly_reset_at": _datetime_text(self.weekly_reset_at),
            "checked_at": _datetime_text(self.checked_at),
            "unavailable_reason": self.unavailable_reason,
        }


Transport = Callable[..., Any]


def fetch_usage(
    profile: "Profile",
    *,
    transport: Optional[Transport] = None,
    refresh_transport: Optional[Transport] = None,
    now: Optional[datetime] = None,
    activity_log: Optional[ActivityLog] = None,
    proxy_config: Optional[ProxyConfig] = None,
) -> Usage:
    """Fetch usage from a saved Codex profile without touching live auth.json."""
    checked_at = now or _utc_now()
    auth = _read_auth(profile.path)
    if auth is None:
        return Usage.unavailable("Saved credentials are unreadable.", checked_at)

    if auth.get("auth_mode") != "chatgpt":
        return Usage.unavailable("Usage is only available for ChatGPT-login profiles.", checked_at)
    if auth.get("OPENAI_API_KEY"):
        return Usage.unavailable("Usage is not available for API-key profiles.", checked_at)

    refresh = refresh_profile_token_if_needed(
        profile,
        auth,
        transport=refresh_transport,
        now=checked_at,
        activity_log=activity_log,
        proxy_config=proxy_config,
    )
    if refresh.error:
        return Usage.unavailable(refresh.error, checked_at)
    auth = refresh.auth

    tokens = auth.get("tokens")
    if not isinstance(tokens, Mapping):
        return Usage.unavailable("Saved credentials do not contain session tokens.", checked_at)
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id")
    if not isinstance(access_token, str) or not access_token:
        return Usage.unavailable("Saved credentials do not contain an access token.", checked_at)
    if not isinstance(account_id, str) or not account_id:
        return Usage.unavailable("Saved credentials do not contain an account id.", checked_at)

    request = Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "ChatGPT-Account-Id": account_id,
        },
        method="GET",
    )

    def perform_request() -> Usage:
        opener = transport or (proxy_config or ProxyConfig()).open
        response = opener(request, timeout=USAGE_TIMEOUT_SECONDS)
        try:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 200:
                raise NetworkCallFailure(f"Usage service returned HTTP {status}.")
            payload = json.load(response)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        return _parse_usage(payload, checked_at)

    try:
        return run_network_call(
            activity_log,
            USAGE_URL,
            "usage_check",
            perform_request,
            payload={"profile": profile.name},
            describe=lambda usage: {
                "success": usage.available,
                "error": usage.unavailable_reason,
                "five_hour_used_pct": usage.five_hour_used_pct,
                "weekly_used_pct": usage.weekly_used_pct,
            },
        )
    except HTTPError as exc:
        return Usage.unavailable(f"Usage service returned HTTP {exc.code}.", checked_at)
    except (TimeoutError, URLError):
        return Usage.unavailable("Usage check failed after retrying the network connection.", checked_at)
    except NetworkCallFailure as exc:
        return Usage.unavailable(str(exc), checked_at)
    except Exception as exc:
        return Usage.unavailable(f"Usage is unavailable: {type(exc).__name__}.", checked_at)


def read_profile_account_id(profile: "Profile") -> Optional[str]:
    auth = _read_auth(profile.path)
    if auth is None:
        return None
    tokens = auth.get("tokens")
    if not isinstance(tokens, Mapping):
        return None
    account_id = tokens.get("account_id")
    return account_id if isinstance(account_id, str) and account_id else None


fetch_codex_usage = fetch_usage
UsageResult = Usage


def _read_auth(path: Path) -> Optional[Mapping[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, Mapping) else None


def _parse_usage(payload: Any, checked_at: datetime) -> Usage:
    if not isinstance(payload, Mapping):
        return Usage.unavailable("Usage service returned an unexpected response.", checked_at)
    rate_limit = payload.get("rate_limit")
    if not isinstance(rate_limit, Mapping):
        return Usage.unavailable("Usage service returned an unexpected response.", checked_at)

    primary = rate_limit.get("primary_window")
    secondary = rate_limit.get("secondary_window")
    if not isinstance(primary, Mapping):
        return Usage.unavailable("Usage service returned an unexpected response.", checked_at)

    primary_values = _window_values(primary)
    if primary_values is None:
        return Usage.unavailable("Usage service returned an unexpected response.", checked_at)

    windows = [(0, primary_values)]
    if secondary is not None:
        if not isinstance(secondary, Mapping):
            return Usage.unavailable("Usage service returned an unexpected response.", checked_at)
        secondary_values = _window_values(secondary)
        if secondary_values is None:
            return Usage.unavailable("Usage service returned an unexpected response.", checked_at)
        windows.append((1, secondary_values))

    five_hour_pct = None
    five_hour_reset = None
    weekly_pct = None
    weekly_reset = None
    for position, (percentage, reset_at, duration) in windows:
        if duration is not None and duration >= 24 * 60 * 60:
            weekly_pct, weekly_reset = percentage, reset_at
        elif duration is not None:
            five_hour_pct, five_hour_reset = percentage, reset_at
        elif position == 0:
            five_hour_pct, five_hour_reset = percentage, reset_at
        else:
            weekly_pct, weekly_reset = percentage, reset_at

    return Usage(
        five_hour_used_pct=five_hour_pct,
        five_hour_reset_at=five_hour_reset,
        weekly_used_pct=weekly_pct,
        weekly_reset_at=weekly_reset,
        checked_at=checked_at,
    )


def _percentage(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if 0 <= number <= 100 else None


def _window_values(window: Mapping[str, Any]) -> Optional[tuple[float, datetime, Optional[float]]]:
    percentage = _percentage(window.get("used_percent"))
    reset_at = _reset_time(window.get("reset_at"))
    if percentage is None or reset_at is None:
        return None
    duration_value = window.get("limit_window_seconds")
    duration = None
    if isinstance(duration_value, (int, float)) and not isinstance(duration_value, bool):
        duration = float(duration_value)
    return percentage, reset_at, duration


def _reset_time(value: Any) -> Optional[datetime]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _datetime_text(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

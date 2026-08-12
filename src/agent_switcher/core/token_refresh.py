from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, TYPE_CHECKING
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request

from .files import atomic_write
from .identity import decode_jwt
from .activity_log import ActivityLog, NetworkCallFailure, run_network_call
from .proxy import ProxyConfig

if TYPE_CHECKING:
    from .store import Profile


TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REFRESH_MARGIN_SECONDS = 30
REFRESH_TIMEOUT_SECONDS = 5.0

Transport = Callable[..., Any]


@dataclass(frozen=True)
class TokenRefreshResult:
    auth: Mapping[str, Any]
    refreshed: bool = False
    error: Optional[str] = None


def refresh_profile_token_if_needed(
    profile: "Profile",
    auth: Mapping[str, Any],
    *,
    transport: Optional[Transport] = None,
    now: Optional[datetime] = None,
    activity_log: Optional[ActivityLog] = None,
    proxy_config: Optional[ProxyConfig] = None,
) -> TokenRefreshResult:
    if profile.active:
        return TokenRefreshResult(auth=auth)

    tokens = auth.get("tokens")
    if not isinstance(tokens, Mapping):
        return TokenRefreshResult(auth=auth)
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not _expires_soon(access_token, now):
        return TokenRefreshResult(auth=auth)

    refresh_token = tokens.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        return TokenRefreshResult(auth=auth, error="Token refresh failed: no refresh token is available.")

    body = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        }
    ).encode("ascii")
    request = Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    def perform_request() -> Mapping[str, Any]:
        opener = transport or (proxy_config or ProxyConfig()).open
        response = opener(request, timeout=REFRESH_TIMEOUT_SECONDS)
        try:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if not 200 <= status < 300:
                raise NetworkCallFailure(f"Token refresh failed with HTTP {status}.")
            payload = json.load(response)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        if not isinstance(payload, Mapping):
            raise NetworkCallFailure("Token refresh returned an unexpected response.")
        return payload

    try:
        payload = run_network_call(
            activity_log,
            TOKEN_URL,
            "token_refresh",
            perform_request,
            payload={"profile": profile.name},
        )
    except HTTPError as exc:
        return TokenRefreshResult(auth=auth, error=f"Token refresh failed with HTTP {exc.code}.")
    except (TimeoutError, URLError):
        return TokenRefreshResult(auth=auth, error="Token refresh failed after retrying the network connection.")
    except NetworkCallFailure as exc:
        return TokenRefreshResult(auth=auth, error=str(exc))
    except Exception as exc:
        return TokenRefreshResult(auth=auth, error=f"Token refresh failed: {type(exc).__name__}.")

    new_access_token = payload.get("access_token")
    if not isinstance(new_access_token, str) or not new_access_token:
        return TokenRefreshResult(auth=auth, error="Token refresh returned no access token.")

    updated_tokens = dict(tokens)
    updated_tokens["access_token"] = new_access_token
    new_refresh_token = payload.get("refresh_token")
    if isinstance(new_refresh_token, str) and new_refresh_token:
        updated_tokens["refresh_token"] = new_refresh_token
    new_id_token = payload.get("id_token")
    if isinstance(new_id_token, str) and new_id_token:
        updated_tokens["id_token"] = new_id_token

    updated_auth = dict(auth)
    updated_auth["tokens"] = updated_tokens
    checked_at = now or datetime.now(timezone.utc)
    updated_auth["last_refresh"] = checked_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        serialized = (json.dumps(updated_auth, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        atomic_write(profile.path, serialized)
    except Exception as exc:
        return TokenRefreshResult(auth=auth, error=f"Token refresh could not be saved: {type(exc).__name__}.")
    return TokenRefreshResult(auth=updated_auth, refreshed=True)


def _expires_soon(access_token: str, now: Optional[datetime]) -> bool:
    claims = decode_jwt(access_token)
    expires_at = claims.get("exp")
    if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
        return False
    current = now or datetime.now(timezone.utc)
    return float(expires_at) <= current.timestamp() + REFRESH_MARGIN_SECONDS

import base64
import json
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import parse_qs

from agent_switcher.core.identity import Identity
from agent_switcher.core.store import Profile
from agent_switcher.core.proxy import ProxyConfig
from agent_switcher.core.usage import USAGE_TIMEOUT_SECONDS, fetch_codex_usage


CHECKED_AT = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


class Response(BytesIO):
    def __init__(self, payload, status=200):
        if isinstance(payload, bytes):
            raw = payload
        else:
            raw = json.dumps(payload).encode("utf-8")
        super().__init__(raw)
        self.status = status

    def getcode(self):
        return self.status


def write_profile(tmp_path, **overrides):
    auth = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": "synthetic-access-token",
            "account_id": "account-synthetic",
        },
    }
    auth.update(overrides)
    path = tmp_path / "auth.work.json"
    path.write_text(json.dumps(auth), encoding="utf-8")
    return Profile(name="work", active=False, path=path, identity=Identity())


def make_jwt(exp):
    def encode(payload):
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{encode({'alg': 'none'})}.{encode({'exp': exp})}."


def usage_payload():
    return {
        "rate_limit": {
            "primary_window": {
                "used_percent": 12,
                "reset_at": 1785848400,
                "limit_window_seconds": 18000,
            },
            "secondary_window": None,
        }
    }


def test_fetch_usage_parses_success_and_sends_saved_profile_credentials(tmp_path):
    profile = write_profile(tmp_path)
    calls = []

    def transport(request, timeout):
        calls.append((request, timeout))
        return Response(
            {
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 12.5,
                        "reset_at": 1785848400,
                        "limit_window_seconds": 18000,
                    },
                    "secondary_window": {
                        "used_percent": 78,
                        "reset_at": "2026-08-10T12:00:00Z",
                        "limit_window_seconds": 604800,
                    },
                }
            }
        )

    usage = fetch_codex_usage(profile, transport=transport, now=CHECKED_AT)

    assert usage.available is True
    assert usage.five_hour_used_pct == 12.5
    assert usage.five_hour_reset_at == datetime(2026, 8, 4, 13, 0, tzinfo=timezone.utc)
    assert usage.weekly_used_pct == 78
    assert usage.weekly_reset_at == datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert usage.checked_at == CHECKED_AT
    request, timeout = calls[0]
    assert request.full_url == "https://chatgpt.com/backend-api/wham/usage"
    assert request.get_header("Authorization") == "Bearer synthetic-access-token"
    assert request.get_header("Chatgpt-account-id") == "account-synthetic"
    assert timeout == USAGE_TIMEOUT_SECONDS


def test_fetch_usage_returns_unavailable_for_403(tmp_path):
    usage = fetch_codex_usage(
        write_profile(tmp_path),
        transport=lambda _request, timeout: Response({}, status=403),
        now=CHECKED_AT,
    )

    assert usage.available is False
    assert usage.five_hour_used_pct is None
    assert usage.weekly_used_pct is None
    assert usage.unavailable_reason == "Usage service returned HTTP 403."


def test_fetch_usage_returns_unavailable_for_timeout(tmp_path):
    def timeout(_request, timeout):
        raise TimeoutError("synthetic timeout")

    usage = fetch_codex_usage(write_profile(tmp_path), transport=timeout, now=CHECKED_AT)

    assert usage.available is False
    assert usage.unavailable_reason == "Usage is unavailable: TimeoutError."


def test_fetch_usage_returns_unavailable_for_malformed_json(tmp_path):
    usage = fetch_codex_usage(
        write_profile(tmp_path),
        transport=lambda _request, timeout: Response(b"not-json"),
        now=CHECKED_AT,
    )

    assert usage.available is False
    assert usage.unavailable_reason == "Usage is unavailable: JSONDecodeError."


def test_fetch_usage_returns_stable_null_fields_for_unexpected_shape(tmp_path):
    usage = fetch_codex_usage(
        write_profile(tmp_path),
        transport=lambda _request, timeout: Response({"rate_limit": {}}),
        now=CHECKED_AT,
    )

    assert usage.as_dict() == {
        "available": False,
        "five_hour_used_pct": None,
        "five_hour_reset_at": None,
        "weekly_used_pct": None,
        "weekly_reset_at": None,
        "checked_at": "2026-08-04T12:00:00Z",
        "unavailable_reason": "Usage service returned an unexpected response.",
    }


def test_fetch_usage_classifies_a_lone_weekly_window_by_duration(tmp_path):
    usage = fetch_codex_usage(
        write_profile(tmp_path),
        transport=lambda _request, timeout: Response(
            {
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 31,
                        "reset_at": 1785848400,
                        "limit_window_seconds": 604800,
                    },
                    "secondary_window": None,
                }
            }
        ),
        now=CHECKED_AT,
    )

    assert usage.available is True
    assert usage.five_hour_used_pct is None
    assert usage.five_hour_reset_at is None
    assert usage.weekly_used_pct == 31
    assert usage.weekly_reset_at == datetime(2026, 8, 4, 13, 0, tzinfo=timezone.utc)


def test_fetch_usage_skips_non_chatgpt_and_api_key_profiles(tmp_path):
    calls = []

    def transport(_request, timeout):
        calls.append(timeout)
        return Response({})

    non_chatgpt = write_profile(tmp_path, auth_mode="apikey")
    assert fetch_codex_usage(non_chatgpt, transport=transport).available is False

    api_key = write_profile(tmp_path, OPENAI_API_KEY="synthetic-key")
    assert fetch_codex_usage(api_key, transport=transport).available is False
    assert calls == []


def test_near_expired_background_profile_refreshes_and_persists_before_usage(tmp_path):
    old_access = make_jwt(int(CHECKED_AT.timestamp()) + 10)
    profile = write_profile(
        tmp_path,
        tokens={
            "access_token": old_access,
            "refresh_token": "old-refresh",
            "account_id": "account-synthetic",
        },
    )
    live_path = tmp_path / "auth.json"
    live_path.write_bytes(b'{"live":"must-not-change"}')
    other_path = tmp_path / "auth.other.json"
    other_path.write_bytes(b'{"other":"must-not-change"}')
    events = []

    def refresh_transport(request, timeout):
        events.append("refresh")
        assert request.full_url == "https://auth.openai.com/oauth/token"
        assert request.get_method() == "POST"
        assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
        assert parse_qs(request.data.decode("ascii")) == {
            "grant_type": ["refresh_token"],
            "refresh_token": ["old-refresh"],
            "client_id": ["app_EMoamEEZ73f0CkXaXp7hrann"],
        }
        return Response({"access_token": "new-access", "refresh_token": "rotated-refresh"})

    def usage_transport(request, timeout):
        events.append("usage")
        persisted = json.loads(profile.path.read_text(encoding="utf-8"))
        assert persisted["tokens"]["access_token"] == "new-access"
        assert persisted["tokens"]["refresh_token"] == "rotated-refresh"
        assert request.get_header("Authorization") == "Bearer new-access"
        return Response(usage_payload())

    usage = fetch_codex_usage(
        profile,
        transport=usage_transport,
        refresh_transport=refresh_transport,
        now=CHECKED_AT,
    )

    assert usage.available is True
    assert events == ["refresh", "usage"]
    assert live_path.read_bytes() == b'{"live":"must-not-change"}'
    assert other_path.read_bytes() == b'{"other":"must-not-change"}'


def test_failed_background_token_refresh_degrades_without_usage_request(tmp_path):
    profile = write_profile(
        tmp_path,
        tokens={
            "access_token": make_jwt(int(CHECKED_AT.timestamp()) - 1),
            "refresh_token": "revoked-refresh",
            "account_id": "account-synthetic",
        },
    )
    before = profile.path.read_bytes()
    usage_calls = []

    usage = fetch_codex_usage(
        profile,
        transport=lambda _request, timeout: usage_calls.append(timeout),
        refresh_transport=lambda _request, timeout: Response({}, status=401),
        now=CHECKED_AT,
    )

    assert usage.available is False
    assert usage.unavailable_reason == "Token refresh failed with HTTP 401."
    assert usage_calls == []
    assert profile.path.read_bytes() == before


def test_live_profile_never_uses_background_refresh_or_writes_saved_file(tmp_path):
    profile = write_profile(
        tmp_path,
        tokens={
            "access_token": make_jwt(int(CHECKED_AT.timestamp()) - 1),
            "refresh_token": "must-not-be-used",
            "account_id": "account-synthetic",
        },
    )
    profile = replace(profile, active=True)
    before = profile.path.read_bytes()
    refresh_calls = []

    def usage_transport(request, timeout):
        assert request.get_header("Authorization").startswith("Bearer ey")
        return Response(usage_payload())

    usage = fetch_codex_usage(
        profile,
        transport=usage_transport,
        refresh_transport=lambda _request, timeout: refresh_calls.append(timeout),
        now=CHECKED_AT,
    )

    assert usage.available is True
    assert refresh_calls == []
    assert profile.path.read_bytes() == before


def test_proxy_is_used_for_token_refresh_and_usage_request(tmp_path):
    profile = write_profile(
        tmp_path,
        tokens={
            "access_token": make_jwt(int(CHECKED_AT.timestamp()) - 1),
            "refresh_token": "old-refresh",
            "account_id": "account-synthetic",
        },
    )
    calls = []

    class RecordingProxy(ProxyConfig):
        def open(self, request, timeout):
            calls.append((request.full_url, timeout))
            if request.full_url == "https://auth.openai.com/oauth/token":
                return Response({"access_token": "new-access", "refresh_token": "new-refresh"})
            return Response(usage_payload())

    usage = fetch_codex_usage(
        profile,
        proxy_config=RecordingProxy(mode="custom", url="http://proxy.test:8080"),
        now=CHECKED_AT,
    )

    assert usage.available is True
    assert calls == [
        ("https://auth.openai.com/oauth/token", 5.0),
        ("https://chatgpt.com/backend-api/wham/usage", 5.0),
    ]

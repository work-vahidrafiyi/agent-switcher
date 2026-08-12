import json
import stat

from agent_switcher.core.activity_log import ActivityLog
from agent_switcher.core.egress_guard import EgressGuard, resolve_public_ip
from agent_switcher.core.proxy import ProxyConfig


class Response:
    def __init__(self, payload=b"203.0.113.8\n", status=200):
        self.payload = payload
        self.status = status
        self.closed = False

    def read(self, limit=-1):
        return self.payload if limit < 0 else self.payload[:limit]

    def getcode(self):
        return self.status

    def close(self):
        self.closed = True


def test_first_egress_is_trusted_and_only_fingerprint_is_persisted(tmp_path):
    state = tmp_path / "egress.json"
    activity = ActivityLog(tmp_path / "activity.jsonl")
    guard = EgressGuard(state, activity_log=activity, resolver=lambda _proxy: "203.0.113.10")

    result = guard.check("work", "usage_check", ProxyConfig())

    assert result.status == "first"
    assert result.allowed is True
    assert "203.0.113.10" not in state.read_text(encoding="utf-8")
    assert len(json.loads(state.read_text(encoding="utf-8"))["profiles"]["work"]["fingerprint"]) == 64
    assert stat.S_IMODE(state.stat().st_mode) == 0o600
    network_events = activity.recent_network_calls()
    assert network_events[0]["payload"]["purpose"] == "egress_check"
    assert "203.0.113.10" not in (tmp_path / "activity.jsonl").read_text(encoding="utf-8")


def test_same_ip_is_allowed_and_changed_ip_requires_approval(tmp_path):
    addresses = iter(["198.51.100.1", "198.51.100.1", "198.51.100.2", "198.51.100.2"])
    guard = EgressGuard(tmp_path / "egress.json", resolver=lambda _proxy: next(addresses))

    first = guard.check("work", "login", ProxyConfig())
    same = guard.check("work", "usage_check", ProxyConfig())
    changed = guard.check("work", "account_switch", ProxyConfig())

    assert first.status == "first"
    assert same.status == "same"
    assert changed.status == "changed"
    assert changed.allowed is False
    assert changed.previous_fingerprint != changed.current_fingerprint

    guard.approve(changed)

    assert guard.check("work", "usage_check", ProxyConfig()).status == "same"


def test_failed_public_ip_check_is_fail_safe_without_overwriting_baseline(tmp_path):
    address = ["192.0.2.10"]

    def resolver(_proxy):
        value = address[0]
        if isinstance(value, Exception):
            raise value
        return value

    guard = EgressGuard(tmp_path / "egress.json", resolver=resolver)
    guard.check("personal", "usage_check", ProxyConfig())
    before = (tmp_path / "egress.json").read_bytes()
    address[0] = TimeoutError("route probe timed out")

    result = guard.check("personal", "usage_check", ProxyConfig())

    assert result.status == "unavailable"
    assert result.needs_confirmation is True
    assert "timed out" in result.error
    assert (tmp_path / "egress.json").read_bytes() == before


def test_guard_tracks_profile_rename_and_delete(tmp_path):
    state = tmp_path / "egress.json"
    guard = EgressGuard(state, resolver=lambda _proxy: "203.0.113.20")
    guard.check("old", "usage_check", ProxyConfig())

    guard.rename_profile("old", "new")
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert "old" not in payload["profiles"]
    assert "new" in payload["profiles"]

    guard.delete_profile("new")
    assert json.loads(state.read_text(encoding="utf-8"))["profiles"] == {}


def test_disabled_guard_does_not_call_public_ip_service(tmp_path):
    guard = EgressGuard(
        tmp_path / "egress.json",
        resolver=lambda _proxy: (_ for _ in ()).throw(AssertionError("must not run")),
        enabled=False,
    )

    assert guard.check("work", "usage_check", ProxyConfig()).status == "disabled"
    assert not (tmp_path / "egress.json").exists()


def test_public_ip_lookup_uses_configured_route_and_validates_response():
    response = Response()

    class Route:
        def __init__(self):
            self.calls = []

        def open(self, request, timeout):
            self.calls.append((request.full_url, timeout))
            return response

    route = Route()

    assert resolve_public_ip(route) == "203.0.113.8"
    assert route.calls == [("https://api.ipify.org", 8.0)]
    assert response.closed is True

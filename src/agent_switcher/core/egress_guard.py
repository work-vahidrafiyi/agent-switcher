from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Mapping, Optional
from urllib.request import Request

from .activity_log import ActivityLog
from .files import atomic_write
from .proxy import ProxyConfig


PUBLIC_IP_URL = "https://api.ipify.org"
PUBLIC_IP_TIMEOUT_SECONDS = 8.0
MAX_PUBLIC_IP_RESPONSE_BYTES = 128
EgressStatus = Literal["disabled", "first", "same", "changed", "unavailable"]
Resolver = Callable[[ProxyConfig], str]


@dataclass(frozen=True)
class EgressCheck:
    profile: str
    purpose: str
    status: EgressStatus
    previous_fingerprint: str = ""
    current_fingerprint: str = ""
    address_family: str = ""
    route_fingerprint: str = ""
    error: str = ""

    @property
    def allowed(self) -> bool:
        # The public-IP service is an advisory safety check. If it is blocked or
        # unavailable, it must not prevent the requested OpenAI operation.
        return self.status in {"disabled", "first", "same", "unavailable"}

    @property
    def needs_confirmation(self) -> bool:
        return self.status == "changed"


class EgressGuard:
    """Detect public egress-IP changes without persisting the raw address."""

    def __init__(
        self,
        path: Path,
        *,
        activity_log: Optional[ActivityLog] = None,
        resolver: Optional[Resolver] = None,
        enabled: bool = True,
    ) -> None:
        self.path = Path(path)
        self.activity_log = activity_log
        self.resolver = resolver or resolve_public_ip
        self.enabled = enabled
        self._lock = threading.RLock()
        self._state = self._load_state()
        self._unavailable_routes: dict[str, str] = {}

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def check(self, profile: str, purpose: str, proxy_config: ProxyConfig) -> EgressCheck:
        if not self.enabled:
            return EgressCheck(profile, purpose, "disabled")

        route_fingerprint = self._fingerprint(
            f"route\0{proxy_config.mode}\0{proxy_config.url}".encode("utf-8")
        )
        with self._lock:
            unavailable_error = self._unavailable_routes.get(route_fingerprint)
        if unavailable_error:
            return EgressCheck(
                profile,
                purpose,
                "unavailable",
                route_fingerprint=route_fingerprint[:12],
                error=unavailable_error,
            )
        try:
            public_ip = str(ipaddress.ip_address(self.resolver(proxy_config).strip()))
        except Exception as exc:
            error = str(exc) or type(exc).__name__
            with self._lock:
                # Avoid repeating the same blocked lookup for every account in
                # this app session. A different proxy route is still attempted.
                self._unavailable_routes[route_fingerprint] = error
            result = EgressCheck(
                profile,
                purpose,
                "unavailable",
                route_fingerprint=route_fingerprint[:12],
                error=error,
            )
            self._log(result)
            return result

        current = self._fingerprint(f"ip\0{public_ip}".encode("ascii"))
        family = "IPv6" if ":" in public_ip else "IPv4"
        with self._lock:
            profiles = self._state.setdefault("profiles", {})
            previous_record = profiles.get(profile) if isinstance(profiles, dict) else None
            previous = (
                previous_record.get("fingerprint", "")
                if isinstance(previous_record, Mapping)
                else ""
            )
            if not previous:
                status: EgressStatus = "first"
                self._store_observation(profile, current, family, route_fingerprint)
            elif hmac.compare_digest(previous, current):
                status = "same"
                self._store_observation(profile, current, family, route_fingerprint)
            else:
                status = "changed"

        result = EgressCheck(
            profile=profile,
            purpose=purpose,
            status=status,
            previous_fingerprint=previous,
            current_fingerprint=current,
            address_family=family,
            route_fingerprint=route_fingerprint[:12],
        )
        self._log(result)
        return result

    def approve(self, result: EgressCheck) -> None:
        if result.status != "changed" or not result.current_fingerprint:
            return
        with self._lock:
            profiles = self._state.setdefault("profiles", {})
            if not isinstance(profiles, dict):
                profiles = {}
                self._state["profiles"] = profiles
            # Public egress is shared by the app, not by one account. Trust the
            # acknowledged route for every known profile so a multi-account
            # usage refresh shows one warning for the IP change instead of one
            # warning per profile.
            known_profiles = set(profiles)
            known_profiles.add(result.profile)
            checked_at = _timestamp()
            for profile in known_profiles:
                profiles[profile] = {
                    "fingerprint": result.current_fingerprint,
                    "family": result.address_family,
                    "route_fingerprint": result.route_fingerprint,
                    "checked_at": checked_at,
                }
            self._save_state()
        if self.activity_log is not None:
            self.activity_log.append(
                "egress_approval",
                {
                    "profile": result.profile,
                    "purpose": result.purpose,
                    "fingerprint": result.current_fingerprint,
                },
            )

    def rename_profile(self, old: str, new: str) -> None:
        with self._lock:
            profiles = self._state.get("profiles")
            if not isinstance(profiles, dict) or old not in profiles:
                return
            profiles[new] = profiles.pop(old)
            self._save_state()

    def delete_profile(self, profile: str) -> None:
        with self._lock:
            profiles = self._state.get("profiles")
            if isinstance(profiles, dict) and profiles.pop(profile, None) is not None:
                self._save_state()

    def _store_observation(
        self,
        profile: str,
        fingerprint: str,
        family: str,
        route_fingerprint: str,
    ) -> None:
        profiles = self._state.setdefault("profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
            self._state["profiles"] = profiles
        profiles[profile] = {
            "fingerprint": fingerprint,
            "family": family,
            "route_fingerprint": route_fingerprint,
            "checked_at": _timestamp(),
        }
        self._save_state()

    def _fingerprint(self, value: bytes) -> str:
        key = bytes.fromhex(str(self._state["secret"]))
        return hmac.new(key, value, hashlib.sha256).hexdigest()

    def _load_state(self) -> dict[str, object]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            raw = {}
        secret = raw.get("secret") if isinstance(raw, Mapping) else None
        try:
            valid_secret = isinstance(secret, str) and len(bytes.fromhex(secret)) == 32
        except ValueError:
            valid_secret = False
        profiles = raw.get("profiles") if isinstance(raw, Mapping) else None
        return {
            "version": 1,
            "secret": secret if valid_secret else secrets.token_hex(32),
            "profiles": dict(profiles) if isinstance(profiles, Mapping) else {},
        }

    def _save_state(self) -> None:
        data = (json.dumps(self._state, indent=2, sort_keys=True) + "\n").encode("utf-8")
        atomic_write(self.path, data)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _log(self, result: EgressCheck) -> None:
        if self.activity_log is None:
            return
        payload = {
            "endpoint": PUBLIC_IP_URL,
            "profile": result.profile,
            "purpose": "egress_check",
            "guarded_purpose": result.purpose,
            "status": result.status,
            "success": result.status != "unavailable",
            "address_family": result.address_family,
            "route_fingerprint": result.route_fingerprint,
        }
        if result.error:
            payload["error"] = result.error
        self.activity_log.append("network_call", payload)


def resolve_public_ip(proxy_config: ProxyConfig) -> str:
    request = Request(
        PUBLIC_IP_URL,
        headers={"Accept": "text/plain", "User-Agent": "agent-switcher-ip-guard"},
        method="GET",
    )
    response = proxy_config.open(request, timeout=PUBLIC_IP_TIMEOUT_SECONDS)
    try:
        status = getattr(response, "status", None)
        if status is None:
            status = response.getcode()
        if status != 200:
            raise RuntimeError(f"Public IP check returned HTTP {status}.")
        raw = response.read(MAX_PUBLIC_IP_RESPONSE_BYTES + 1)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    if len(raw) > MAX_PUBLIC_IP_RESPONSE_BYTES:
        raise RuntimeError("Public IP response was larger than expected.")
    try:
        return str(ipaddress.ip_address(raw.decode("ascii").strip()))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("Public IP service returned an invalid address.") from exc


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

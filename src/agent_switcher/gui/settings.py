from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_switcher.core.files import atomic_write
from agent_switcher.core.proxy import ProxyConfig, ProxyConfigError


@dataclass(frozen=True)
class GuiSettings:
    auto_refresh_interval_ms: int = 15 * 60 * 1000
    request_delay_ms: int = 400
    offline_mode: bool = False
    ip_guard_enabled: bool = True
    low_quota_threshold_pct: int = 15
    smart_pick_stale_minutes: int = 10
    smart_pick_headroom_pct: int = 20
    global_hotkey_enabled: bool = True
    global_hotkey: str = "<ctrl>+<alt>+<space>"
    theme: str = "system"
    onboarding_seen: bool = False
    privacy_notice_suppressed: bool = False
    language: str = "en"
    proxy_mode: str = "none"
    proxy_url: str = ""


DEFAULT_SETTINGS = GuiSettings()


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> GuiSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return DEFAULT_SETTINGS
        if not isinstance(data, dict):
            return DEFAULT_SETTINGS
        try:
            proxy_config = ProxyConfig.from_values(data.get("proxy_mode"), data.get("proxy_url"))
        except ProxyConfigError:
            proxy_config = ProxyConfig()
        return GuiSettings(
            auto_refresh_interval_ms=_positive_int(data.get("auto_refresh_interval_ms"), DEFAULT_SETTINGS.auto_refresh_interval_ms),
            request_delay_ms=_positive_int(data.get("request_delay_ms"), DEFAULT_SETTINGS.request_delay_ms),
            offline_mode=data.get("offline_mode") is True,
            ip_guard_enabled=data.get("ip_guard_enabled") is not False,
            low_quota_threshold_pct=_percentage_int(
                data.get("low_quota_threshold_pct"), DEFAULT_SETTINGS.low_quota_threshold_pct
            ),
            smart_pick_stale_minutes=_positive_int(
                data.get("smart_pick_stale_minutes"), DEFAULT_SETTINGS.smart_pick_stale_minutes
            ),
            smart_pick_headroom_pct=_percentage_int(
                data.get("smart_pick_headroom_pct"), DEFAULT_SETTINGS.smart_pick_headroom_pct
            ),
            global_hotkey_enabled=data.get("global_hotkey_enabled") is not False,
            global_hotkey=_nonempty_string(data.get("global_hotkey"), DEFAULT_SETTINGS.global_hotkey),
            theme=_theme(data.get("theme")),
            onboarding_seen=data.get("onboarding_seen") is True,
            privacy_notice_suppressed=data.get("privacy_notice_suppressed") is True,
            language=_language(data.get("language")),
            proxy_mode=proxy_config.mode,
            proxy_url=proxy_config.url,
        )

    def save(self, settings: GuiSettings) -> None:
        data = (json.dumps(asdict(settings), indent=2, sort_keys=True) + "\n").encode("utf-8")
        atomic_write(self.path, data)


def _positive_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _percentage_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100 else default


def _nonempty_string(value: object, default: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _theme(value: object) -> str:
    return value if value in {"system", "dark", "light"} else DEFAULT_SETTINGS.theme


def _language(value: object) -> str:
    return value if value in {"en", "fa"} else DEFAULT_SETTINGS.language

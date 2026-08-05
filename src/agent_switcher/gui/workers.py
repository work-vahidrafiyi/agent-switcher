from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from agent_switcher.core.login import DeviceLogin, DeviceLoginManager, LoginError
from agent_switcher.core.providers.base import LoginMode
from agent_switcher.core.store import Store, StoreError
from agent_switcher.core.store import Profile

from .i18n import tr


class LoginWorker(QThread):
    url_ready = Signal(str)
    code_ready = Signal(str)
    line_ready = Signal(str)
    succeeded = Signal(object, object)
    failed = Signal(str)

    def __init__(self, store: Store, name: str, mode: LoginMode) -> None:
        super().__init__()
        self.store = store
        self.name = name
        self.runner = DeviceLogin(store.provider, mode=mode, proxy_config=store.proxy_config)

    def cancel(self) -> None:
        self.runner.cancel()

    def run(self) -> None:
        manager = DeviceLoginManager(self.store, runner=self.runner)
        try:
            profile, result = manager.add_profile(
                self.name,
                on_url=self.url_ready.emit,
                on_code=self.code_ready.emit,
                on_line=self.line_ready.emit,
            )
        except (LoginError, StoreError) as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(tr("Sign-in failed: {error}", error=exc))
            return
        self.succeeded.emit(profile, result)


class UsageRefreshWorker(QThread):
    profile_started = Signal(str)
    usage_ready = Signal(str, object)

    def __init__(self, store: Store, profiles: list[Profile], delay_ms: int) -> None:
        super().__init__()
        self.store = store
        self.profiles = profiles
        self.delay_ms = delay_ms

    def run(self) -> None:
        for index, profile in enumerate(self.profiles):
            if self.isInterruptionRequested():
                return
            self.profile_started.emit(profile.name)
            usage = self.store.fetch_usage(profile)
            self.usage_ready.emit(profile.name, usage)
            if index < len(self.profiles) - 1 and self.delay_ms > 0:
                self.msleep(self.delay_ms)

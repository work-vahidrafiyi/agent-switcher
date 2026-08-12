from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from agent_switcher.core.login import DeviceLogin, DeviceLoginManager, LoginError
from agent_switcher.core.providers.base import LoginMode
from agent_switcher.core.store import Store, StoreError
from agent_switcher.core.store import Profile
from agent_switcher.core.usage import Usage
from agent_switcher.core.updater import check_for_update, download_update
from agent_switcher import __version__

from .i18n import tr


class LoginWorker(QThread):
    url_ready = Signal(str)
    code_ready = Signal(str)
    line_ready = Signal(str)
    succeeded = Signal(object, object)
    failed = Signal(str)
    egress_attention = Signal(object)

    def __init__(self, store: Store, name: str, mode: LoginMode) -> None:
        super().__init__()
        self.store = store
        self.name = name
        self.runner = DeviceLogin(store.provider, mode=mode, proxy_config=store.proxy_config)
        self._egress_decision = threading.Event()
        self._egress_allowed = False

    def cancel(self) -> None:
        self._egress_allowed = False
        self._egress_decision.set()
        self.runner.cancel()

    def resolve_egress(self, allowed: bool) -> None:
        self._egress_allowed = allowed
        self._egress_decision.set()

    def run(self) -> None:
        check = self.store.check_egress(self.name, "login")
        if check.needs_confirmation:
            self._egress_decision.clear()
            self.egress_attention.emit(check)
            while not self._egress_decision.wait(0.1):
                if self.isInterruptionRequested():
                    return
            if not self._egress_allowed:
                self.failed.emit(tr("Sign-in was cancelled by IP Guard."))
                return
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
    egress_attention = Signal(object)

    def __init__(self, store: Store, profiles: list[Profile], delay_ms: int) -> None:
        super().__init__()
        self.store = store
        self.profiles = profiles
        self.delay_ms = delay_ms
        self._egress_decision = threading.Event()
        self._egress_allowed = False

    def resolve_egress(self, allowed: bool) -> None:
        self._egress_allowed = allowed
        self._egress_decision.set()

    def run(self) -> None:
        for index, profile in enumerate(self.profiles):
            if self.isInterruptionRequested():
                return
            self.profile_started.emit(profile.name)
            check = self.store.check_egress(profile.name, "usage_check")
            if check.needs_confirmation:
                self._egress_decision.clear()
                self.egress_attention.emit(check)
                while not self._egress_decision.wait(0.1):
                    if self.isInterruptionRequested():
                        return
                if not self._egress_allowed:
                    reason = (
                        tr("Usage check blocked because the public IP changed.")
                        if check.status == "changed"
                        else tr("Usage check blocked because the public IP could not be verified.")
                    )
                    self.usage_ready.emit(profile.name, Usage.unavailable(reason))
                    continue
            usage = self.store.fetch_usage(profile)
            self.usage_ready.emit(profile.name, usage)
            if index < len(self.profiles) - 1 and self.delay_ms > 0:
                self.msleep(self.delay_ms)


class EgressCheckWorker(QThread):
    checked = Signal(object)

    def __init__(self, store: Store, profile: str, purpose: str) -> None:
        super().__init__()
        self.store = store
        self.profile = profile
        self.purpose = purpose

    def run(self) -> None:
        self.checked.emit(self.store.check_egress(self.profile, self.purpose))


class UpdateCheckWorker(QThread):
    checked = Signal(object)
    failed = Signal(str)

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store

    def run(self) -> None:
        try:
            info = check_for_update(
                __version__,
                proxy_config=self.store.proxy_config,
                activity_log=self.store.activity_log,
            )
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)
            return
        self.checked.emit(info)


class UpdateDownloadWorker(QThread):
    progress_changed = Signal(int)
    prepared = Signal(object)
    failed = Signal(str)

    def __init__(self, store: Store, info: object) -> None:
        super().__init__()
        self.store = store
        self.info = info

    def run(self) -> None:
        try:
            prepared = download_update(
                self.info,
                proxy_config=self.store.proxy_config,
                activity_log=self.store.activity_log,
                progress=self.progress_changed.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)
            return
        self.prepared.emit(prepared)

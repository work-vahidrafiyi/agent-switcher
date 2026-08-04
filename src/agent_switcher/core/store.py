from __future__ import annotations

import os
import re
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .identity import Identity
from .files import atomic_write
from .activity_log import ActivityLog
from .providers.base import Provider
from .providers.codex import CodexProvider
from .usage import Usage, read_profile_account_id

NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
PROFILE_RE = re.compile(r"^auth\.([A-Za-z0-9._-]+)\.json$")


class StoreError(Exception):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    active: bool
    path: Path
    identity: Identity

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "active": self.active,
            "path": str(self.path),
            "identity": self.identity.as_dict(),
        }


@dataclass(frozen=True)
class ProfileDebugInfo:
    account_id: Optional[str]
    path: Path


@dataclass
class LoginTransaction:
    name: str
    previous_active: Optional[str]
    had_active_file: bool
    active_file_bytes: bytes
    had_auth_file: bool
    auth_file_bytes: bytes
    closed: bool = False


class Store:
    def __init__(self, provider: Optional[Provider] = None, activity_log: Optional[ActivityLog] = None) -> None:
        self.provider = provider or CodexProvider()
        self.home = self.provider.home()
        self.auth_file = self.provider.auth_file()
        self.active_file = self.home / ".active"
        self.activity_log = activity_log or ActivityLog.for_provider_home(self.home)

    def profile_path(self, name: str) -> Path:
        self.validate_name(name)
        return self.home / f"auth.{name}.json"

    def validate_name(self, name: str) -> None:
        if not NAME_RE.match(name):
            raise StoreError("Profile names may contain only letters, digits, dot, dash, or underscore.")

    def profiles(self) -> list[str]:
        if not self.home.is_dir():
            return []
        names = []
        for entry in self.home.iterdir():
            match = PROFILE_RE.match(entry.name)
            if match and entry.is_file():
                names.append(match.group(1))
        return sorted(names)

    def active(self) -> Optional[str]:
        try:
            value = self.active_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    def set_active(self, name: Optional[str]) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        if name is None:
            self._unlink(self.active_file)
            return
        self.validate_name(name)
        self._atomic_write(self.active_file, (name + "\n").encode("utf-8"))

    def profile(self, name: str) -> Profile:
        path = self.profile_path(name)
        if not path.is_file():
            raise StoreError(f"{name} has no saved credentials.")
        active = self.active() == name
        source = self.auth_file if active and self.auth_file.is_file() else path
        return Profile(name=name, active=active, path=path, identity=self.provider.parse_identity(source))

    def profile_list(self) -> list[Profile]:
        return [self.profile(name) for name in self.profiles()]

    def current_profile(self) -> Optional[Profile]:
        name = self.active()
        if not name:
            return None
        try:
            return self.profile(name)
        except StoreError:
            return None

    def running_processes(self) -> list[str]:
        return self.provider.running_processes()

    def fetch_usage(self, profile: Profile) -> Usage:
        fetcher = getattr(self.provider, "fetch_usage", None)
        if not callable(fetcher):
            return Usage.unavailable("Usage is not supported by this provider.")
        try:
            current = self.active()
            usage_profile = Profile(
                name=profile.name,
                active=current == profile.name,
                path=profile.path,
                identity=profile.identity,
            )
            parameters = inspect.signature(fetcher).parameters
            if "activity_log" in parameters:
                return fetcher(usage_profile, activity_log=self.activity_log)
            return fetcher(usage_profile)
        except Exception as exc:
            return Usage.unavailable(f"Usage is unavailable: {type(exc).__name__}.")

    def profile_debug_info(self, profile: Profile) -> ProfileDebugInfo:
        return ProfileDebugInfo(account_id=read_profile_account_id(profile), path=profile.path)

    def sync_live(self) -> Optional[str]:
        """Save live auth.json into the active profile before switching away."""
        current = self.active()
        if current and self.auth_file.is_file():
            self._atomic_copy(self.auth_file, self.profile_path(current))
            return current
        return None

    def switch(self, name: str) -> Optional[str]:
        target = self.profile_path(name)
        if not target.is_file():
            raise StoreError(f"{name} has no saved credentials.")

        previous = self.sync_live()
        self._atomic_copy(target, self.auth_file)
        self.set_active(name)
        self.activity_log.append("switch", {"from": previous, "to": name})
        return previous

    def rename(self, old: str, new: str) -> None:
        old_path = self.profile_path(old)
        new_path = self.profile_path(new)
        if not old_path.is_file():
            raise StoreError(f"{old} has no saved credentials.")
        if new_path.exists():
            raise StoreError(f"{new} already exists.")
        self.home.mkdir(parents=True, exist_ok=True)
        old_path.replace(new_path)
        if self.active() == old:
            self.set_active(new)

    def delete(self, name: str) -> None:
        path = self.profile_path(name)
        if not path.exists():
            raise StoreError(f"{name} has no saved credentials.")
        path.unlink()
        if self.active() == name:
            self.set_active(None)

    def begin_login(self, name: str) -> LoginTransaction:
        self.validate_name(name)
        if self.profile_path(name).exists():
            raise StoreError(f"{name} already exists.")

        had_active_file, active_bytes = self._read_snapshot(self.active_file)
        had_auth_file, auth_bytes = self._read_snapshot(self.auth_file)
        previous = self.sync_live()
        self._unlink(self.auth_file)
        return LoginTransaction(
            name=name,
            previous_active=previous,
            had_active_file=had_active_file,
            active_file_bytes=active_bytes,
            had_auth_file=had_auth_file,
            auth_file_bytes=auth_bytes,
        )

    def commit_login(self, transaction: LoginTransaction) -> Profile:
        self._ensure_open(transaction)
        if not self.auth_file.is_file():
            raise StoreError("Login did not create auth.json.")
        target = self.profile_path(transaction.name)
        if target.exists():
            raise StoreError(f"{transaction.name} already exists.")
        self._atomic_copy(self.auth_file, target)
        self.set_active(transaction.name)
        transaction.closed = True
        return self.profile(transaction.name)

    def rollback_login(self, transaction: LoginTransaction) -> None:
        if transaction.closed:
            return
        if transaction.had_auth_file:
            self._atomic_write(self.auth_file, transaction.auth_file_bytes)
        else:
            self._unlink(self.auth_file)

        if transaction.had_active_file:
            self._atomic_write(self.active_file, transaction.active_file_bytes)
        else:
            self._unlink(self.active_file)
        transaction.closed = True

    def _ensure_open(self, transaction: LoginTransaction) -> None:
        if transaction.closed:
            raise StoreError("Login transaction is already closed.")

    def _read_snapshot(self, path: Path) -> tuple[bool, bytes]:
        try:
            return True, path.read_bytes()
        except OSError:
            return False, b""

    def _atomic_copy(self, source: Path, target: Path) -> None:
        data = source.read_bytes()
        self._atomic_write(target, data)
        try:
            os.utime(target, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
        except OSError:
            pass

    def _atomic_write(self, target: Path, data: bytes) -> None:
        atomic_write(target, data)

    def _unlink(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, TYPE_CHECKING

from ..identity import Identity
from ..usage import Usage
from ..activity_log import ActivityLog

if TYPE_CHECKING:
    from ..store import Profile


LoginMode = Literal["device", "browser"]


class Provider(Protocol):
    name: str

    def home(self) -> Path:
        ...

    def auth_file(self) -> Path:
        ...

    def login_command(self, mode: LoginMode = "device") -> list[str]:
        ...

    def parse_identity(self, path: Path) -> Identity:
        ...

    def running_processes(self) -> list[str]:
        ...

    def fetch_usage(self, profile: "Profile", activity_log: ActivityLog = None) -> Usage:
        """Optional capability; Store supplies this fallback when absent."""
        return Usage.unavailable("Usage is not supported by this provider.")

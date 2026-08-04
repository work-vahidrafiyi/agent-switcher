from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..identity import Identity, parse_auth_identity
from ..usage import Usage, fetch_codex_usage
from ..activity_log import ActivityLog
from .base import LoginMode

if TYPE_CHECKING:
    from ..store import Profile


class CodexProvider:
    name = "codex"

    def __init__(self, home: Optional[Path] = None) -> None:
        self._home = Path(home) if home is not None else Path(
            os.environ.get("CODEX_HOME") or Path.home() / ".codex"
        )

    def home(self) -> Path:
        return self._home

    def auth_file(self) -> Path:
        return self.home() / "auth.json"

    def login_command(self, mode: LoginMode = "device") -> list[str]:
        command = ["codex", "login"]
        if mode == "device":
            command.append("--device-auth")
        return command

    def parse_identity(self, path: Path) -> Identity:
        return parse_auth_identity(path)

    def running_processes(self) -> list[str]:
        if os.name == "nt":
            return self._running_processes_windows()
        return self._running_processes_unix()

    def fetch_usage(self, profile: "Profile", activity_log: ActivityLog = None) -> Usage:
        return fetch_codex_usage(profile, activity_log=activity_log)

    def _running_processes_unix(self) -> list[str]:
        try:
            result = subprocess.run(
                ["pgrep", "-a", "-f", r"(^|/)codex($| )"],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception:
            return []
        return [
            line
            for line in result.stdout.splitlines()
            if "agent-switcher" not in line and "codex-switch" not in line
        ]

    def _running_processes_windows(self) -> list[str]:
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq codex.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=no_window,
            )
        except Exception:
            return []
        lines = [line.strip() for line in result.stdout.splitlines()]
        return [line for line in lines if line and "codex.exe" in line.lower()]

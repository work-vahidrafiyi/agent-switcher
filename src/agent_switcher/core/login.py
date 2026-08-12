from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol
from pathlib import Path
from html import unescape

from .providers.base import LoginMode, Provider
from .store import Store, StoreError
from .activity_log import run_network_call
from .proxy import ProxyConfig

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\r")
URL_RE = re.compile(r"https?://[^\s'\"<>\)\]]+")
CODE_DASHED_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4,6})\b")
CODE_PLAIN_RE = re.compile(r"\b([A-Z0-9]{6,10})\b")

Callback = Optional[Callable[[str], None]]


class LoginError(Exception):
    pass


@dataclass
class DeviceLoginResult:
    ok: bool
    returncode: int = 1
    error: Optional[str] = None
    url: Optional[str] = None
    code: Optional[str] = None
    raw_output: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "error": self.error,
            "url": self.url,
            "code": self.code,
            "raw_output": self.raw_output,
        }


class LoginRunner(Protocol):
    def run(self, on_url: Callback = None, on_code: Callback = None, on_line: Callback = None) -> DeviceLoginResult:
        ...


class DeviceLoginOutputParser:
    def __init__(self, mode: LoginMode = "device") -> None:
        self.mode = mode
        self.url: Optional[str] = None
        self.code: Optional[str] = None
        self.raw_output: list[str] = []
        self._url_rank = -1

    def feed(self, text: str, on_url: Callback = None, on_code: Callback = None, on_line: Callback = None) -> None:
        clean = ANSI_RE.sub("\n", text)
        for line in clean.splitlines():
            line = line.strip()
            if line:
                self.feed_line(line, on_url=on_url, on_code=on_code, on_line=on_line)

    def feed_line(self, line: str, on_url: Callback = None, on_code: Callback = None, on_line: Callback = None) -> None:
        self.raw_output.append(line)
        if on_line:
            on_line(line)

        urls = URL_RE.findall(line)
        if urls:
            ranked = max((self._url_priority(url), index, url) for index, url in enumerate(urls))
            rank, _index, raw_url = ranked
            if self.url is None or rank > self._url_rank:
                self.url = unescape(raw_url).rstrip(".,;:")
                self._url_rank = rank
                if on_url:
                    on_url(self.url)

        if self.mode == "device" and self.code is None:
            match = CODE_DASHED_RE.search(line)
            if match is None and re.search(r"code", line, re.I):
                for candidate in CODE_PLAIN_RE.finditer(line):
                    value = candidate.group(1)
                    if not value.isdigit() or len(value) >= 6:
                        match = candidate
                        break
            if match:
                self.code = match.group(1)
                if on_code:
                    on_code(self.code)

    def _url_priority(self, url: str) -> int:
        lowered = url.lower()
        if self.mode == "device":
            if "device" in lowered or "activate" in lowered:
                return 3
            if "oauth" in lowered or "authorize" in lowered:
                return 1
        elif "oauth" in lowered or "authorize" in lowered:
            return 3
        return 2 if "auth.openai.com" in lowered else 0


class DeviceLogin:
    def __init__(
        self,
        provider: Provider,
        mode: LoginMode = "device",
        proxy_config: Optional[ProxyConfig] = None,
    ) -> None:
        self.provider = provider
        self.mode = mode
        self.proxy_config = proxy_config or ProxyConfig()
        self.proc: Optional[subprocess.Popen[bytes]] = None
        self._stop = threading.Event()

    def cancel(self) -> None:
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(self.proc.pid, signal.SIGTERM)
                else:
                    self.proc.kill()
            except Exception:
                pass

    def run(self, on_url: Callback = None, on_code: Callback = None, on_line: Callback = None) -> DeviceLoginResult:
        command = self._resolve_command(self.provider.login_command(self.mode))
        if command is None:
            if self.provider.name == "codex":
                error = (
                    "Codex CLI was not found. Install it with "
                    "npm install -g @openai/codex, then try again."
                )
            else:
                error = f"{self.provider.name} CLI is not installed."
            return DeviceLoginResult(ok=False, error=error, returncode=127)
        if os.name == "posix":
            return self._run_pty(command, on_url=on_url, on_code=on_code, on_line=on_line)
        return self._run_pipes(command, on_url=on_url, on_code=on_code, on_line=on_line)

    def _resolve_command(self, command: list[str]) -> Optional[list[str]]:
        if not command:
            return None
        exe = shutil.which(command[0]) or _find_desktop_executable(command[0])
        if not exe:
            return None
        resolved = [exe, *command[1:]]
        if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", *resolved]
        return resolved

    def _run_pty(self, command: list[str], on_url: Callback, on_code: Callback, on_line: Callback) -> DeviceLoginResult:
        import pty
        import select

        parser = DeviceLoginOutputParser(self.mode)
        master, slave = pty.openpty()
        try:
            self.proc = subprocess.Popen(
                command,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True,
                start_new_session=True,
                env=self._subprocess_environment(),
            )
        except Exception as exc:
            os.close(master)
            os.close(slave)
            return DeviceLoginResult(ok=False, error=str(exc), returncode=1)

        os.close(slave)
        buffer = ""
        try:
            while not self._stop.is_set():
                ready, _, _ = select.select([master], [], [], 0.25)
                if ready:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", "replace")
                    lines = ANSI_RE.sub("\n", buffer).split("\n")
                    buffer = lines.pop()
                    for line in lines:
                        line = line.strip()
                        if line:
                            parser.feed_line(line, on_url=on_url, on_code=on_code, on_line=on_line)
                elif self.proc.poll() is not None:
                    break
        finally:
            try:
                os.close(master)
            except OSError:
                pass

        if buffer.strip():
            parser.feed(buffer, on_url=on_url, on_code=on_code, on_line=on_line)

        returncode = self.proc.wait() if self.proc else 1
        return self._finish_result(returncode, parser)

    def _run_pipes(self, command: list[str], on_url: Callback, on_code: Callback, on_line: Callback) -> DeviceLoginResult:
        parser = DeviceLoginOutputParser(self.mode)
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = self._subprocess_environment(NO_COLOR="1", TERM="dumb")
        try:
            self.proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=no_window,
                env=env,
            )
        except Exception as exc:
            return DeviceLoginResult(ok=False, error=str(exc), returncode=1)

        assert self.proc.stdout is not None
        buffer = ""
        while not self._stop.is_set():
            chunk = self.proc.stdout.read(1)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", "replace")
            if chunk in (b"\n", b"\r"):
                parser.feed(buffer, on_url=on_url, on_code=on_code, on_line=on_line)
                buffer = ""

        if buffer.strip():
            parser.feed(buffer, on_url=on_url, on_code=on_code, on_line=on_line)

        returncode = self.proc.wait() if self.proc else 1
        return self._finish_result(returncode, parser)

    def _subprocess_environment(self, **updates: str) -> dict[str, str]:
        return self.proxy_config.subprocess_environment(**updates)

    def _finish_result(self, returncode: int, parser: DeviceLoginOutputParser) -> DeviceLoginResult:
        if self._stop.is_set():
            return DeviceLoginResult(
                ok=False,
                returncode=returncode,
                error="Cancelled",
                url=parser.url,
                code=parser.code,
                raw_output=parser.raw_output,
            )
        ok = returncode == 0 and self.provider.auth_file().is_file()
        error = None if ok else f"{self.provider.name} login exited with {returncode}"
        return DeviceLoginResult(
            ok=ok,
            returncode=returncode,
            error=error,
            url=parser.url,
            code=parser.code,
            raw_output=parser.raw_output,
        )


class DeviceLoginManager:
    def __init__(self, store: Store, runner: Optional[LoginRunner] = None) -> None:
        self.store = store
        self.runner = runner or DeviceLogin(store.provider, proxy_config=store.proxy_config)

    def add_profile(self, name: str, on_url: Callback = None, on_code: Callback = None, on_line: Callback = None):
        transaction = self.store.begin_login(name)
        try:
            mode = getattr(self.runner, "mode", "device")
            endpoint = "https://auth.openai.com/oauth/authorize"
            result = run_network_call(
                self.store.activity_log,
                endpoint,
                "login",
                lambda: self.runner.run(on_url=on_url, on_code=on_code, on_line=on_line),
                payload={"profile": name, "mode": mode},
                describe=lambda value: {"success": value.ok, "error": value.error},
            )
            if not result.ok:
                raise LoginError(result.error or "Login failed.")
            profile = self.store.commit_login(transaction)
            self.store.activity_log.append("login", {"profile": name, "mode": mode})
            return profile, result
        except BaseException:
            try:
                self.store.rollback_login(transaction)
            except StoreError:
                pass
            raise


def _find_desktop_executable(name: str) -> Optional[str]:
    """Find CLIs omitted from the PATH inherited by desktop launchers."""
    home = Path.home()
    candidates: list[Path] = []
    if os.name == "nt":
        suffixes = (".cmd", ".exe", ".bat", "")
        roots = []
        if os.environ.get("APPDATA"):
            roots.append(Path(os.environ["APPDATA"]) / "npm")
        if os.environ.get("LOCALAPPDATA"):
            roots.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "nodejs")
        if os.environ.get("ProgramFiles"):
            roots.append(Path(os.environ["ProgramFiles"]) / "nodejs")
        for root in roots:
            candidates.extend(root / f"{name}{suffix}" for suffix in suffixes)
    else:
        candidates.extend(
            [
                home / ".local" / "bin" / name,
                home / ".npm-global" / "bin" / name,
                home / ".npm" / "bin" / name,
                Path("/usr/local/bin") / name,
                Path("/opt/homebrew/bin") / name,
                Path("/snap/bin") / name,
            ]
        )
        nvm_root = Path(os.environ.get("NVM_DIR", str(home / ".nvm"))) / "versions" / "node"
        if nvm_root.is_dir():
            candidates.extend(
                sorted(nvm_root.glob(f"*/bin/{name}"), key=_node_version, reverse=True)
            )
    for candidate in candidates:
        if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
            return str(candidate)
    return None


def _node_version(path: Path) -> tuple[int, ...]:
    values = re.findall(r"\d+", path.parent.parent.name)
    return tuple(int(value) for value in values)

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_switcher.core.login import (
    DeviceLogin,
    DeviceLoginManager,
    DeviceLoginOutputParser,
    DeviceLoginResult,
    LoginError,
)
from agent_switcher.core.providers.codex import CodexProvider
from agent_switcher.core.proxy import ProxyConfig
from agent_switcher.core.store import Store


def test_core_login_import_does_not_require_unix_terminal_modules():
    source_root = Path(__file__).resolve().parents[1] / "src"
    script = f"""
import sys
sys.path.insert(0, {str(source_root)!r})

class BlockUnixTerminalModules:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {{"pty", "termios"}}:
            raise ModuleNotFoundError(fullname)
        return None

sys.meta_path.insert(0, BlockUnixTerminalModules())
import agent_switcher.core.login
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


class FailingRunner:
    def __init__(self, auth_file, replacement):
        self.auth_file = auth_file
        self.replacement = replacement

    def run(self, on_url=None, on_code=None, on_line=None):
        self.auth_file.write_bytes(self.replacement)
        if on_line:
            on_line("Cancelled")
        return DeviceLoginResult(ok=False, returncode=1, error="Cancelled")


def test_login_failure_restores_previous_active_profile_exactly(tmp_path):
    provider = CodexProvider(home=tmp_path)
    store = Store(provider)
    live_auth = b'{"tokens":{"refresh_token":"rotated-live"},"last_refresh":"2026-08-04T01:02:03Z"}'
    old_saved_auth = b'{"tokens":{"refresh_token":"old-saved"}}'
    active_file = b"work"

    (tmp_path / "auth.work.json").write_bytes(old_saved_auth)
    (tmp_path / "auth.json").write_bytes(live_auth)
    (tmp_path / ".active").write_bytes(active_file)

    manager = DeviceLoginManager(store, runner=FailingRunner(provider.auth_file(), b'{"partial":"new-login"}'))

    with pytest.raises(LoginError):
        manager.add_profile("new-account")

    assert (tmp_path / "auth.json").read_bytes() == live_auth
    assert (tmp_path / ".active").read_bytes() == active_file
    assert (tmp_path / "auth.work.json").read_bytes() == live_auth
    assert not (tmp_path / "auth.new-account.json").exists()


def test_device_login_parser_handles_ansi_and_code_on_separate_line():
    parser = DeviceLoginOutputParser()
    urls = []
    codes = []
    lines = []

    parser.feed(
        "\x1b[32mOpen https://auth.openai.com/activate to continue\x1b[0m\n"
        "Your one-time code is\n"
        "ABCD-123456\n",
        on_url=urls.append,
        on_code=codes.append,
        on_line=lines.append,
    )

    assert urls == ["https://auth.openai.com/activate"]
    assert codes == ["ABCD-123456"]
    assert lines == [
        "Open https://auth.openai.com/activate to continue",
        "Your one-time code is",
        "ABCD-123456",
    ]


def test_device_login_parser_handles_plain_code_on_same_line():
    parser = DeviceLoginOutputParser()
    codes = []

    parser.feed("Enter code WXYZ9876 when prompted", on_code=codes.append)

    assert codes == ["WXYZ9876"]


def test_browser_login_parser_captures_url_but_ignores_code():
    parser = DeviceLoginOutputParser(mode="browser")
    urls = []
    codes = []

    parser.feed(
        "If the browser does not open, visit https://auth.openai.com/oauth/authorize\n"
        "Ignore code ABCD-123456 in browser mode",
        on_url=urls.append,
        on_code=codes.append,
    )

    assert urls == ["https://auth.openai.com/oauth/authorize"]
    assert codes == []
    assert parser.code is None


def test_codex_login_command_supports_device_and_browser_modes(tmp_path):
    provider = CodexProvider(home=tmp_path)

    assert provider.login_command("device") == ["codex", "login", "--device-auth"]
    assert provider.login_command("browser") == ["codex", "login"]


def test_login_subprocess_uses_configured_proxy_and_removes_bypass_list(tmp_path):
    runner = DeviceLogin(
        CodexProvider(home=tmp_path),
        proxy_config=ProxyConfig.from_values("custom", "http://proxy.test:8080"),
    )

    environment = runner.proxy_config.subprocess_environment(
        {"NO_PROXY": "auth.openai.com", "KEEP_ME": "yes"},
        NO_COLOR="1",
    )

    assert environment["HTTP_PROXY"] == "http://proxy.test:8080"
    assert environment["HTTPS_PROXY"] == "http://proxy.test:8080"
    assert environment["NO_COLOR"] == "1"
    assert environment["KEEP_ME"] == "yes"
    assert "NO_PROXY" not in environment

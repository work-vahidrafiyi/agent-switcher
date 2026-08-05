import json
import tomllib

import pytest
from datetime import datetime, timezone

from agent_switcher import cli
from agent_switcher.cli import build_parser, main
from agent_switcher.core.usage import Usage
from agent_switcher import __version__
from agent_switcher.core.proxy import ProxyConfig


def test_json_flag_works_after_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    code = main(["list", "--json"])

    assert code == 0
    out = capsys.readouterr().out
    assert json.loads(out) == {"active": None, "ok": True, "profiles": []}


def test_json_flag_works_before_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    code = main(["--json", "list"])

    assert code == 0
    out = capsys.readouterr().out
    assert json.loads(out) == {"active": None, "ok": True, "profiles": []}


def test_gui_subcommand_launches_gui(monkeypatch):
    called = []
    monkeypatch.setattr(cli, "_launch_gui", lambda: called.append(True) or 0)

    assert main(["gui"]) == 0
    assert called == [True]


def test_help_shows_gui_subcommand(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])

    assert exc.value.code == 0
    assert "gui" in capsys.readouterr().out


def test_version_uses_package_metadata(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"asw {__version__}"


def test_script_entrypoints_are_asw_only():
    with open("pyproject.toml", "rb") as handle:
        scripts = tomllib.load(handle)["project"]["scripts"]

    assert scripts == {"asw": "agent_switcher.cli:main"}


def test_list_details_includes_stable_usage_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.work.json").write_text("{}", encoding="utf-8")
    checked = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    usage = Usage(
        five_hour_used_pct=20,
        five_hour_reset_at=checked,
        weekly_used_pct=40,
        weekly_reset_at=checked,
        checked_at=checked,
    )
    monkeypatch.setattr(cli.CodexProvider, "fetch_usage", lambda _self, _profile: usage)

    assert main(["list", "--details", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["profiles"][0]["usage"] == {
        "available": True,
        "checked_at": "2026-08-04T12:00:00Z",
        "five_hour_reset_at": "2026-08-04T12:00:00Z",
        "five_hour_used_pct": 20,
        "unavailable_reason": None,
        "weekly_reset_at": "2026-08-04T12:00:00Z",
        "weekly_used_pct": 40,
    }


def test_list_without_details_does_not_fetch_or_add_usage(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.work.json").write_text("{}", encoding="utf-8")

    def fail_if_called(_self, _profile):
        raise AssertionError("usage fetch should be opt-in")

    monkeypatch.setattr(cli.CodexProvider, "fetch_usage", fail_if_called)

    assert main(["list", "--json"]) == 0
    profile = json.loads(capsys.readouterr().out)["profiles"][0]
    assert "usage" not in profile


def test_cli_uses_proxy_saved_by_gui(monkeypatch, tmp_path, capsys):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    state_home = tmp_path / "agent-switcher"
    state_home.mkdir()
    (state_home / "settings.json").write_text(
        '{"proxy_mode":"custom","proxy_url":"http://proxy.test:8080"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    configured = []
    original = cli.Store.set_proxy_config

    def capture(store, proxy_config):
        configured.append(proxy_config)
        original(store, proxy_config)

    monkeypatch.setattr(cli.Store, "set_proxy_config", capture)

    assert main(["list", "--json"]) == 0
    assert configured == [ProxyConfig(mode="custom", url="http://proxy.test:8080")]
    assert json.loads(capsys.readouterr().out)["profiles"] == []

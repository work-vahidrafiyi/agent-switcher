import json

import pytest

from agent_switcher.core.providers.codex import CodexProvider
from agent_switcher.core.store import Store, StoreError


def write_json(path, payload):
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_switch_syncs_live_before_swapping_so_rotated_token_is_not_lost(tmp_path):
    store = Store(CodexProvider(home=tmp_path))
    saved_work = {"tokens": {"refresh_token": "stale-work"}}
    rotated_work = {"tokens": {"refresh_token": "rotated-work"}, "last_refresh": "2026-08-04T10:00:00Z"}
    personal = {"tokens": {"refresh_token": "personal"}}

    write_json(tmp_path / "auth.work.json", saved_work)
    write_json(tmp_path / "auth.personal.json", personal)
    write_json(tmp_path / "auth.json", rotated_work)
    store.set_active("work")

    previous = store.switch("personal")

    assert previous == "work"
    assert read_json(tmp_path / "auth.work.json") == rotated_work
    assert read_json(tmp_path / "auth.json") == personal
    assert store.active() == "personal"


def test_profile_discovery_ignores_auth_json_and_malformed_names(tmp_path):
    store = Store(CodexProvider(home=tmp_path))
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")
    (tmp_path / "auth.work.json").write_text("{}", encoding="utf-8")
    (tmp_path / "auth.client-1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "auth.bad name.json").write_text("{}", encoding="utf-8")
    (tmp_path / "auth.missing_suffix").write_text("{}", encoding="utf-8")
    (tmp_path / "auth.dir.json").mkdir()

    assert store.profiles() == ["client-1", "work"]


def test_store_rejects_invalid_profile_names(tmp_path):
    store = Store(CodexProvider(home=tmp_path))

    with pytest.raises(StoreError):
        store.profile_path("bad name")


def test_delete_active_profile_leaves_live_auth_file_untouched(tmp_path):
    store = Store(CodexProvider(home=tmp_path))
    live_auth = {"tokens": {"refresh_token": "still-live"}}

    write_json(tmp_path / "auth.work.json", {"tokens": {"refresh_token": "saved"}})
    write_json(tmp_path / "auth.json", live_auth)
    store.set_active("work")

    store.delete("work")

    assert not (tmp_path / "auth.work.json").exists()
    assert read_json(tmp_path / "auth.json") == live_auth
    assert store.active() is None

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from agent_switcher.core.updater import (
    PreparedUpdate,
    ReleaseAsset,
    UpdateError,
    UpdateInfo,
    UnsupportedUpdateError,
    apply_staged_update,
    asset_name_for_platform,
    check_for_update,
    download_update,
    launch_update_helper,
    run_update_helper,
    version_is_newer,
)


class Response(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(payload)
        self.status = status

    def getcode(self):
        return self.status


def release_payload(version="0.3.0", asset_bytes=b"release-asset"):
    asset_name = "agent-switcher-linux-x86_64.tar.gz"
    return {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/work-vahidrafiyi/agent-switcher/releases/tag/v{version}",
        "body": "### Fixed\n\n- Synthetic release notes",
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": (
                    "https://github.com/work-vahidrafiyi/agent-switcher/"
                    f"releases/download/v{version}/{asset_name}"
                ),
                "size": len(asset_bytes),
                "digest": f"sha256:{hashlib.sha256(asset_bytes).hexdigest()}",
            }
        ],
    }


def json_transport(payload):
    encoded = json.dumps(payload).encode("utf-8")
    return lambda _request, timeout: Response(encoded)


def make_linux_archive(path, member_name="agent-switcher", contents=b"new executable"):
    with tarfile.open(path, "w:gz") as bundle:
        member = tarfile.TarInfo(member_name)
        member.mode = 0o755
        member.size = len(contents)
        bundle.addfile(member, io.BytesIO(contents))
    return path.read_bytes()


def test_version_comparison_handles_stable_and_prerelease_versions():
    assert version_is_newer("0.3.0", "0.2.1") is True
    assert version_is_newer("1.0.0", "1.0.0-rc.1") is True
    assert version_is_newer("1.0.0-rc.1", "1.0.0") is False
    assert version_is_newer("0.2.1", "0.2.1") is False


def test_update_check_selects_current_platform_asset_and_digest():
    payload = release_payload()

    info = check_for_update(
        "0.2.1",
        transport=json_transport(payload),
        system_name="Linux",
        machine="x86_64",
    )

    assert info.latest_version == "0.3.0"
    assert info.asset.name == "agent-switcher-linux-x86_64.tar.gz"
    assert len(info.asset.sha256) == 64
    assert info.release_url.endswith("/v0.3.0")


def test_update_check_returns_none_when_current_version_is_latest():
    assert check_for_update(
        "0.3.0",
        transport=json_transport(release_payload()),
        system_name="Linux",
        machine="x86_64",
    ) is None


def test_update_check_rejects_asset_without_github_digest():
    payload = release_payload()
    payload["assets"][0]["digest"] = None

    with pytest.raises(UpdateError, match="SHA-256"):
        check_for_update(
            "0.2.1",
            transport=json_transport(payload),
            system_name="Linux",
            machine="x86_64",
        )


def test_asset_selection_rejects_unsupported_architecture():
    with pytest.raises(UnsupportedUpdateError):
        asset_name_for_platform(system_name="Linux", machine="aarch64")


def test_asset_selection_supports_windows_x86_64():
    assert (
        asset_name_for_platform(system_name="Windows", machine="AMD64")
        == "agent-switcher-windows-x86_64.exe"
    )


def test_download_verifies_digest_and_safely_extracts_linux_binary(tmp_path):
    archive_path = tmp_path / "fixture.tar.gz"
    archive_bytes = make_linux_archive(archive_path)
    asset = ReleaseAsset(
        "agent-switcher-linux-x86_64.tar.gz",
        "https://github.com/work-vahidrafiyi/agent-switcher/releases/download/v0.3.0/agent-switcher-linux-x86_64.tar.gz",
        len(archive_bytes),
        hashlib.sha256(archive_bytes).hexdigest(),
    )
    info = UpdateInfo("0.2.1", "0.3.0", "v0.3.0", "https://github.com/release", "notes", asset)
    progress = []

    prepared = download_update(
        info,
        transport=lambda _request, timeout: Response(archive_bytes),
        progress=progress.append,
        destination_root=tmp_path,
    )

    assert prepared.executable.read_bytes() == b"new executable"
    assert prepared.executable.stat().st_mode & 0o100
    assert progress[-1] == 100


def test_download_rejects_digest_mismatch_and_removes_staging(tmp_path):
    payload = b"not the expected file"
    info = UpdateInfo(
        "0.2.1",
        "0.3.0",
        "v0.3.0",
        "https://github.com/release",
        "notes",
        ReleaseAsset(
            "agent-switcher-windows-x86_64.exe",
            "https://github.com/work-vahidrafiyi/agent-switcher/releases/download/v0.3.0/agent-switcher-windows-x86_64.exe",
            len(payload),
            "0" * 64,
        ),
    )

    with pytest.raises(UpdateError, match="SHA-256"):
        download_update(
            info,
            transport=lambda _request, timeout: Response(payload),
            destination_root=tmp_path,
        )

    assert list(tmp_path.glob("agent-switcher-update-*")) == []


def test_download_rejects_incomplete_payload_and_removes_staging(tmp_path):
    payload = b"partial executable"
    info = UpdateInfo(
        "0.2.1",
        "0.3.0",
        "v0.3.0",
        "https://github.com/release",
        "notes",
        ReleaseAsset(
            "agent-switcher-windows-x86_64.exe",
            "https://github.com/work-vahidrafiyi/agent-switcher/releases/download/v0.3.0/agent-switcher-windows-x86_64.exe",
            len(payload) + 10,
            hashlib.sha256(payload).hexdigest(),
        ),
    )

    with pytest.raises(UpdateError, match="incomplete"):
        download_update(
            info,
            transport=lambda _request, timeout: Response(payload),
            destination_root=tmp_path,
        )

    assert list(tmp_path.glob("agent-switcher-update-*")) == []


def test_download_rejects_archive_path_traversal(tmp_path):
    archive_path = tmp_path / "unsafe.tar.gz"
    archive_bytes = make_linux_archive(archive_path, "../evil-updater-file")
    info = UpdateInfo(
        "0.2.1",
        "0.3.0",
        "v0.3.0",
        "https://github.com/release",
        "notes",
        ReleaseAsset(
            "agent-switcher-linux-x86_64.tar.gz",
            "https://github.com/work-vahidrafiyi/agent-switcher/releases/download/v0.3.0/agent-switcher-linux-x86_64.tar.gz",
            len(archive_bytes),
            hashlib.sha256(archive_bytes).hexdigest(),
        ),
    )

    with pytest.raises(UpdateError, match="unsafe"):
        download_update(
            info,
            transport=lambda _request, timeout: Response(archive_bytes),
            destination_root=tmp_path,
        )

    assert not (tmp_path.parent / "evil-updater-file").exists()


def test_staged_update_atomically_replaces_target_without_restart(tmp_path):
    target = tmp_path / "agent-switcher"
    target.write_bytes(b"old version")
    target.chmod(0o755)
    work_dir = tmp_path / "download"
    work_dir.mkdir()
    staged = work_dir / "agent-switcher"
    staged.write_bytes(b"new version")
    staged.chmod(0o755)

    apply_staged_update(0, staged, target, work_dir, restart=False)

    assert target.read_bytes() == b"new version"
    assert target.stat().st_mode & 0o100
    assert not work_dir.exists()


def test_staged_update_restarts_replacement_once_with_helper_cleanup(tmp_path):
    target = tmp_path / "agent-switcher"
    target.write_bytes(b"old version")
    work_dir = tmp_path / "download"
    work_dir.mkdir()
    staged = work_dir / "agent-switcher"
    staged.write_bytes(b"new version")
    helper = tmp_path / ".agent-switcher-update-helper"
    launches = []

    apply_staged_update(
        0,
        staged,
        target,
        work_dir,
        helper_executable=helper,
        launcher=lambda arguments, **kwargs: launches.append((arguments, kwargs)),
    )

    assert len(launches) == 1
    assert launches[0][0] == [
        str(target),
        "--cleanup-update-helper",
        str(helper),
    ]


def test_launch_helper_uses_copy_and_explicit_safe_arguments(tmp_path):
    current = tmp_path / "agent-switcher"
    current.write_bytes(b"current executable")
    current.chmod(0o755)
    work_dir = tmp_path / "download"
    work_dir.mkdir()
    staged = work_dir / "agent-switcher"
    staged.write_bytes(b"new executable")
    calls = []

    helper = launch_update_helper(
        PreparedUpdate("0.3.0", staged, work_dir),
        current_executable=current,
        current_pid=12345,
        launcher=lambda arguments, **kwargs: calls.append((arguments, kwargs)),
    )

    assert helper.read_bytes() == b"current executable"
    arguments, kwargs = calls[0]
    assert arguments[1:] == [
        "--apply-update",
        "12345",
        str(staged),
        str(current.resolve()),
        str(work_dir),
    ]
    assert kwargs["close_fds"] is True


def test_cleanup_helper_removes_file_and_strips_internal_arguments(tmp_path):
    helper = tmp_path / ".agent-switcher-update-helper"
    helper.write_bytes(b"old helper")
    arguments = ["agent-switcher", "--cleanup-update-helper", str(helper), "--user-argument"]

    assert run_update_helper(arguments) is None

    assert not helper.exists()
    assert arguments == ["agent-switcher", "--user-argument"]

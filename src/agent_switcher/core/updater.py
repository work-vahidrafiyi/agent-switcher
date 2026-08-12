from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlsplit
from urllib.request import Request

from .activity_log import ActivityLog, NetworkCallFailure, run_network_call
from .proxy import ProxyConfig


REPOSITORY = "work-vahidrafiyi/agent-switcher"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
UPDATE_TIMEOUT_SECONDS = 20.0
MAX_RELEASE_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 250 * 1024 * 1024
DOWNLOAD_CHUNK_SIZE = 256 * 1024
SHA256_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")
VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")

Transport = Callable[..., Any]
ProgressCallback = Optional[Callable[[int], None]]


class UpdateError(Exception):
    pass


class UnsupportedUpdateError(UpdateError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    tag_name: str
    release_url: str
    notes: str
    asset: ReleaseAsset


@dataclass(frozen=True)
class PreparedUpdate:
    version: str
    executable: Path
    work_dir: Path


def check_for_update(
    current_version: str,
    *,
    proxy_config: Optional[ProxyConfig] = None,
    activity_log: Optional[ActivityLog] = None,
    transport: Optional[Transport] = None,
    system_name: Optional[str] = None,
    machine: Optional[str] = None,
) -> Optional[UpdateInfo]:
    request = Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "agent-switcher-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )

    def fetch() -> Optional[UpdateInfo]:
        response = _open(request, proxy_config, transport)
        try:
            _require_success(response, "Update check")
            payload = _read_json_limited(response, MAX_RELEASE_BYTES)
        finally:
            _close(response)
        return _parse_release(
            payload,
            current_version=current_version,
            system_name=system_name,
            machine=machine,
        )

    return run_network_call(
        activity_log,
        LATEST_RELEASE_API,
        "update_check",
        fetch,
        describe=lambda info: {
            "success": True,
            "update_available": info is not None,
            "latest_version": info.latest_version if info else current_version,
        },
    )


def download_update(
    info: UpdateInfo,
    *,
    proxy_config: Optional[ProxyConfig] = None,
    activity_log: Optional[ActivityLog] = None,
    transport: Optional[Transport] = None,
    progress: ProgressCallback = None,
    destination_root: Optional[Path] = None,
) -> PreparedUpdate:
    work_dir = Path(
        tempfile.mkdtemp(
            prefix="agent-switcher-update-",
            dir=str(destination_root) if destination_root is not None else None,
        )
    )
    archive = work_dir / info.asset.name
    request = Request(
        info.asset.url,
        headers={"Accept": "application/octet-stream", "User-Agent": "agent-switcher-updater"},
        method="GET",
    )

    def fetch() -> PreparedUpdate:
        response = _open(request, proxy_config, transport)
        digest = hashlib.sha256()
        written = 0
        try:
            _require_success(response, "Update download")
            with archive.open("wb") as handle:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_ASSET_BYTES:
                        raise UpdateError("The update file is larger than the allowed limit.")
                    handle.write(chunk)
                    digest.update(chunk)
                    if progress:
                        progress(_progress_percent(written, info.asset.size))
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            _close(response)

        if info.asset.size > 0 and written != info.asset.size:
            raise UpdateError(
                f"The update download is incomplete ({written} of {info.asset.size} bytes)."
            )
        actual_digest = digest.hexdigest()
        if actual_digest.lower() != info.asset.sha256.lower():
            raise UpdateError("The downloaded update failed SHA-256 verification.")
        if progress:
            progress(100)
        executable = _prepare_executable(archive, work_dir)
        return PreparedUpdate(info.latest_version, executable, work_dir)

    try:
        return run_network_call(
            activity_log,
            info.asset.url,
            "update_download",
            fetch,
            payload={"version": info.latest_version, "asset": info.asset.name},
        )
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def automatic_install_supported() -> bool:
    return bool(getattr(sys, "frozen", False)) and Path(sys.executable).is_file()


def launch_update_helper(
    prepared: PreparedUpdate,
    *,
    current_executable: Optional[Path] = None,
    current_pid: Optional[int] = None,
    launcher: Callable[..., Any] = subprocess.Popen,
) -> Path:
    if current_executable is None:
        if not automatic_install_supported():
            raise UnsupportedUpdateError(
                "Automatic installation is available only in the standalone app."
            )
        current_executable = Path(sys.executable)
    target = Path(current_executable).resolve()
    if not target.is_file():
        raise UpdateError("The current application executable could not be found.")
    if not os.access(target.parent, os.W_OK):
        raise UpdateError("The application folder is not writable.")
    parent_pid = current_pid if current_pid is not None else os.getpid()
    helper = target.with_name(
        f".{target.stem}-update-helper-{parent_pid}{target.suffix}"
        if target.suffix
        else f".{target.name}-update-helper-{parent_pid}"
    )
    shutil.copy2(target, helper)
    _make_executable(helper)
    arguments = [
        str(helper),
        "--apply-update",
        str(parent_pid),
        str(prepared.executable),
        str(target),
        str(prepared.work_dir),
    ]
    kwargs: dict[str, Any] = {"close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        kwargs["start_new_session"] = True
    try:
        launcher(arguments, **kwargs)
    except Exception:
        try:
            helper.unlink()
        except OSError:
            pass
        raise
    return helper


def apply_staged_update(
    parent_pid: int,
    staged_executable: Path,
    target_executable: Path,
    work_dir: Path,
    *,
    helper_executable: Optional[Path] = None,
    restart: bool = True,
    wait_timeout: float = 60.0,
    launcher: Callable[..., Any] = subprocess.Popen,
) -> None:
    _wait_for_process_exit(parent_pid, timeout=wait_timeout)
    staged = Path(staged_executable)
    target = Path(target_executable)
    if not staged.is_file():
        raise UpdateError("The staged update executable is missing.")
    sibling = target.with_name(f".{target.name}.new")
    shutil.copy2(staged, sibling)
    _make_executable(sibling)
    with sibling.open("rb") as handle:
        os.fsync(handle.fileno())
    _replace_with_retries(sibling, target)
    shutil.rmtree(Path(work_dir), ignore_errors=True)
    if not restart:
        return
    arguments = [str(target)]
    if helper_executable is not None:
        arguments.extend(["--cleanup-update-helper", str(helper_executable)])
    kwargs: dict[str, Any] = {"close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        kwargs["start_new_session"] = True
    launcher(arguments, **kwargs)


def run_update_helper(arguments: list[str]) -> Optional[int]:
    if "--cleanup-update-helper" in arguments:
        index = arguments.index("--cleanup-update-helper")
        if index + 1 < len(arguments):
            _remove_with_retries(Path(arguments[index + 1]))
            del arguments[index : index + 2]
        return None
    if "--apply-update" not in arguments:
        return None
    index = arguments.index("--apply-update")
    values = arguments[index + 1 : index + 5]
    if len(values) != 4:
        return 2
    parent_pid_text, staged_text, target_text, work_dir_text = values
    target = Path(target_text)
    try:
        apply_staged_update(
            int(parent_pid_text),
            Path(staged_text),
            target,
            Path(work_dir_text),
            helper_executable=Path(sys.executable),
        )
        return 0
    except Exception as exc:
        try:
            error_log = target.with_name(f".{target.name}-update-error.log")
            error_log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        except OSError:
            pass
        return 1


def _parse_release(
    payload: Any,
    *,
    current_version: str,
    system_name: Optional[str],
    machine: Optional[str],
) -> Optional[UpdateInfo]:
    if not isinstance(payload, Mapping):
        raise UpdateError("GitHub returned an unexpected release response.")
    tag_name = payload.get("tag_name")
    if not isinstance(tag_name, str):
        raise UpdateError("The latest release has no version tag.")
    latest_version = tag_name.removeprefix("v")
    if not version_is_newer(latest_version, current_version):
        return None
    expected_name = asset_name_for_platform(system_name=system_name, machine=machine)
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("The latest release has no downloadable assets.")
    raw_asset = next(
        (asset for asset in assets if isinstance(asset, Mapping) and asset.get("name") == expected_name),
        None,
    )
    if raw_asset is None:
        raise UpdateError(f"The latest release has no {expected_name} asset.")
    url = raw_asset.get("browser_download_url")
    digest = raw_asset.get("digest")
    size = raw_asset.get("size")
    if not isinstance(url, str) or not _trusted_download_url(url):
        raise UpdateError("The update asset has an invalid download URL.")
    digest_match = SHA256_RE.match(digest) if isinstance(digest, str) else None
    if digest_match is None:
        raise UpdateError("The update asset does not include a SHA-256 digest.")
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_ASSET_BYTES:
        raise UpdateError("The update asset has an invalid file size.")
    release_url = payload.get("html_url")
    notes = payload.get("body")
    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        tag_name=tag_name,
        release_url=release_url if isinstance(release_url, str) else "",
        notes=notes if isinstance(notes, str) else "",
        asset=ReleaseAsset(expected_name, url, size, digest_match.group(1).lower()),
    )


def version_is_newer(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


def _version_key(value: str) -> tuple[tuple[int, ...], int, tuple[tuple[int, Any], ...]]:
    match = VERSION_RE.match(value.strip())
    if match is None:
        raise UpdateError(f"Cannot compare application version: {value}")
    numbers = tuple(int(part) for part in match.group(1).split("."))
    numbers = numbers + (0,) * (4 - len(numbers))
    prerelease = match.group(2)
    if prerelease is None:
        return numbers, 1, ()
    tokens = []
    for token in prerelease.split("."):
        tokens.append((0, int(token)) if token.isdigit() else (1, token.lower()))
    return numbers, 0, tuple(tokens)


def asset_name_for_platform(
    *,
    system_name: Optional[str] = None,
    machine: Optional[str] = None,
) -> str:
    system_value = (system_name or platform.system()).lower()
    machine_value = (machine or platform.machine()).lower()
    if machine_value not in {"x86_64", "amd64"}:
        raise UnsupportedUpdateError(f"Automatic updates are not available for {machine_value}.")
    if system_value == "linux":
        return "agent-switcher-linux-x86_64.tar.gz"
    if system_value == "windows":
        return "agent-switcher-windows-x86_64.exe"
    raise UnsupportedUpdateError(f"Automatic updates are not available on {system_value}.")


def _prepare_executable(archive: Path, work_dir: Path) -> Path:
    if archive.name.endswith(".exe"):
        return archive
    if not archive.name.endswith(".tar.gz"):
        raise UpdateError("The downloaded update has an unsupported format.")
    output = work_dir / "agent-switcher"
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            members = [member for member in bundle.getmembers() if member.name not in {"", "."}]
            if len(members) != 1:
                raise UpdateError("The Linux update archive has unexpected contents.")
            member = members[0]
            normalized = member.name.removeprefix("./")
            if normalized != "agent-switcher" or not member.isfile() or member.size > MAX_ASSET_BYTES:
                raise UpdateError("The Linux update archive is unsafe.")
            source = bundle.extractfile(member)
            if source is None:
                raise UpdateError("The Linux update executable could not be extracted.")
            with source, output.open("wb") as handle:
                shutil.copyfileobj(source, handle, DOWNLOAD_CHUNK_SIZE)
                handle.flush()
                os.fsync(handle.fileno())
    except (tarfile.TarError, OSError) as exc:
        raise UpdateError(f"The Linux update archive could not be opened: {exc}") from exc
    _make_executable(output)
    return output


def _open(request: Request, proxy_config: Optional[ProxyConfig], transport: Optional[Transport]):
    opener = transport or (proxy_config or ProxyConfig()).open
    return opener(request, timeout=UPDATE_TIMEOUT_SECONDS)


def _read_json_limited(response: Any, limit: int) -> Any:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise UpdateError("The release response is larger than expected.")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UpdateError("GitHub returned invalid release data.") from exc


def _require_success(response: Any, purpose: str) -> None:
    status = getattr(response, "status", None)
    if status is None:
        status = response.getcode()
    if not isinstance(status, int) or not 200 <= status < 300:
        raise NetworkCallFailure(f"{purpose} returned HTTP {status}.")


def _close(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _trusted_download_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname == "github.com"


def _progress_percent(written: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(99, int(written * 100 / total)))


def _make_executable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as exc:
        raise UpdateError(f"The update executable could not be made runnable: {exc}") from exc


def _wait_for_process_exit(pid: int, *, timeout: float) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return
        time.sleep(0.1)
    raise UpdateError("The running application did not close in time.")


def _replace_with_retries(source: Path, target: Path) -> None:
    last_error: Optional[OSError] = None
    for _attempt in range(50):
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.1)
    raise UpdateError(f"The current application could not be replaced: {last_error}")


def _remove_with_retries(path: Path) -> None:
    for _attempt in range(50):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.1)

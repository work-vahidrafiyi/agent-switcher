from pathlib import Path
import tomllib


def test_pyproject_is_the_version_source_of_truth():
    with Path("pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    package_init = Path("src/agent_switcher/__init__.py").read_text(encoding="utf-8")

    assert project_version == "1.5.1"
    assert 'version("agent-switcher")' in package_init
    assert f'__version__ = "{project_version}"' not in package_init


def test_release_workflow_builds_both_platforms_and_publishes_assets():
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'tags:\n      - "v*"' in workflow
    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert "packaging/agent-switcher.spec" in workflow
    assert "Install UPX on Windows" in workflow
    assert "maximum_bytes=$((41 * 1024 * 1024))" in workflow
    assert "agent-switcher-linux-x86_64.tar.gz" in workflow
    assert "agent-switcher-windows-x86_64.exe" in workflow
    assert "GH_REPO: ${{ github.repository }}" in workflow
    assert "release-notes.md" in workflow
    assert "--notes-file release-notes.md" in workflow
    assert "--generate-notes" not in workflow
    assert "gh release" in workflow


def test_standalone_spec_keeps_only_the_required_qt_and_icon_runtime():
    spec = Path("packaging/agent-switcher.spec").read_text(encoding="utf-8")
    runtime_hook = Path("packaging/pyi_rth_qtawesome_slim.py").read_text(encoding="utf-8")

    assert '"PySide6.QtPdf"' in spec
    assert '"PySide6.QtQml"' in spec
    assert '"PySide6.QtQuick"' in spec
    assert '"PySide6.QtNetwork"' in spec
    assert "exclude_system_libraries" in spec
    assert "fontawesome5-solid-webfont-5.15.4.ttf" in spec
    assert "/pyside6/qt/translations/" in spec
    assert 'font[0] == "fa5s"' in runtime_hook


def test_runtime_uses_pyside_essentials_to_avoid_shipping_unused_addons():
    with Path("pyproject.toml").open("rb") as handle:
        dependencies = tomllib.load(handle)["project"]["dependencies"]

    assert any(value.startswith("PySide6-Essentials") for value in dependencies)
    assert not any(value.startswith("PySide6>") for value in dependencies)


def test_standalone_entrypoint_handles_update_helper_before_starting_qt():
    entrypoint = Path("packaging/pyinstaller_entry.py").read_text(encoding="utf-8")

    assert "run_update_helper(sys.argv)" in entrypoint
    assert entrypoint.index("run_update_helper(sys.argv)") < entrypoint.index(
        "from agent_switcher.gui.app import main"
    )


def test_readme_documents_unsigned_windows_smartscreen_path():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "unsigned" in readme
    assert "More info" in readme
    assert "Run anyway" in readme


def test_release_docs_state_current_provider_and_include_screenshots():
    readme = Path("README.md").read_text(encoding="utf-8")
    persian_readme = Path("README.fa.md").read_text(encoding="utf-8")

    assert "currently works with **OpenAI Codex only**" in readme
    assert "فقط برای **OpenAI Codex** فعال است" in persian_readme
    assert Path("docs/screenshot-main.png").is_file()
    assert Path("docs/screenshot-usage.png").is_file()

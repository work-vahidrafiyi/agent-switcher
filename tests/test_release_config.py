from pathlib import Path
import tomllib


def test_pyproject_is_the_version_source_of_truth():
    with Path("pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    package_init = Path("src/agent_switcher/__init__.py").read_text(encoding="utf-8")

    assert project_version == "0.2.1"
    assert 'version("agent-switcher")' in package_init
    assert f'__version__ = "{project_version}"' not in package_init


def test_release_workflow_builds_both_platforms_and_publishes_assets():
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'tags:\n      - "v*"' in workflow
    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert "--onefile" in workflow
    assert "--collect-all qtawesome" in workflow
    assert "--collect-all qdarktheme" in workflow
    assert "--collect-all pynput" in workflow
    assert "--copy-metadata agent-switcher" in workflow
    assert "agent-switcher-linux-x86_64.tar.gz" in workflow
    assert "agent-switcher-windows-x86_64.exe" in workflow
    assert "GH_REPO: ${{ github.repository }}" in workflow
    assert "release-notes.md" in workflow
    assert "--notes-file release-notes.md" in workflow
    assert "--generate-notes" not in workflow
    assert "gh release" in workflow


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

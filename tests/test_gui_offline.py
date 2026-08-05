import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from agent_switcher.core.activity_log import ActivityLog
from agent_switcher.core.providers.codex import CodexProvider
from agent_switcher.core.store import Store
from agent_switcher.gui.dialogs import AboutDialog, HistoryDialog, SettingsDialog, TransparencyDialog
from agent_switcher import __version__
from agent_switcher.gui.main_window import MainWindow
from agent_switcher.gui.platform import PlatformIntegration
from agent_switcher.gui.settings import GuiSettings, SettingsStore
from agent_switcher.gui.hotkey import GlobalHotkeyController
from agent_switcher.gui.theme import apply_theme


def application():
    return QApplication.instance() or QApplication(["agent-switcher-tests"])


def test_settings_store_persists_offline_mode(tmp_path):
    settings_store = SettingsStore(tmp_path / "settings.json")
    settings_store.save(
        GuiSettings(
            offline_mode=True,
            low_quota_threshold_pct=12,
            theme="light",
            onboarding_seen=True,
            language="fa",
            proxy_mode="custom",
            proxy_url="http://proxy.test:8080",
        )
    )

    assert settings_store.load().offline_mode is True
    assert settings_store.load().low_quota_threshold_pct == 12
    assert settings_store.load().theme == "light"
    assert settings_store.load().onboarding_seen is True
    assert settings_store.load().language == "fa"
    assert settings_store.load().proxy_mode == "custom"
    assert settings_store.load().proxy_url == "http://proxy.test:8080"


def test_proxy_controls_validate_custom_mode_and_disable_url_for_no_proxy():
    app = application()
    dialog = SettingsDialog(
        False,
        15,
        10,
        20,
        False,
        "<ctrl>+<alt>+<space>",
        "system",
        "en",
        "none",
        "http://saved-proxy.test:8080",
    )

    assert dialog.proxy_url_edit.isEnabled() is False
    dialog.proxy_mode_combo.setCurrentIndex(dialog.proxy_mode_combo.findData("custom"))
    assert dialog.proxy_url_edit.isEnabled() is True
    assert dialog.proxy_config().url == "http://saved-proxy.test:8080"

    dialog.proxy_url_edit.setText("socks5://proxy.test:1080")
    dialog.accept()
    assert dialog.result() == 0
    assert "http://" in dialog.proxy_error.text()
    dialog.close()


def test_main_window_applies_saved_proxy_to_core_store(tmp_path):
    app = application()
    provider = CodexProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    window = MainWindow(
        store,
        PlatformIntegration(app),
        settings=GuiSettings(
            offline_mode=True,
            global_hotkey_enabled=False,
            onboarding_seen=True,
            proxy_mode="custom",
            proxy_url="http://proxy.test:8080",
        ),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )

    assert store.proxy_config.mode == "custom"
    assert store.proxy_config.url == "http://proxy.test:8080"
    window.close()


def test_offline_mode_blocks_all_and_per_profile_refresh(tmp_path):
    app = application()
    calls = []

    class CountingProvider(CodexProvider):
        def fetch_usage(self, profile, activity_log=None):
            calls.append(profile.name)
            return super().fetch_usage(profile, activity_log=activity_log)

    provider = CountingProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    log = ActivityLog(tmp_path / "state" / "activity.jsonl")
    store = Store(provider, activity_log=log)
    platform = PlatformIntegration(app)
    platform.configure_application()
    window = MainWindow(
        store,
        platform,
        settings=GuiSettings(offline_mode=True),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )

    window.refresh_all_usage()
    window.refresh_profile_usage("work")

    assert calls == []
    assert window.usage_worker is None
    assert window.refresh_button.isEnabled() is False
    assert window.rows["work"].refresh_button.isEnabled() is False
    window.close()


def test_transparency_dialog_reads_network_events(tmp_path):
    app = application()
    log = ActivityLog(tmp_path / "activity.jsonl")
    log.append(
        "network_call",
        {"endpoint": "https://example.test", "purpose": "usage_check", "success": False, "error": "timeout"},
    )

    dialog = TransparencyDialog(log)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "usage_check"
    assert dialog.table.item(0, 2).text() == "https://example.test"
    assert dialog.table.item(0, 3).text() == "Failed: timeout"
    dialog.close()


def test_history_dialog_reads_recent_switches_newest_first(tmp_path):
    app = application()
    log = ActivityLog(tmp_path / "activity.jsonl")
    log.append("switch", {"from": "work", "to": "personal"})

    dialog = HistoryDialog(log)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "work"
    assert dialog.table.item(0, 2).text() == "personal"
    dialog.close()


def test_about_dialog_uses_package_version():
    app = application()
    dialog = AboutDialog()

    assert __version__ in dialog.version_label.text()
    dialog.close()


def test_global_hotkey_registration_failure_is_logged_and_nonfatal(tmp_path):
    app = application()
    log = ActivityLog(tmp_path / "activity.jsonl")

    def failing_factory(_mapping):
        raise RuntimeError("Wayland registration unavailable")

    controller = GlobalHotkeyController(log, lambda: None, "<ctrl>+<alt>+<space>", failing_factory)

    assert controller.start() is False
    event = [line for line in log.path.read_text(encoding="utf-8").splitlines()][-1]
    assert '"event_type":"hotkey"' in event
    assert '"success":false' in event


def test_onboarding_can_be_replayed_after_first_run(tmp_path):
    app = application()
    provider = CodexProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    window = MainWindow(
        store,
        PlatformIntegration(app),
        settings=GuiSettings(offline_mode=True, global_hotkey_enabled=False, onboarding_seen=True),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )
    app.processEvents()

    assert window.onboarding_dialog is None
    window.help_button.click()
    app.processEvents()
    assert window.onboarding_dialog is not None
    assert window.onboarding_dialog.isVisible()

    window.onboarding_dialog.close()
    window.close()


def test_existing_icons_recolor_when_theme_changes(tmp_path):
    app = application()
    apply_theme(app, "light")
    provider = CodexProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    window = MainWindow(
        store,
        PlatformIntegration(app),
        settings=GuiSettings(offline_mode=True, global_hotkey_enabled=False, onboarding_seen=True),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )
    light_key = window.help_button.icon().cacheKey()

    apply_theme(app, "dark")

    assert window.help_button.icon().cacheKey() != light_key
    window.close()
    apply_theme(app, "system")

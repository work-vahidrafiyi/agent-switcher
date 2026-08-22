import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QFrame, QMessageBox
from PySide6.QtTest import QTest

from agent_switcher.core.activity_log import ActivityLog
from agent_switcher.core.providers.codex import CodexProvider
from agent_switcher.core.store import Store
from agent_switcher.core.usage import Usage
from agent_switcher.core.updater import ReleaseAsset, UpdateInfo
from agent_switcher.core.egress_guard import EgressCheck
from agent_switcher.gui.dialogs import AboutDialog, HistoryDialog, SettingsDialog, TransparencyDialog
from agent_switcher import __version__
from agent_switcher.gui.main_window import MainWindow
from agent_switcher.gui.platform import PlatformIntegration
from agent_switcher.gui.settings import GuiSettings, SettingsStore
from agent_switcher.gui.hotkey import GlobalHotkeyController
from agent_switcher.gui.message_box import MessageDialog
from agent_switcher.gui.privacy_notice import PrivacyNoticeDialog
from agent_switcher.gui.update_dialog import UpdateAvailableDialog, UpdateProgressDialog
from agent_switcher.gui.theme import apply_theme
from agent_switcher.gui.workers import UsageRefreshWorker
from agent_switcher.gui.egress_prompt import confirm_egress
from agent_switcher.gui.i18n import set_language


def application():
    return QApplication.instance() or QApplication(["agent-switcher-tests"])


def test_settings_store_persists_offline_mode(tmp_path):
    settings_store = SettingsStore(tmp_path / "settings.json")
    settings_store.save(
        GuiSettings(
            offline_mode=True,
            ip_guard_enabled=False,
            low_quota_threshold_pct=12,
            theme="light",
            onboarding_seen=True,
            privacy_notice_suppressed=True,
            language="fa",
            proxy_mode="custom",
            proxy_url="http://proxy.test:8080",
        )
    )

    assert settings_store.load().offline_mode is True
    assert settings_store.load().ip_guard_enabled is False
    assert settings_store.load().low_quota_threshold_pct == 12
    assert settings_store.load().theme == "light"
    assert settings_store.load().onboarding_seen is True
    assert settings_store.load().privacy_notice_suppressed is True
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
        True,
    )

    assert dialog.proxy_url_edit.isEnabled() is False
    assert dialog.ip_guard_checkbox.isChecked() is True
    dialog.proxy_mode_combo.setCurrentIndex(dialog.proxy_mode_combo.findData("custom"))
    assert dialog.proxy_url_edit.isEnabled() is True
    assert dialog.proxy_config().url == "http://saved-proxy.test:8080"
    assert len(dialog.findChildren(QFrame, "settingsSection")) == 4

    dialog.proxy_url_edit.setText("socks5://proxy.test:1080")
    dialog.accept()
    assert dialog.result() == 0
    assert "http://" in dialog.proxy_error.text()
    dialog.close()


def test_privacy_notice_repeats_until_user_explicitly_suppresses_it():
    app = application()
    dialog = PrivacyNoticeDialog()

    assert dialog.dont_show_again.isChecked() is False
    assert "private" in dialog.windowTitle().lower()
    assert dialog.isModal() is True
    dialog.close()


def test_accepting_first_run_privacy_notice_persists_choice(tmp_path, monkeypatch):
    app = application()
    provider = CodexProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    settings_store = SettingsStore(tmp_path / "state" / "settings.json")

    class Checked:
        @staticmethod
        def isChecked():
            return True

    class AcceptedPrivacyNotice:
        dont_show_again = Checked()

        def __init__(self, _parent):
            pass

        @staticmethod
        def exec():
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "agent_switcher.gui.main_window.PrivacyNoticeDialog",
        AcceptedPrivacyNotice,
    )
    window = MainWindow(
        Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl")),
        PlatformIntegration(app),
        settings=GuiSettings(
            offline_mode=True,
            global_hotkey_enabled=False,
            onboarding_seen=True,
        ),
        settings_store=settings_store,
    )

    window.maybe_show_startup_notices()

    assert window.settings.privacy_notice_suppressed is True
    assert settings_store.load().privacy_notice_suppressed is True
    app.processEvents()
    window.close()


def test_accepting_privacy_notice_without_checkbox_shows_it_next_time(tmp_path, monkeypatch):
    app = application()
    provider = CodexProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    settings_store = SettingsStore(tmp_path / "state" / "settings.json")

    class Unchecked:
        @staticmethod
        def isChecked():
            return False

    class AcceptedPrivacyNotice:
        dont_show_again = Unchecked()

        def __init__(self, _parent):
            pass

        @staticmethod
        def exec():
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "agent_switcher.gui.main_window.PrivacyNoticeDialog",
        AcceptedPrivacyNotice,
    )
    window = MainWindow(
        Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl")),
        PlatformIntegration(app),
        settings=GuiSettings(
            offline_mode=True,
            global_hotkey_enabled=False,
            onboarding_seen=True,
        ),
        settings_store=settings_store,
    )

    window.maybe_show_startup_notices()

    assert window.settings.privacy_notice_suppressed is False
    assert settings_store.load().privacy_notice_suppressed is False
    app.processEvents()
    window.close()


def test_update_dialog_supports_install_action_and_progress():
    app = application()
    info = UpdateInfo(
        "0.2.1",
        "0.3.0",
        "v0.3.0",
        "https://github.com/work-vahidrafiyi/agent-switcher/releases/tag/v0.3.0",
        "### Fixed\n\n- Update flow",
        ReleaseAsset(
            "agent-switcher-linux-x86_64.tar.gz",
            "https://github.com/download",
            123,
            "0" * 64,
        ),
    )
    dialog = UpdateAvailableDialog(info, True)
    progress = UpdateProgressDialog(info.latest_version)

    dialog._finish("install")
    progress.set_progress(42)

    assert dialog.action == "install"
    assert progress.progress.value() == 42
    assert "42" in progress.status_label.text()
    dialog.close()
    progress.close()


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
            privacy_notice_suppressed=True,
            proxy_mode="custom",
            proxy_url="http://proxy.test:8080",
        ),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )

    assert store.proxy_config.mode == "custom"
    assert store.proxy_config.url == "http://proxy.test:8080"
    assert store.egress_guard.enabled is True
    window.close()


def test_usage_worker_blocks_changed_ip_before_provider_request(tmp_path):
    calls = []

    class CountingProvider(CodexProvider):
        def fetch_usage(self, profile, activity_log=None, proxy_config=None):
            calls.append(profile.name)
            raise AssertionError("OpenAI usage request must stay blocked")

    provider = CountingProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    changed = EgressCheck(
        "work",
        "usage_check",
        "changed",
        previous_fingerprint="a" * 64,
        current_fingerprint="b" * 64,
    )
    store.check_egress = lambda _profile, _purpose: changed
    worker = UsageRefreshWorker(store, [store.profile("work")], 0)
    results = []
    worker.egress_attention.connect(lambda _result: worker.resolve_egress(False))
    worker.usage_ready.connect(lambda name, usage: results.append((name, usage)))
    worker.run()

    assert calls == []
    assert results[0][0] == "work"
    assert results[0][1].available is False
    assert "IP" in results[0][1].unavailable_reason


def test_usage_worker_continues_when_public_ip_service_is_unavailable(tmp_path):
    calls = []

    class CountingProvider(CodexProvider):
        def fetch_usage(self, profile, activity_log=None, proxy_config=None):
            calls.append(profile.name)
            return Usage.unavailable("fixture")

    provider = CountingProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    store.check_egress = lambda profile, purpose: EgressCheck(
        profile,
        purpose,
        "unavailable",
        error="public IP service is blocked",
    )
    worker = UsageRefreshWorker(store, [store.profile("work")], 0)
    attention = []
    worker.egress_attention.connect(attention.append)

    worker.run()

    assert calls == ["work"]
    assert attention == []


def test_changed_ip_warning_explains_openai_block_risk_and_is_remembered(monkeypatch):
    set_language("en")
    changed = EgressCheck(
        "work",
        "usage_check",
        "changed",
        previous_fingerprint="a" * 64,
        current_fingerprint="b" * 64,
    )
    captured = {}

    def capture_message(_parent, _icon, title, text, _buttons, _default, labels):
        captured.update(title=title, text=text, labels=labels)
        return QMessageBox.StandardButton.Ok

    approved = []

    class GuardStore:
        def approve_egress(self, result):
            approved.append(result)

    monkeypatch.setattr("agent_switcher.gui.egress_prompt.show_message", capture_message)

    assert confirm_egress(GuardStore(), changed, None) is True
    assert "OpenAI may block your account" in captured["text"]
    assert "will not be shown again" in captured["text"]
    assert captured["labels"][QMessageBox.StandardButton.Ok] == "Continue and remember"
    assert approved == [changed]


def test_switch_warning_hides_process_ids_and_paths(tmp_path, monkeypatch):
    app = application()

    class RunningProvider(CodexProvider):
        def running_processes(self):
            return ["650437 /private/node/path/codex app-server --dangerous-detail"]

    provider = RunningProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    (provider.home() / "auth.personal.json").write_text("{}", encoding="utf-8")
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    store.set_active("work")
    captured = {}

    def capture_message(_parent, _icon, _title, text, _buttons, _default, labels):
        captured["text"] = text
        captured["labels"] = labels
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr("agent_switcher.gui.main_window.show_message", capture_message)
    window = MainWindow(
        store,
        PlatformIntegration(app),
        settings=GuiSettings(
            offline_mode=True,
            global_hotkey_enabled=False,
            onboarding_seen=True,
            privacy_notice_suppressed=True,
        ),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )

    window.switch_profile("personal")

    assert "650437" not in captured["text"]
    assert "/private/node/path" not in captured["text"]
    assert captured["labels"][QMessageBox.StandardButton.Ok] == "Switch anyway"
    assert store.active() == "work"
    window.close()


def test_switch_waits_for_ip_guard_and_stays_local_when_user_cancels(tmp_path, monkeypatch):
    app = application()

    class IdleProvider(CodexProvider):
        def running_processes(self):
            return []

    provider = IdleProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    (provider.home() / "auth.personal.json").write_text("{}", encoding="utf-8")
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    store.set_active("work")
    changed = EgressCheck(
        "personal",
        "account_switch",
        "changed",
        previous_fingerprint="a" * 64,
        current_fingerprint="b" * 64,
    )
    store.check_egress = lambda _profile, _purpose: changed
    monkeypatch.setattr("agent_switcher.gui.main_window.confirm_egress", lambda *_args: False)
    window = MainWindow(
        store,
        PlatformIntegration(app),
        settings=GuiSettings(
            offline_mode=True,
            global_hotkey_enabled=False,
            onboarding_seen=True,
            privacy_notice_suppressed=True,
        ),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )

    window.switch_profile("personal")
    assert window.switch_egress_worker.wait(1000)
    app.processEvents()

    assert store.active() == "work"
    assert window.pending_switch is None
    window.close()


def test_opening_main_window_does_not_fetch_usage(tmp_path):
    app = application()
    calls = []

    class CountingProvider(CodexProvider):
        def fetch_usage(self, profile, activity_log=None, proxy_config=None):
            calls.append(profile.name)
            return super().fetch_usage(
                profile,
                activity_log=activity_log,
                proxy_config=proxy_config,
            )

    provider = CountingProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    window = MainWindow(
        store,
        PlatformIntegration(app),
        settings=GuiSettings(global_hotkey_enabled=False, onboarding_seen=True, privacy_notice_suppressed=True),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )

    QTest.qWait(500)

    assert calls == []
    assert window.usage_worker is None
    assert window.update_button.text() == "Check updates"
    assert window.minimumSize() == window.maximumSize()
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
        settings=GuiSettings(offline_mode=True, privacy_notice_suppressed=True),
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


def test_global_hotkey_waits_for_backend_registration(tmp_path):
    app = application()
    log = ActivityLog(tmp_path / "activity.jsonl")
    calls = []

    class Listener:
        def start(self):
            calls.append("start")

        def wait(self):
            calls.append("wait")

        def stop(self):
            calls.append("stop")

    controller = GlobalHotkeyController(log, lambda: None, "<ctrl>+<alt>+<space>", lambda _mapping: Listener())

    assert controller.start() is True
    assert calls == ["start", "wait"]
    controller.stop()


def test_themed_message_dialog_uses_safe_cancel_when_closed():
    app = application()
    dialog = MessageDialog(
        None,
        QMessageBox.Icon.Warning,
        "Switch account",
        "Continue?",
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )

    assert dialog.selected == QMessageBox.StandardButton.Cancel
    assert dialog.minimumWidth() == 440
    dialog.close()


def test_onboarding_can_be_replayed_after_first_run(tmp_path):
    app = application()
    provider = CodexProvider(home=tmp_path / ".codex")
    provider.home().mkdir(parents=True)
    (provider.home() / "auth.work.json").write_text("{}", encoding="utf-8")
    store = Store(provider, activity_log=ActivityLog(tmp_path / "state" / "activity.jsonl"))
    window = MainWindow(
        store,
        PlatformIntegration(app),
        settings=GuiSettings(
            offline_mode=True,
            global_hotkey_enabled=False,
            onboarding_seen=True,
            privacy_notice_suppressed=True,
        ),
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
        settings=GuiSettings(
            offline_mode=True,
            global_hotkey_enabled=False,
            onboarding_seen=True,
            privacy_notice_suppressed=True,
        ),
        settings_store=SettingsStore(tmp_path / "state" / "settings.json"),
    )
    light_key = window.help_button.icon().cacheKey()

    apply_theme(app, "dark")

    assert window.help_button.icon().cacheKey() != light_key
    window.close()
    apply_theme(app, "system")

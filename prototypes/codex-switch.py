#!/usr/bin/env python3
"""
Codex Switch — manage multiple Codex (ChatGPT) accounts and switch between them.

Never calls `codex logout` (that revokes the refresh token server-side).
Instead it saves the live auth.json into the active profile, then swaps files.

Profiles live next to auth.json:
    $CODEX_HOME/auth.<name>.json      (default $CODEX_HOME = ~/.codex)
    $CODEX_HOME/.active               plain text, name of the current profile

Compatible with the shell function of the same name.
"""

import base64
import json
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Gdk, Gio  # noqa: E402

Indicator = None
for _mod, _ver in (("AyatanaAppIndicator3", "0.1"), ("AppIndicator3", "0.1")):
    try:
        gi.require_version(_mod, _ver)
        Indicator = getattr(__import__("gi.repository", fromlist=[_mod]), _mod)
        break
    except (ValueError, ImportError, AttributeError):
        continue

APP_ID = "dev.local.codex-switch"
ICON_NAME = "system-switch-user"

CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
AUTH_FILE = CODEX_HOME / "auth.json"
ACTIVE_FILE = CODEX_HOME / ".active"

PROFILE_RE = re.compile(r"^auth\.(?P<name>[^.].*)\.json$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\r")
URL_RE = re.compile(r"https?://[^\s'\"<>\)\]]+")
CODE_DASHED_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4,6})\b")
CODE_PLAIN_RE = re.compile(r"\b([A-Z0-9]{6,10})\b")

CSS = b"""
.cs-code {
    font-family: monospace;
    font-size: 30pt;
    font-weight: bold;
    letter-spacing: 3px;
    padding: 12px 18px;
}
.cs-name { font-weight: bold; font-size: 12pt; }
.cs-meta { font-size: 9pt; opacity: 0.65; }
.cs-pill {
    font-size: 8pt;
    font-weight: bold;
    padding: 2px 8px;
    border-radius: 9px;
    background-color: alpha(@theme_selected_bg_color, 0.20);
    color: @theme_selected_bg_color;
}
.cs-log {
    font-family: monospace;
    font-size: 9pt;
}
"""


# ---------------------------------------------------------------- data layer


def decode_jwt(token):
    """Return the payload dict of a JWT, or {} if it can't be read."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def describe(path):
    """Pull a human label (email / plan / age) out of an auth file."""
    out = {"email": None, "plan": None, "refreshed": None}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return out

    tokens = data.get("tokens") or {}
    claims = decode_jwt(tokens.get("id_token", ""))

    out["email"] = claims.get("email")
    if not out["email"]:
        for value in claims.values():
            if isinstance(value, dict) and value.get("email"):
                out["email"] = value["email"]
                break

    for value in claims.values():
        if isinstance(value, dict):
            plan = value.get("chatgpt_plan_type") or value.get("plan_type")
            if plan:
                out["plan"] = plan
                break

    stamp = data.get("last_refresh")
    if stamp:
        out["refreshed"] = stamp[:19].replace("T", " ")
    return out


class Store:
    """All reads and writes against $CODEX_HOME."""

    @staticmethod
    def profile_path(name):
        return CODEX_HOME / f"auth.{name}.json"

    @staticmethod
    def profiles():
        if not CODEX_HOME.is_dir():
            return []
        names = []
        for entry in CODEX_HOME.iterdir():
            match = PROFILE_RE.match(entry.name)
            if match and entry.is_file():
                names.append(match.group("name"))
        return sorted(names)

    @staticmethod
    def active():
        try:
            name = ACTIVE_FILE.read_text().strip()
        except OSError:
            return None
        return name or None

    @staticmethod
    def set_active(name):
        CODEX_HOME.mkdir(parents=True, exist_ok=True)
        if name is None:
            ACTIVE_FILE.unlink(missing_ok=True)
        else:
            ACTIVE_FILE.write_text(name + "\n")

    @classmethod
    def sync_live(cls):
        """Copy the live auth.json back into whichever profile is active.

        This is the step that keeps rotated refresh tokens from going stale.
        """
        current = cls.active()
        if current and AUTH_FILE.is_file():
            shutil.copy2(AUTH_FILE, cls.profile_path(current))
            return current
        return None

    @classmethod
    def switch(cls, name):
        target = cls.profile_path(name)
        if not target.is_file():
            raise FileNotFoundError(f"{name} has no saved credentials")
        previous = cls.sync_live()
        shutil.copy2(target, AUTH_FILE)
        cls.set_active(name)
        return previous

    @classmethod
    def rename(cls, old, new):
        cls.profile_path(old).rename(cls.profile_path(new))
        if cls.active() == old:
            cls.set_active(new)

    @classmethod
    def delete(cls, name):
        cls.profile_path(name).unlink(missing_ok=True)
        if cls.active() == name:
            cls.set_active(None)
            AUTH_FILE.unlink(missing_ok=True)


def codex_running():
    """Names of running codex processes, so we don't swap files mid-flight."""
    try:
        result = subprocess.run(
            ["pgrep", "-a", "-f", r"(^|/)codex($| )"],
            capture_output=True, text=True, timeout=3,
        )
    except Exception:
        return []
    lines = [l for l in result.stdout.splitlines() if "codex-switch" not in l]
    return lines


# ------------------------------------------------------------ device login


class DeviceLogin:
    """Runs `codex login --device-auth` on a pty and reports what it prints."""

    def __init__(self, on_url, on_code, on_line, on_done):
        self.on_url = on_url
        self.on_code = on_code
        self.on_line = on_line
        self.on_done = on_done
        self.proc = None
        self._stop = threading.Event()
        self._saw_url = False
        self._saw_code = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def _emit(self, callback, *args):
        GLib.idle_add(callback, *args)

    def _scan(self, line):
        if not self._saw_url:
            urls = URL_RE.findall(line)
            preferred = [u for u in urls if re.search(r"device|activate|auth", u)]
            if preferred or urls:
                self._saw_url = True
                self._emit(self.on_url, (preferred or urls)[0].rstrip(".,"))

        if not self._saw_code:
            match = CODE_DASHED_RE.search(line)
            if not match and re.search(r"code", line, re.I):
                for candidate in CODE_PLAIN_RE.finditer(line):
                    if not candidate.group(1).isdigit() or len(candidate.group(1)) >= 6:
                        match = candidate
                        break
            if match:
                self._saw_code = True
                self._emit(self.on_code, match.group(1))

    def _run(self):
        if not shutil.which("codex"):
            self._emit(self.on_line, "codex not found in PATH")
            self._emit(self.on_done, False, "codex CLI is not installed")
            return

        master, slave = pty.openpty()
        try:
            self.proc = subprocess.Popen(
                ["codex", "login", "--device-auth"],
                stdin=slave, stdout=slave, stderr=slave,
                close_fds=True, start_new_session=True,
            )
        except Exception as exc:
            os.close(master)
            os.close(slave)
            self._emit(self.on_done, False, str(exc))
            return

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
                    buffer += ANSI_RE.sub("\n", chunk.decode("utf-8", "replace"))
                    *lines, buffer = buffer.split("\n")
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        self._emit(self.on_line, line)
                        self._scan(line)
                elif self.proc.poll() is not None:
                    break
        finally:
            try:
                os.close(master)
            except OSError:
                pass

        if buffer.strip():
            self._emit(self.on_line, buffer.strip())
            self._scan(buffer.strip())

        code = self.proc.wait() if self.proc else 1
        if self._stop.is_set():
            self._emit(self.on_done, False, "Cancelled")
        elif code == 0 and AUTH_FILE.is_file():
            self._emit(self.on_done, True, None)
        else:
            self._emit(self.on_done, False, f"codex login exited with {code}")


# --------------------------------------------------------------- login view


class AddAccountDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="Add account", transient_for=parent, modal=True)
        self.set_default_size(480, -1)
        self.login = None
        self.saved_previous = None
        self.result_name = None

        box = self.get_content_area()
        box.set_spacing(12)
        box.set_border_width(16)

        intro = Gtk.Label(
            label="Give the account a name, then sign in through your browser.",
            xalign=0, wrap=True,
        )
        box.add(intro)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_row.pack_start(Gtk.Label(label="Name", xalign=0), False, False, 0)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("work")
        self.name_entry.set_activates_default(True)
        existing = Store.profiles()
        index = 1
        while f"account{index}" in existing:
            index += 1
        self.name_entry.set_text(f"account{index}")
        name_row.pack_start(self.name_entry, True, True, 0)
        box.add(name_row)

        self.start_button = Gtk.Button(label="Start sign-in")
        self.start_button.get_style_context().add_class("suggested-action")
        self.start_button.connect("clicked", self.on_start)
        box.add(self.start_button)

        self.steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.steps.set_no_show_all(True)
        box.add(self.steps)

        self.status = Gtk.Label(label="", xalign=0, wrap=True)
        self.status.get_style_context().add_class("cs-meta")
        box.add(self.status)

        self._build_steps()

        self.log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self.log_buffer, editable=False, monospace=True)
        log_view.get_style_context().add_class("cs-log")
        log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroller = Gtk.ScrolledWindow()
        scroller.set_min_content_height(120)
        scroller.add(log_view)
        expander = Gtk.Expander(label="Raw output")
        expander.add(scroller)
        box.add(expander)

        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.connect("response", self.on_response)
        self.show_all()

    def _build_steps(self):
        self.url_entry = Gtk.Entry(editable=False)
        self.url_entry.set_width_chars(34)
        url_copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.BUTTON)
        url_copy.set_tooltip_text("Copy link")
        url_copy.connect("clicked", lambda *_: self._copy(self.url_entry.get_text()))
        url_open = Gtk.Button(label="Open")
        url_open.connect("clicked", self.on_open_browser)

        url_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        url_row.pack_start(self.url_entry, True, True, 0)
        url_row.pack_start(url_copy, False, False, 0)
        url_row.pack_start(url_open, False, False, 0)

        self.steps.add(Gtk.Label(label="1. Open this link", xalign=0))
        self.steps.add(url_row)

        self.code_label = Gtk.Label(label="……")
        self.code_label.get_style_context().add_class("cs-code")
        self.code_label.set_selectable(True)
        code_copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.BUTTON)
        code_copy.set_tooltip_text("Copy code")
        code_copy.set_valign(Gtk.Align.CENTER)
        code_copy.connect("clicked", lambda *_: self._copy(self.code_label.get_text()))

        code_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        code_row.set_halign(Gtk.Align.CENTER)
        code_row.pack_start(self.code_label, False, False, 0)
        code_row.pack_start(code_copy, False, False, 0)

        self.steps.add(Gtk.Label(label="2. Enter this code", xalign=0))
        self.steps.add(code_row)

    def _copy(self, text):
        if not text or text == "……":
            return
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        self.status.set_text("Copied.")

    def on_open_browser(self, _button):
        url = self.url_entry.get_text()
        if url:
            Gtk.show_uri_on_window(self, url, Gdk.CURRENT_TIME)

    def on_start(self, _button):
        name = self.name_entry.get_text().strip()
        if not NAME_RE.match(name):
            self.status.set_text("Use letters, digits, dot, dash or underscore only.")
            return
        if name in Store.profiles():
            self.status.set_text(f"{name} already exists. Pick another name.")
            return

        self.result_name = name
        self.name_entry.set_sensitive(False)
        self.start_button.set_sensitive(False)
        self.start_button.set_label("Waiting for browser…")
        self.steps.set_no_show_all(False)
        self.steps.show_all()
        self.status.set_text("Starting codex login --device-auth …")

        # Park the account that is currently live so its rotated token survives.
        self.saved_previous = Store.sync_live()
        AUTH_FILE.unlink(missing_ok=True)

        self.login = DeviceLogin(
            on_url=self.on_url, on_code=self.on_code,
            on_line=self.on_line, on_done=self.on_done,
        )
        self.login.start()

    def on_url(self, url):
        self.url_entry.set_text(url)
        self.status.set_text("Open the link and enter the code.")

    def on_code(self, code):
        self.code_label.set_text(code)

    def on_line(self, line):
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end, line + "\n")

    def on_done(self, ok, error):
        if ok:
            shutil.copy2(AUTH_FILE, Store.profile_path(self.result_name))
            Store.set_active(self.result_name)
            self.response(Gtk.ResponseType.OK)
            return

        self.status.set_text(error or "Sign-in failed.")
        self.start_button.set_sensitive(True)
        self.start_button.set_label("Try again")
        self.name_entry.set_sensitive(True)
        self._restore()

    def _restore(self):
        """Put the previously live account back if the new sign-in didn't land."""
        if self.saved_previous:
            source = Store.profile_path(self.saved_previous)
            if source.is_file():
                shutil.copy2(source, AUTH_FILE)
                Store.set_active(self.saved_previous)
        self.saved_previous = None

    def on_response(self, _dialog, response):
        if response != Gtk.ResponseType.OK:
            if self.login:
                self.login.cancel()
            self._restore()


# -------------------------------------------------------------- main window


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Codex Switch")
        self.set_default_size(420, 440)
        self.set_icon_name(ICON_NAME)

        header = Gtk.HeaderBar(show_close_button=True, title="Codex Switch")
        header.set_subtitle(str(CODEX_HOME))
        add_button = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        add_button.set_tooltip_text("Add account")
        add_button.connect("clicked", self.on_add)
        header.pack_start(add_button)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Reload")
        refresh.connect("clicked", lambda *_: self.reload())
        header.pack_end(refresh)
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)

        self.banner = Gtk.InfoBar()
        self.banner.set_message_type(Gtk.MessageType.INFO)
        self.banner.set_show_close_button(True)
        self.banner.connect("response", lambda bar, *_: bar.hide())
        self.banner_label = Gtk.Label(label="", wrap=True, xalign=0)
        self.banner.get_content_area().add(self.banner_label)
        self.banner.set_no_show_all(True)
        outer.pack_start(self.banner, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scroller.add(self.listbox)
        outer.pack_start(scroller, True, True, 0)

        self.footer = Gtk.Label(xalign=0, wrap=True)
        self.footer.get_style_context().add_class("cs-meta")
        self.footer.set_margin_start(12)
        self.footer.set_margin_end(12)
        self.footer.set_margin_top(8)
        self.footer.set_margin_bottom(10)
        outer.pack_start(self.footer, False, False, 0)

        self.connect("delete-event", self.on_delete)
        self.reload()

    # -- rendering

    def reload(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        profiles = Store.profiles()
        active = Store.active()

        if not profiles:
            empty = Gtk.Label(
                label="No accounts yet.\nUse + to sign in to your first one.",
                justify=Gtk.Justification.CENTER,
            )
            empty.set_margin_top(48)
            empty.set_margin_bottom(48)
            self.listbox.add(empty)
        else:
            for name in profiles:
                self.listbox.add(self._row(name, name == active))

        self.listbox.show_all()
        self.footer.set_text(
            f"{len(profiles)} account(s) · active: {active or 'none'}\n"
            "After switching, close and reopen VS Code."
        )
        self.get_application().rebuild_menu()

    def _row(self, name, is_active):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_border_width(10)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=name, xalign=0)
        label.get_style_context().add_class("cs-name")
        title_row.pack_start(label, False, False, 0)
        if is_active:
            pill = Gtk.Label(label="ACTIVE")
            pill.get_style_context().add_class("cs-pill")
            pill.set_valign(Gtk.Align.CENTER)
            title_row.pack_start(pill, False, False, 0)
        text.pack_start(title_row, False, False, 0)

        source = AUTH_FILE if is_active and AUTH_FILE.is_file() else Store.profile_path(name)
        info = describe(source)
        parts = [p for p in (info["email"], info["plan"]) if p]
        if info["refreshed"]:
            parts.append(f"refreshed {info['refreshed']}")
        meta = Gtk.Label(label=" · ".join(parts) or "no details", xalign=0)
        meta.get_style_context().add_class("cs-meta")
        meta.set_ellipsize(3)  # Pango.EllipsizeMode.END
        text.pack_start(meta, False, False, 0)
        box.pack_start(text, True, True, 0)

        if not is_active:
            use = Gtk.Button(label="Use")
            use.set_valign(Gtk.Align.CENTER)
            use.connect("clicked", lambda *_: self.do_switch(name))
            box.pack_start(use, False, False, 0)

        menu_button = Gtk.MenuButton()
        menu_button.set_valign(Gtk.Align.CENTER)
        menu_button.add(Gtk.Image.new_from_icon_name("view-more-symbolic", Gtk.IconSize.BUTTON))
        menu = Gtk.Menu()
        rename_item = Gtk.MenuItem(label="Rename")
        rename_item.connect("activate", lambda *_: self.do_rename(name))
        remove_item = Gtk.MenuItem(label="Remove")
        remove_item.connect("activate", lambda *_: self.do_delete(name))
        menu.append(rename_item)
        menu.append(remove_item)
        menu.show_all()
        menu_button.set_popup(menu)
        box.pack_start(menu_button, False, False, 0)

        row.add(box)
        return row

    def notify(self, text, kind=Gtk.MessageType.INFO):
        self.banner.set_message_type(kind)
        self.banner_label.set_text(text)
        self.banner.set_no_show_all(False)
        self.banner.show_all()

    # -- actions

    def do_switch(self, name):
        running = codex_running()
        if running:
            dialog = Gtk.MessageDialog(
                transient_for=self, modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Codex is still running",
            )
            dialog.format_secondary_text(
                "Switching now can overwrite the file that is about to be saved. "
                "Quit Codex first, or continue anyway."
            )
            answer = dialog.run()
            dialog.destroy()
            if answer != Gtk.ResponseType.OK:
                return

        try:
            previous = Store.switch(name)
        except Exception as exc:
            self.notify(str(exc), Gtk.MessageType.ERROR)
            return

        self.reload()
        self.notify(
            f"Switched {previous or 'none'} → {name}. Close and reopen VS Code to pick it up."
        )

    def do_rename(self, name):
        dialog = Gtk.Dialog(title="Rename account", transient_for=self, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Rename", Gtk.ResponseType.OK)
        entry = Gtk.Entry(text=name)
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_border_width(14)
        area.set_spacing(8)
        area.add(entry)
        dialog.show_all()
        answer = dialog.run()
        new = entry.get_text().strip()
        dialog.destroy()

        if answer != Gtk.ResponseType.OK or new == name:
            return
        if not NAME_RE.match(new) or new in Store.profiles():
            self.notify("That name is not available.", Gtk.MessageType.ERROR)
            return
        Store.rename(name, new)
        self.reload()

    def do_delete(self, name):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Remove {name}?",
        )
        dialog.format_secondary_text(
            "This deletes the saved credential file only. The ChatGPT account itself "
            "is untouched and you can sign in again later."
        )
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            Store.delete(name)
            self.reload()

    def on_add(self, _button=None):
        dialog = AddAccountDialog(self)
        answer = dialog.run()
        name = dialog.result_name
        dialog.destroy()
        self.reload()
        if answer == Gtk.ResponseType.OK:
            self.notify(f"Added {name} and made it active. Reopen VS Code to use it.")

    def on_delete(self, *_args):
        self.hide()
        return True  # keep running in the tray


# ---------------------------------------------------------------- the app


class CodexSwitchApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.indicator = None
        self.status_icon = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def do_activate(self):
        if self.window is None:
            CODEX_HOME.mkdir(parents=True, exist_ok=True)
            self.window = MainWindow(self)
            self._setup_tray()
        self.window.show_all()
        self.window.present()

    # -- tray

    def _setup_tray(self):
        if Indicator is not None:
            self.indicator = Indicator.Indicator.new(
                APP_ID, ICON_NAME, Indicator.IndicatorCategory.APPLICATION_STATUS
            )
            self.indicator.set_status(Indicator.IndicatorStatus.ACTIVE)
        else:
            self.status_icon = Gtk.StatusIcon.new_from_icon_name(ICON_NAME)
            self.status_icon.set_tooltip_text("Codex Switch")
            self.status_icon.connect("activate", lambda *_: self.do_activate())
            self.status_icon.connect("popup-menu", self._popup_status_menu)
        self.rebuild_menu()

    def _popup_status_menu(self, icon, button, activate_time):
        self._menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)

    def rebuild_menu(self):
        menu = Gtk.Menu()
        active = Store.active()

        for name in Store.profiles():
            item = Gtk.CheckMenuItem(label=name)
            item.set_draw_as_radio(True)
            item.set_active(name == active)
            if name == active:
                item.set_sensitive(False)
            else:
                item.connect("activate", lambda _i, n=name: self.window.do_switch(n))
            menu.append(item)

        if Store.profiles():
            menu.append(Gtk.SeparatorMenuItem())

        add_item = Gtk.MenuItem(label="Add account…")
        add_item.connect("activate", lambda *_: self._show_and(self.window.on_add))
        menu.append(add_item)

        show_item = Gtk.MenuItem(label="Open Codex Switch")
        show_item.connect("activate", lambda *_: self.do_activate())
        menu.append(show_item)

        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: self.quit())
        menu.append(quit_item)

        menu.show_all()
        self._menu = menu

        if self.indicator is not None:
            self.indicator.set_menu(menu)
            self.indicator.set_title(f"Codex: {active or 'none'}")

    def _show_and(self, callback):
        self.do_activate()
        callback()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = CodexSwitchApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

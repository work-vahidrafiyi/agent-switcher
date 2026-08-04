#!/usr/bin/env python3
"""
Codex Switch (Windows) - manage multiple Codex (ChatGPT) accounts and switch
between them.

Never calls `codex logout`, because that revokes the refresh token server-side
and any copy you saved earlier stops working. Instead the live auth.json is
copied back into the active profile first, then the files are swapped.

Profiles live next to auth.json:
    %USERPROFILE%\\.codex\\auth.<name>.json
    %USERPROFILE%\\.codex\\.active          plain text, current profile name

Requires: Python 3.9+ (tkinter is bundled).
Optional: pip install pystray pillow      -> adds the system tray icon.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
AUTH_FILE = CODEX_HOME / "auth.json"
ACTIVE_FILE = CODEX_HOME / ".active"

PROFILE_RE = re.compile(r"^auth\.(?P<name>[^.].*)\.json$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\r")
URL_RE = re.compile(r"https?://[^\s'\"<>\)\]]+")
CODE_DASHED_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4,6})\b")
CODE_PLAIN_RE = re.compile(r"\b([A-Z0-9]{6,10})\b")

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

BG = "#f4f4f5"
CARD = "#ffffff"
INK = "#18181b"
MUTED = "#71717a"
ACCENT = "#2563eb"
LINE = "#e4e4e7"


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
    """Pull email / plan / refresh time out of an auth file."""
    out = {"email": None, "plan": None, "refreshed": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out

    claims = decode_jwt((data.get("tokens") or {}).get("id_token", ""))

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
    @staticmethod
    def profile_path(name):
        return CODEX_HOME / f"auth.{name}.json"

    @staticmethod
    def profiles():
        if not CODEX_HOME.is_dir():
            return []
        found = []
        for entry in CODEX_HOME.iterdir():
            match = PROFILE_RE.match(entry.name)
            if match and entry.is_file():
                found.append(match.group("name"))
        return sorted(found)

    @staticmethod
    def active():
        try:
            return ACTIVE_FILE.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    @staticmethod
    def set_active(name):
        CODEX_HOME.mkdir(parents=True, exist_ok=True)
        if name is None:
            ACTIVE_FILE.unlink(missing_ok=True)
        else:
            ACTIVE_FILE.write_text(name + "\n", encoding="utf-8")

    @classmethod
    def sync_live(cls):
        """Copy the live auth.json back into the active profile.

        This is what keeps a rotated refresh token from going stale.
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
        cls.profile_path(old).replace(cls.profile_path(new))
        if cls.active() == old:
            cls.set_active(new)

    @classmethod
    def delete(cls, name):
        cls.profile_path(name).unlink(missing_ok=True)
        if cls.active() == name:
            cls.set_active(None)
            AUTH_FILE.unlink(missing_ok=True)


def codex_running():
    """True if a codex process is alive, so we don't swap files mid-flight."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq codex.exe", "/NH"],
            capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW,
        )
    except Exception:
        return False
    return "codex.exe" in result.stdout.lower()


def codex_command(*args):
    """Build a command list that also works when codex is an npm .cmd shim."""
    exe = shutil.which("codex")
    if not exe:
        return None
    if exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe, *args]
    return [exe, *args]


# ------------------------------------------------------------ device login


class DeviceLogin:
    """Runs `codex login --device-auth` and reports the link and the code."""

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
                self.proc.kill()
            except Exception:
                pass

    def _scan(self, line):
        if not self._saw_url:
            urls = URL_RE.findall(line)
            preferred = [u for u in urls if re.search(r"device|activate|auth", u)]
            if preferred or urls:
                self._saw_url = True
                self.on_url((preferred or urls)[0].rstrip(".,"))

        if not self._saw_code:
            match = CODE_DASHED_RE.search(line)
            if not match and re.search(r"code", line, re.I):
                match = CODE_PLAIN_RE.search(line)
            if match:
                self._saw_code = True
                self.on_code(match.group(1))

    def _run(self):
        command = codex_command("login", "--device-auth")
        if command is None:
            self.on_line("codex was not found in PATH")
            self.on_done(False, "codex CLI is not installed, or not in PATH")
            return

        env = dict(os.environ, NO_COLOR="1", TERM="dumb")
        try:
            self.proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=NO_WINDOW,
                env=env,
            )
        except Exception as exc:
            self.on_done(False, str(exc))
            return

        buffer = ""
        stream = self.proc.stdout
        while not self._stop.is_set():
            chunk = stream.read(1)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", "replace")
            if chunk in (b"\n", b"\r"):
                for line in ANSI_RE.sub("\n", buffer).split("\n"):
                    line = line.strip()
                    if line:
                        self.on_line(line)
                        self._scan(line)
                buffer = ""

        tail = ANSI_RE.sub("\n", buffer).strip()
        if tail:
            self.on_line(tail)
            self._scan(tail)

        code = self.proc.wait() if self.proc else 1
        if self._stop.is_set():
            self.on_done(False, "Cancelled")
        elif code == 0 and AUTH_FILE.is_file():
            self.on_done(True, None)
        else:
            self.on_done(False, f"codex login exited with {code}")


# ------------------------------------------------------------------- add ui


class AddAccountWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Add account")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app.root)
        self.grab_set()

        self.login = None
        self.saved_previous = None
        self.name = None

        frame = tk.Frame(self, bg=BG, padx=18, pady=16)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame, bg=BG, fg=INK, justify="left", anchor="w",
            text="Name the account, then sign in through your browser.",
        ).pack(fill="x")

        row = tk.Frame(frame, bg=BG)
        row.pack(fill="x", pady=(12, 0))
        tk.Label(row, text="Name", bg=BG, fg=MUTED, width=6, anchor="w").pack(side="left")
        self.name_var = tk.StringVar()
        existing = Store.profiles()
        index = 1
        while f"account{index}" in existing:
            index += 1
        self.name_var.set(f"account{index}")
        self.name_entry = ttk.Entry(row, textvariable=self.name_var, width=28)
        self.name_entry.pack(side="left", fill="x", expand=True)

        self.start_button = ttk.Button(frame, text="Start sign-in", command=self.on_start)
        self.start_button.pack(fill="x", pady=(12, 0))

        self.steps = tk.Frame(frame, bg=BG)

        tk.Label(self.steps, text="1.  Open this link", bg=BG, fg=MUTED, anchor="w").pack(
            fill="x", pady=(14, 4)
        )
        url_row = tk.Frame(self.steps, bg=BG)
        url_row.pack(fill="x")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var, state="readonly")
        self.url_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(url_row, text="Copy", width=6,
                   command=lambda: self.copy(self.url_var.get())).pack(side="left", padx=(6, 0))
        ttk.Button(url_row, text="Open", width=6, command=self.open_browser).pack(side="left", padx=(4, 0))

        tk.Label(self.steps, text="2.  Enter this code", bg=BG, fg=MUTED, anchor="w").pack(
            fill="x", pady=(14, 4)
        )
        code_row = tk.Frame(self.steps, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        code_row.pack(fill="x")
        self.code_var = tk.StringVar(value="- - - -")
        tk.Label(
            code_row, textvariable=self.code_var, bg=CARD, fg=INK,
            font=("Consolas", 26, "bold"), pady=10,
        ).pack(side="left", padx=(14, 0))
        ttk.Button(code_row, text="Copy", width=6,
                   command=lambda: self.copy(self.code_var.get())).pack(side="right", padx=10)

        self.status = tk.Label(frame, text="", bg=BG, fg=MUTED, anchor="w",
                               wraplength=380, justify="left")
        self.status.pack(fill="x", pady=(12, 0))

        self.log_visible = False
        self.log_toggle = ttk.Button(frame, text="Show raw output", command=self.toggle_log)
        self.log_toggle.pack(fill="x", pady=(8, 0))
        self.log = tk.Text(frame, height=7, bg=CARD, fg=MUTED, font=("Consolas", 8),
                           relief="flat", highlightbackground=LINE, highlightthickness=1)

        ttk.Button(frame, text="Close", command=self.on_close).pack(fill="x", pady=(10, 0))
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # -- helpers, all called on the Tk thread via app.ui()

    def copy(self, text):
        if not text or text.startswith("-"):
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.config(text="Copied.")

    def open_browser(self):
        if self.url_var.get():
            webbrowser.open(self.url_var.get())

    def toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log.pack(fill="x", pady=(6, 0))
            self.log_toggle.config(text="Hide raw output")
        else:
            self.log.pack_forget()
            self.log_toggle.config(text="Show raw output")

    def on_start(self):
        name = self.name_var.get().strip()
        if not NAME_RE.match(name):
            self.status.config(text="Use letters, digits, dot, dash or underscore only.")
            return
        if name in Store.profiles():
            self.status.config(text=f"{name} already exists. Pick another name.")
            return

        self.name = name
        self.name_entry.state(["disabled"])
        self.start_button.state(["disabled"])
        self.start_button.config(text="Waiting for browser...")
        self.steps.pack(fill="x")
        self.status.config(text="Starting codex login --device-auth ...")

        # Park the account that is live right now so its token survives.
        self.saved_previous = Store.sync_live()
        AUTH_FILE.unlink(missing_ok=True)

        self.login = DeviceLogin(
            on_url=lambda u: self.app.ui(self._set_url, u),
            on_code=lambda c: self.app.ui(self._set_code, c),
            on_line=lambda l: self.app.ui(self._append, l),
            on_done=lambda ok, err: self.app.ui(self._finish, ok, err),
        )
        self.login.start()

    def _set_url(self, url):
        self.url_var.set(url)
        self.status.config(text="Open the link and enter the code.")

    def _set_code(self, code):
        self.code_var.set(code)

    def _append(self, line):
        self.log.insert("end", line + "\n")
        self.log.see("end")

    def _finish(self, ok, error):
        if ok:
            shutil.copy2(AUTH_FILE, Store.profile_path(self.name))
            Store.set_active(self.name)
            self.saved_previous = None
            self.grab_release()
            self.destroy()
            self.app.reload()
            self.app.notify(f"Added {self.name} and made it active. Reopen VS Code to use it.")
            return

        self.status.config(text=error or "Sign-in failed.")
        self.start_button.state(["!disabled"])
        self.start_button.config(text="Try again")
        self.name_entry.state(["!disabled"])
        self._restore()

    def _restore(self):
        """Put the previously live account back if the new sign-in didn't land."""
        if self.saved_previous:
            source = Store.profile_path(self.saved_previous)
            if source.is_file():
                shutil.copy2(source, AUTH_FILE)
                Store.set_active(self.saved_previous)
        self.saved_previous = None

    def on_close(self):
        if self.login:
            self.login.cancel()
        self._restore()
        self.grab_release()
        self.destroy()
        self.app.reload()


# ------------------------------------------------------------------ main ui


class App:
    def __init__(self):
        CODEX_HOME.mkdir(parents=True, exist_ok=True)

        self.root = tk.Tk()
        self.root.title("Codex Switch")
        self.root.geometry("440x480")
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        header = tk.Frame(self.root, bg=BG, padx=16, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="Codex Switch", bg=BG, fg=INK,
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Button(header, text="Reload", width=8, command=self.reload).pack(side="right")
        ttk.Button(header, text="+ Add", width=8, command=self.on_add).pack(side="right", padx=(0, 6))

        tk.Label(header, text=str(CODEX_HOME), bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(10, 0), pady=(6, 0))

        self.banner = tk.Label(self.root, bg="#dbeafe", fg="#1e3a8a", anchor="w",
                               justify="left", wraplength=400, padx=12, pady=8)

        self.list_frame = tk.Frame(self.root, bg=BG, padx=12)
        self.list_frame.pack(fill="both", expand=True)

        self.footer = tk.Label(self.root, bg=BG, fg=MUTED, anchor="w", justify="left",
                               padx=16, pady=10, font=("Segoe UI", 8))
        self.footer.pack(fill="x")

        self.tray = None
        self.reload()
        if HAS_TRAY:
            self.start_tray()

    # -- thread bridge

    def ui(self, func, *args):
        self.root.after(0, lambda: func(*args))

    def notify(self, text):
        self.banner.config(text=text)
        self.banner.pack(fill="x", before=self.list_frame)

    # -- rendering

    def reload(self):
        for child in self.list_frame.winfo_children():
            child.destroy()

        profiles = Store.profiles()
        active = Store.active()

        if not profiles:
            tk.Label(self.list_frame, bg=BG, fg=MUTED, justify="center",
                     text="\n\nNo accounts yet.\nUse + Add to sign in to your first one.").pack()
        else:
            for name in profiles:
                self._card(name, name == active)

        self.footer.config(
            text=f"{len(profiles)} account(s)  |  active: {active or 'none'}\n"
                 "After switching, close and reopen VS Code."
        )
        if self.tray:
            self.tray.menu = self.build_tray_menu()
            self.tray.update_menu()

    def _card(self, name, is_active):
        card = tk.Frame(self.list_frame, bg=CARD, highlightbackground=LINE,
                        highlightthickness=1, padx=12, pady=10)
        card.pack(fill="x", pady=4)

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=name, bg=CARD, fg=INK,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        if is_active:
            tk.Label(top, text=" ACTIVE ", bg="#dbeafe", fg=ACCENT,
                     font=("Segoe UI", 7, "bold")).pack(side="left", padx=(8, 0))
        else:
            ttk.Button(top, text="Use", width=6,
                       command=lambda: self.do_switch(name)).pack(side="right")

        source = AUTH_FILE if is_active and AUTH_FILE.is_file() else Store.profile_path(name)
        info = describe(source)
        parts = [p for p in (info["email"], info["plan"]) if p]
        if info["refreshed"]:
            parts.append(f"refreshed {info['refreshed']}")
        tk.Label(card, text="  ".join(parts) or "no details", bg=CARD, fg=MUTED,
                 anchor="w", font=("Segoe UI", 8)).pack(fill="x", pady=(2, 6))

        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x")
        ttk.Button(actions, text="Rename", width=8,
                   command=lambda: self.do_rename(name)).pack(side="left")
        ttk.Button(actions, text="Remove", width=8,
                   command=lambda: self.do_delete(name)).pack(side="left", padx=(6, 0))

    # -- actions

    def do_switch(self, name):
        if codex_running():
            proceed = messagebox.askokcancel(
                "Codex is still running",
                "Switching now can overwrite the file Codex is about to save.\n\n"
                "Quit Codex first, or continue anyway.",
                parent=self.root,
            )
            if not proceed:
                return
        try:
            previous = Store.switch(name)
        except Exception as exc:
            messagebox.showerror("Switch failed", str(exc), parent=self.root)
            return

        self.reload()
        self.notify(f"Switched {previous or 'none'} to {name}. "
                    "Close and reopen VS Code to pick it up.")

    def do_rename(self, name):
        new = simpledialog.askstring("Rename account", "New name:",
                                     initialvalue=name, parent=self.root)
        if not new or new == name:
            return
        new = new.strip()
        if not NAME_RE.match(new) or new in Store.profiles():
            messagebox.showerror("Rename failed", "That name is not available.", parent=self.root)
            return
        Store.rename(name, new)
        self.reload()

    def do_delete(self, name):
        confirm = messagebox.askokcancel(
            f"Remove {name}?",
            "This deletes the saved credential file only. The ChatGPT account itself "
            "is untouched and you can sign in again later.",
            parent=self.root,
        )
        if confirm:
            Store.delete(name)
            self.reload()

    def on_add(self):
        AddAccountWindow(self)

    # -- tray

    def make_icon(self):
        image = Image.new("RGB", (64, 64), "#18181b")
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 10, 54, 54), outline="#60a5fa", width=6)
        draw.rectangle((30, 4, 64, 34), fill="#18181b")
        return image

    def build_tray_menu(self):
        active = Store.active()
        items = []
        for name in Store.profiles():
            items.append(pystray.MenuItem(
                name,
                (lambda n: lambda *_: self.ui(self.do_switch, n))(name),
                checked=(lambda n: lambda _item: n == Store.active())(name),
                radio=True,
                enabled=(name != active),
            ))
        if items:
            items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Add account...", lambda *_: self.ui(self._show_and_add)))
        items.append(pystray.MenuItem("Open Codex Switch", lambda *_: self.ui(self.show),
                                      default=True))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Quit", lambda *_: self.ui(self.quit)))
        return pystray.Menu(*items)

    def start_tray(self):
        self.tray = pystray.Icon("codex-switch", self.make_icon(),
                                 "Codex Switch", self.build_tray_menu())
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _show_and_add(self):
        self.show()
        self.on_add()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def on_close(self):
        if self.tray:
            self.root.withdraw()  # keep running in the tray
        else:
            self.quit()

    def quit(self):
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()

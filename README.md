🇬🇧 English | [🇮🇷 فارسی](README.fa.md)

# Agent Switcher 🔄

**Keep all your Codex accounts in one place, check their remaining quota, and switch between them in seconds.**

> 📌 **Current provider support:** Agent Switcher currently works with **OpenAI Codex only**. Support for other coding agents is planned for future releases.

## Why Agent Switcher? 🤔

Many Codex users have more than one account: a personal account, a work account, a client account, or a separate account for another project. Signing out, signing back in, and remembering which account still has quota quickly becomes frustrating.

There is also a hidden problem. Signing out of Codex can invalidate the saved login, and Codex may update its login information in the background. That means a simple "copy the login file" solution can stop working when you need it most.

Agent Switcher takes care of this automatically. Before changing accounts or starting a new login, it safely saves the latest state of the current account. If a login is cancelled or fails, your previous account is restored exactly as it was. You just pick an account and continue working. ✨

> 🔐 Saved accounts contain private login information. Never share or commit those files.

## Features 🚀

### 👤 Account management

- ✅ Add accounts with browser sign-in
- ✅ Add accounts with a one-time device code
- ✅ Switch accounts with one click
- ✅ Rename and remove saved accounts
- ✅ See account email, plan, and last refresh time
- ✅ Restore the previous account after a failed or cancelled login
- ✅ Warn when Codex is still running during a switch
- ✅ View recent account-switch history

### 📊 Usage and quota

- ✅ Five-hour remaining quota
- ✅ Weekly remaining quota
- ✅ Color-coded progress bars
- ✅ Reset time and last-check time
- ✅ Small usage-history charts
- ✅ Refresh one account or all accounts
- ✅ Automatic background refresh every 15 minutes
- ✅ Smooth background checks without freezing the app
- ✅ Keeps inactive accounts signed in during quota checks
- ✅ Low-quota tray notifications
- ✅ Friendly "usage unavailable" state when a check fails

### 🧠 Smart Pick

- ✅ Finds the account with the most useful remaining quota
- ✅ Checks both five-hour and weekly limits
- ✅ Uses recent saved results to avoid unnecessary requests
- ✅ Refreshes old results before choosing
- ✅ Never guesses when no reliable data is available

### 🖥️ Desktop and tray

- ✅ One desktop app for Linux and Windows
- ✅ Quick switching from the system tray
- ✅ Active account and remaining quota in the tray tooltip
- ✅ Closing the window keeps the app in the tray
- ✅ Explicit Quit action in the tray menu
- ✅ Configurable system-wide keyboard shortcut
- ✅ Small quick-switch popup near the tray
- ✅ Graceful tray fallback when a global hotkey is unavailable

> ℹ️ The keyboard shortcut works best on Windows and X11 Linux. Wayland may block it, but tray switching still works.

### 🛡️ Privacy and control

- ✅ Offline mode for disabling all quota checks
- ✅ Direct connection or custom HTTP proxy for app requests
- ✅ No automatic account request when the app first opens, so you can configure the proxy first
- ✅ Login and account switching still work in offline mode
- ✅ Network transparency panel
- ✅ Clear list of sign-in, quota-check, and account-update requests
- ✅ Local activity log with automatic size limits
- ✅ API-key accounts are skipped during quota checks

### 🎨 Personalization and accessibility

- ✅ Dark theme
- ✅ Light theme
- ✅ Automatic system theme
- ✅ English interface
- ✅ Persian interface with right-to-left layout
- ✅ Bundled Vazirmatn font for Persian
- ✅ First-run onboarding
- ✅ Replayable onboarding and contextual help

### ⌨️ CLI

- ✅ Short `asw` command
- ✅ List, switch, add, rename, remove, and inspect accounts
- ✅ Optional quota details with `asw list --details`
- ✅ JSON output for scripts with `--json`
- ✅ Launch the GUI with `asw gui`

## Screenshots 📸

![Agent Switcher main window](docs/screenshot-main.png)

![Expanded account usage details](docs/screenshot-usage.png)

## Installation 📦

Agent Switcher currently supports **Linux and Windows**. macOS has not been built or tested and is not supported yet.

The Codex CLI must be installed and available as `codex` to add an account.

### Install with pipx

From a checkout of this repository:

```shell
pipx install .
asw --version
asw gui
```

`pipx` is recommended because it keeps Agent Switcher and its dependencies separate from the rest of your Python environment.

### Install with pip

Linux:

```shell
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
asw gui
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
asw gui
```

### Download a ready-to-run GUI

Open [GitHub Releases](../../releases/latest) and download the file for your system. Release downloads open the GUI directly. Install with `pipx` or `pip` when you also need the `asw` CLI.

Linux x86_64:

```shell
tar -xzf agent-switcher-linux-x86_64.tar.gz
chmod +x agent-switcher
./agent-switcher
```

Windows x86_64:

1. Download `agent-switcher-windows-x86_64.exe`.
2. Double-click it to open Agent Switcher.
3. The app is currently unsigned. If Microsoft SmartScreen appears, select **More info**, then **Run anyway**.

## Quick start ⚡

See your saved accounts:

```shell
asw list
```

Switch accounts:

```shell
asw switch <name>
```

Open the GUI:

```shell
asw gui
```

After opening the GUI, you can close the main window and keep Agent Switcher ready in the system tray.

## Coming soon 🛠️

These features are planned, but **are not included in the current release**:

- 🔜 Secure account storage with the operating system keyring
- 🔜 VS Code extension for switching without reloading
- 🔜 Claude Code account support
- 🔜 A separate `CODEX_HOME` for every account
- 🔜 In-app update checks and release notifications

## Responsible use 🤝

Agent Switcher is for managing separate accounts, such as personal and work accounts. It is not intended to bypass a provider's rate limits. Users are responsible for following OpenAI's terms of service.

## Contributing 🛠️

Issues, focused pull requests, tests, documentation improvements, and Linux or Windows verification are welcome. Please never include real login files or tokens in an issue or commit.

## License 📄

Agent Switcher is released under the [MIT License](LICENSE).

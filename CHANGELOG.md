# Changelog

This file lists the changes users will notice in each Agent Switcher release.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.1] - 2026-08-22

### Fixed

- Let sign-in, usage checks, and account switching continue when the public-IP service is unavailable.
- Show one warning per accepted IP change instead of repeating it for every account check.

## [1.5.0] - 2026-08-12

### Added

- Add automatic and manual update checks with SHA-256 verification, in-place installation, and restart.
- Add per-account IP Guard checks before OpenAI sign-in, usage refreshes, and account switching without storing raw IP addresses.
- Add the launch-time local-privacy notice, configurable global quick-switch hotkey, smarter account selection, proxy retries, and expanded Codex CLI discovery.

### Changed

- Redesign the main interface, dialogs, and Settings with clearer sections and concise safety warnings.
- Reduce the Linux standalone download by more than 50% compared with v0.2.1 while retaining tested Qt functionality.

### Fixed

- Add the discovered NVM Codex directory to the login subprocess `PATH`, so Linux desktop launches can resolve the matching `node` runtime instead of failing with `/usr/bin/env: 'node': No such file or directory`.
- Force file-based Codex credentials for reliable account switching and improve browser/device authorization parsing.

## [0.3.0] - 2026-08-12

### Added

- Retry temporary network and proxy failures before reporting quota or token-refresh errors.
- Search common desktop and Node installation paths when a GUI launch cannot find the Codex CLI.
- Show a privacy notice explaining that saved login data stays local until the user explicitly hides it.
- Check GitHub for updates and securely download, verify, replace, and restart standalone releases.
- Add a lightweight per-account IP Guard that checks the public route before OpenAI sign-in, usage checks, and account switching without storing raw IP addresses.

### Changed

- Use a fixed, screen-safe main-window size and a consistent themed confirmation dialog.
- Organize Settings into separate appearance, network, quota, and quick-switch cards.
- Make the Linux standalone release more than 50% smaller than v0.2.1 by using a tested minimal Qt runtime, one icon family, system libraries, and stripped symbols.

### Fixed

- Force Codex to use file-based credentials so account switching is recognized on Windows.
- Prefer the actual device-authorization URL printed by Codex and decode escaped links correctly.
- Detect asynchronous global-hotkey registration failures and show the quick switch as an independent popup.
- Refresh incomplete quota samples before Smart Pick chooses an account.
- Replace raw process IDs and executable paths in the switch warning with concise guidance.

## [0.2.1] - 2026-08-05

### Fixed

- Agent Switcher no longer checks account usage immediately when the app opens.
- You now have time to choose a direct connection or configure an HTTP proxy before the first usage request.

### Documentation

- Added public screenshots of the main account list and expanded quota details.
- Clarified that the current release supports OpenAI Codex accounts only.

## [0.2.0] - 2026-08-05

### Added

- Choose between a direct connection and a custom HTTP proxy in Settings.
- Use the selected proxy for sign-in, quota checks, token updates, and CLI requests.
- Keep the proxy choice after closing and reopening the app.

## [0.1.1] - 2026-08-05

### Fixed

- Fixed the Windows app failing to open with a missing `termios` error.

## [0.1.0] - 2026-08-04

### Added

- Save, rename, remove, and safely switch between multiple Codex accounts.
- Sign in through the browser or with a one-time device code.
- Restore the previous account when a new sign-in is cancelled or fails.
- View five-hour and weekly remaining quota, reset times, and recent trends.
- Refresh quota in the background and receive low-quota notifications.
- Let Smart Pick choose another account with the most useful remaining quota.
- Switch quickly from the system tray or with a configurable global shortcut.
- Use Offline mode and the network transparency panel to control and review requests.
- Choose Dark, Light, or System theme and use the English or Persian interface.
- Use the `asw` CLI with regular or JSON output.
- Download standalone builds for Linux and Windows.

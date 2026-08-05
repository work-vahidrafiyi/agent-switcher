# Changelog

This file lists the changes users will notice in each Agent Switcher release.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

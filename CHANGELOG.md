# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-08-05

### Added

- Persisted direct/custom HTTP proxy settings for login, usage checks, token refresh, and CLI network operations.

## [0.1.1] - 2026-08-05

### Fixed

- Windows standalone builds no longer import the Unix-only `pty` and `termios` modules at startup.

## [0.1.0] - 2026-08-04

### Added

- Provider-neutral profile storage with atomic live-auth synchronization and safe switching.
- Browser and device-code login flows with rollback on cancellation or failure.
- Sequential usage checks, inactive-profile token refresh, quota history, and Smart pick.
- Cross-platform PySide6 GUI with tray switching, offline mode, notifications, themes, and onboarding.
- English and Persian interfaces with RTL layout and bundled Vazirmatn font support.
- Activity, switch-history, transparency, global-hotkey, CLI JSON, and usage-detail features.
- PyInstaller release packaging for Linux and Windows through GitHub Actions.

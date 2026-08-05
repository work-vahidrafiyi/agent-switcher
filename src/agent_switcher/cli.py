from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from . import __version__
from .core.login import DeviceLoginManager, LoginError
from .core.providers.codex import CodexProvider
from .core.store import Store, StoreError
from .core.proxy import load_proxy_config

EXIT_OK = 0
EXIT_USER = 1
EXIT_PROVIDER = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="asw")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", action="store_true", help="print a single JSON object to stdout")
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", parents=[json_parent], help="list saved profiles")
    list_parser.add_argument("--details", action="store_true", help="fetch usage details for each profile")
    switch = subparsers.add_parser("switch", parents=[json_parent], help="make a saved profile active")
    switch.add_argument("name")

    add = subparsers.add_parser("add", parents=[json_parent], help="run device auth and save a new profile")
    add.add_argument("name")

    subparsers.add_parser("current", parents=[json_parent], help="show the active profile")

    rename = subparsers.add_parser("rename", parents=[json_parent], help="rename a saved profile")
    rename.add_argument("old")
    rename.add_argument("new")

    remove = subparsers.add_parser("remove", parents=[json_parent], help="remove a saved profile")
    remove.add_argument("name")

    subparsers.add_parser("gui", help="open the graphical account switcher")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(CodexProvider())
    store.set_proxy_config(load_proxy_config(store.activity_log.path.parent / "settings.json"))

    try:
        if args.command == "list":
            profiles = []
            for profile in store.profile_list():
                item = profile.as_dict()
                if args.details:
                    item["usage"] = store.fetch_usage(profile).as_dict()
                profiles.append(item)
            return _success(args, {"profiles": profiles, "active": store.active()}, _print_list, profiles, store.active())

        if args.command == "current":
            profile = store.current_profile()
            payload = {"profile": profile.as_dict() if profile else None, "active": store.active()}
            return _success(args, payload, _print_current, profile)

        if args.command == "switch":
            running = store.running_processes()
            if running:
                print("Warning: a codex process appears to be running; it may write auth.json while switching.", file=sys.stderr)
                for line in running:
                    print(f"  {line}", file=sys.stderr)
            previous = store.switch(args.name)
            profile = store.profile(args.name)
            payload = {"previous": previous, "profile": profile.as_dict()}
            return _success(args, payload, lambda: print(f"Switched {previous or 'none'} to {args.name}."))

        if args.command == "add":
            manager = DeviceLoginManager(store)
            profile, result = manager.add_profile(
                args.name,
                on_url=lambda value: print(f"Verification URL: {value}", file=sys.stderr),
                on_code=lambda value: print(f"Code: {value}", file=sys.stderr),
                on_line=lambda value: print(value, file=sys.stderr),
            )
            payload = {"profile": profile.as_dict(), "login": result.as_dict()}
            return _success(args, payload, lambda: print(f"Added {args.name} and made it active."))

        if args.command == "rename":
            store.rename(args.old, args.new)
            return _success(args, {"old": args.old, "new": args.new}, lambda: print(f"Renamed {args.old} to {args.new}."))

        if args.command == "remove":
            store.delete(args.name)
            return _success(args, {"removed": args.name}, lambda: print(f"Removed {args.name}."))

        if args.command == "gui":
            return _launch_gui()

    except StoreError as exc:
        return _error(args, EXIT_USER, str(exc))
    except LoginError as exc:
        return _error(args, EXIT_PROVIDER, str(exc))
    except KeyboardInterrupt:
        return _error(args, EXIT_PROVIDER, "Cancelled")

    return _error(args, EXIT_USER, "Unknown command.")


def _success(args: argparse.Namespace, payload: dict[str, Any], printer, *printer_args) -> int:
    if args.json:
        print(json.dumps({"ok": True, **payload}, sort_keys=True))
    else:
        printer(*printer_args)
    return EXIT_OK


def _error(args: argparse.Namespace, code: int, message: str) -> int:
    if args.json:
        print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    else:
        print(message, file=sys.stderr)
    return code


def _print_list(profiles: list[dict[str, Any]], active: Optional[str]) -> None:
    if not profiles:
        print(f"No profiles. Active: {active or 'none'}")
        return
    for profile in profiles:
        marker = "*" if profile["active"] else " "
        identity = profile["identity"]
        parts = [value for value in (identity["email"], identity["plan"]) if value]
        if identity["refreshed"]:
            parts.append(f"refreshed {identity['refreshed']}")
        suffix = f" - {'; '.join(parts)}" if parts else ""
        print(f"{marker} {profile['name']}{suffix}")
        usage = profile.get("usage")
        if isinstance(usage, dict):
            print(f"    {_format_usage(usage)}")


def _format_usage(usage: dict[str, Any]) -> str:
    if not usage.get("available"):
        reason = usage.get("unavailable_reason") or "Usage is unavailable."
        return f"usage unavailable: {reason}"
    return (
        f"{_format_usage_window('5-hour', usage.get('five_hour_used_pct'), usage.get('five_hour_reset_at'))}; "
        f"{_format_usage_window('weekly', usage.get('weekly_used_pct'), usage.get('weekly_reset_at'))}; "
        f"checked {usage.get('checked_at')}"
    )


def _format_usage_window(label: str, value: object, reset_at: object) -> str:
    if not isinstance(value, (int, float)):
        return f"{label}: unavailable"
    return f"{label}: {value:g}% (resets {reset_at})"


def _print_current(profile) -> None:
    if profile is None:
        print("No active profile.")
        return
    identity = profile.identity
    parts = [value for value in (identity.email, identity.plan) if value]
    if identity.refreshed:
        parts.append(f"refreshed {identity.refreshed}")
    suffix = f" - {'; '.join(parts)}" if parts else ""
    print(f"{profile.name}{suffix}")


def _launch_gui() -> int:
    from .gui.app import main as gui_main

    return gui_main([sys.argv[0]])

if __name__ == "__main__":
    raise SystemExit(main())

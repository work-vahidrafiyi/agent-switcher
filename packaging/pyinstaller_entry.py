import sys

from agent_switcher.core.updater import run_update_helper


if __name__ == "__main__":
    helper_result = run_update_helper(sys.argv)
    if helper_result is not None:
        raise SystemExit(helper_result)
    from agent_switcher.gui.app import main

    raise SystemExit(main())

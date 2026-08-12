from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from agent_switcher.core.activity_log import ActivityLog


class GlobalHotkeyController(QObject):
    activated = Signal()

    def __init__(
        self,
        activity_log: ActivityLog,
        callback: Callable[[], None],
        hotkey: str,
        listener_factory=None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.activity_log = activity_log
        self.hotkey = hotkey
        self.listener_factory = listener_factory
        self.listener = None
        self.activated.connect(callback)

    def start(self) -> bool:
        self.stop()
        try:
            factory = self.listener_factory or _global_hotkeys_factory
            self.listener = factory({self.hotkey: self.activated.emit})
            self.listener.start()
            # pynput starts registration on a worker thread. Waiting for its
            # ready signal makes asynchronous backend failures observable here
            # instead of reporting a hotkey as registered when it is not.
            wait = getattr(self.listener, "wait", None)
            if callable(wait):
                wait()
            return True
        except Exception as exc:
            self.listener = None
            self._log_failure(exc)
            return False

    def stop(self) -> None:
        listener = self.listener
        self.listener = None
        if listener is None:
            return
        try:
            listener.stop()
        except Exception:
            pass

    def _log_failure(self, exc: Exception) -> None:
        try:
            self.activity_log.append(
                "hotkey",
                {
                    "action": "registration",
                    "hotkey": self.hotkey,
                    "success": False,
                    "error": str(exc) or type(exc).__name__,
                },
            )
        except Exception:
            pass


def _global_hotkeys_factory(mapping):
    from pynput.keyboard import GlobalHotKeys

    return GlobalHotKeys(mapping)

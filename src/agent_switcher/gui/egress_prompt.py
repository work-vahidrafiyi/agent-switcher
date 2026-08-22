from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from agent_switcher.core.egress_guard import EgressCheck
from agent_switcher.core.store import Store

from .i18n import tr
from .message_box import MessageDialog


def confirm_egress(
    store: Store,
    result: EgressCheck,
    parent: Optional[QWidget],
    on_suppress: Optional[Callable[[], None]] = None,
) -> bool:
    if result.allowed:
        return True

    title = tr("Public IP changed")
    message = tr(
        "Your public IP changed before {purpose} for {profile}.\n\n"
        "If a request from this new IP reaches OpenAI, OpenAI may block your account.\n\n"
        "Previous fingerprint: {previous}\n"
        "Current fingerprint: {current}\n\n"
        "Continue only if you recognize this network or proxy. "
        "You can also disable future IP-change warnings below.",
        purpose=tr(result.purpose),
        profile=result.profile,
        previous=result.previous_fingerprint[:12],
        current=result.current_fingerprint[:12],
    )

    dialog = MessageDialog(
        parent,
        QMessageBox.Icon.Warning,
        title,
        message,
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
        {
            QMessageBox.StandardButton.Ok: "Continue",
            QMessageBox.StandardButton.Cancel: "Cancel",
        },
        checkbox_label="Don't show IP change warnings again",
    )
    dialog.exec()
    if dialog.checkbox_checked():
        if on_suppress is not None:
            on_suppress()
        else:
            store.set_egress_guard_enabled(False)
    if dialog.selected != QMessageBox.StandardButton.Ok:
        return False
    store.approve_egress(result)
    return True

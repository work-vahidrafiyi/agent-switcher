from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from agent_switcher.core.egress_guard import EgressCheck
from agent_switcher.core.store import Store

from .i18n import tr
from .message_box import show_message


def confirm_egress(store: Store, result: EgressCheck, parent: Optional[QWidget]) -> bool:
    if result.allowed:
        return True

    title = tr("Public IP changed")
    message = tr(
        "Your public IP changed before {purpose} for {profile}.\n\n"
        "If a request from this new IP reaches OpenAI, OpenAI may block your account.\n\n"
        "Previous fingerprint: {previous}\n"
        "Current fingerprint: {current}\n\n"
        "This new IP fingerprint will be remembered after you acknowledge this warning. "
        "Previously seen IPs will not warn again.",
        purpose=tr(result.purpose),
        profile=result.profile,
        previous=result.previous_fingerprint[:12],
        current=result.current_fingerprint[:12],
    )

    show_message(
        parent,
        QMessageBox.Icon.Warning,
        title,
        message,
        QMessageBox.StandardButton.Ok,
        QMessageBox.StandardButton.Ok,
        {
            QMessageBox.StandardButton.Ok: "Got it",
        },
    )
    store.approve_egress(result)
    return True

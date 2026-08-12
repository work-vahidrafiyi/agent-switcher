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

    if result.status == "changed":
        title = tr("Public IP changed")
        message = tr(
            "IP Guard stopped {purpose} for {profile} before any OpenAI request was sent.\n\n"
            "Previous fingerprint: {previous}\n"
            "Current fingerprint: {current}\n\n"
            "Continue only if you expected this network or proxy change.",
            purpose=tr(result.purpose),
            profile=result.profile,
            previous=result.previous_fingerprint[:12],
            current=result.current_fingerprint[:12],
        )
    else:
        title = tr("Public IP could not be verified")
        message = tr(
            "IP Guard could not verify the public route before {purpose} for {profile}. "
            "No OpenAI request has been sent yet.\n\n{error}\n\n"
            "Continue once, or cancel and check your connection or proxy.",
            purpose=tr(result.purpose),
            profile=result.profile,
            error=result.error or tr("Public IP service is unavailable."),
        )

    answer = show_message(
        parent,
        QMessageBox.Icon.Warning,
        title,
        message,
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
        {
            QMessageBox.StandardButton.Ok: "Continue once",
            QMessageBox.StandardButton.Cancel: "Cancel",
        },
    )
    if answer != QMessageBox.StandardButton.Ok:
        return False
    if result.status == "changed":
        store.approve_egress(result)
    return True

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox


def show_selector_warning(dialog: Any, title: str, body: str) -> None:
    QMessageBox.warning(dialog, title, body)


def ensure_selector_callback_server(dialog: Any) -> bool:
    return dialog._selector_bridge.ensure_server()


def shutdown_selector_bridge(dialog: Any) -> None:
    dialog._selector_bridge.shutdown()


def open_external_selector_session(
    dialog: Any,
    *,
    kind: str,
    head: str | None = None,
    spindle: str | None = None,
    follow_up: dict | None = None,
    initial_assignments: list[dict] | None = None,
) -> bool:
    return dialog._selector_bridge.open_session(
        kind=kind,
        head=head,
        spindle=spindle,
        follow_up=follow_up,
        initial_assignments=initial_assignments,
    )

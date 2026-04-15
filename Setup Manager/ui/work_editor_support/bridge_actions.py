from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox


def show_selector_warning(dialog: Any, title: str, body: str) -> None:
    QMessageBox.warning(dialog, title, body)


def ensure_selector_callback_server(dialog: Any) -> bool:
    bridge = dialog._ensure_selector_bridge()
    return bool(bridge is not None and bridge.ensure_server())


def shutdown_selector_bridge(dialog: Any) -> None:
    bridge = getattr(dialog, "_selector_bridge", None)
    if bridge is not None:
        bridge.shutdown()


def open_external_selector_session(
    dialog: Any,
    *,
    kind: str,
    head: str | None = None,
    spindle: str | None = None,
    follow_up: dict | None = None,
    initial_assignments: list[dict] | None = None,
    initial_assignment_buckets: dict[str, list[dict]] | None = None,
) -> bool:
    bridge = dialog._ensure_selector_bridge()
    return bridge.open_session(
        kind=kind,
        head=head,
        spindle=spindle,
        follow_up=follow_up,
        initial_assignments=initial_assignments,
        initial_assignment_buckets=initial_assignment_buckets,
    )

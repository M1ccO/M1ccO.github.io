from __future__ import annotations

import json
import logging

from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


def send_selector_result_payload(
    window,
    *,
    kind: str,
    selected_items: list[dict],
    selector_head: str,
    selector_spindle: str,
    assignment_buckets_by_target: dict | None = None,
    target_key: str = "",
) -> bool:
    if kind == "tools" and not selected_items:
        QMessageBox.information(
            window,
            window._t("tool_library.selector.no_selection.title", "Nothing selected"),
            window._t(
                "tool_library.selector.no_selection.body",
                "Select at least one {kind} before sending the selection back.",
                kind=window._t("tool_library.selector.tools", "tools"),
            ),
        )
        return False

    callback_server = str(getattr(window, "_selector_callback_server", "") or "").strip()
    request_id = str(getattr(window, "_selector_request_id", "") or "").strip()
    if not callback_server:
        QMessageBox.warning(
            window,
            window._t("tool_library.selector.callback_missing.title", "Selection callback unavailable"),
            window._t(
                "tool_library.selector.callback_missing.body",
                "The selection callback server name is missing.",
            ),
        )
        return False

    payload = {
        "command": "selector_result",
        "request_id": request_id,
        "kind": kind,
        "items": selected_items,
        "selected_items": selected_items,
    }
    if kind == "tools":
        payload["selector_head"] = selector_head
        payload["selector_spindle"] = selector_spindle
        if assignment_buckets_by_target:
            payload["assignment_buckets_by_target"] = assignment_buckets_by_target
        if target_key:
            payload["target_key"] = target_key

    socket = QLocalSocket()
    socket.connectToServer(callback_server)
    if not socket.waitForConnected(300):
        QMessageBox.warning(
            window,
            window._t("tool_library.selector.callback_failed.title", "Selection callback unavailable"),
            window._t(
                "tool_library.selector.callback_failed.body",
                "Could not connect to the selection callback server.",
            ),
        )
        return False

    try:
        bytes_written = socket.write(json.dumps(payload).encode("utf-8"))
        if isinstance(bytes_written, int) and bytes_written < 0:
            raise RuntimeError("Selection payload write failed.")
        socket.flush()
    except Exception:
        logger.exception("selector: failed to send result payload to callback server %r", callback_server)
        QMessageBox.warning(
            window,
            window._t("tool_library.selector.callback_failed.title", "Selection callback unavailable"),
            window._t(
                "tool_library.selector.callback_failed.body",
                "Could not send the selected items back to Setup Manager.",
            ),
        )
        return False
    finally:
        try:
            socket.disconnectFromServer()
        except Exception:
            pass
        try:
            socket.deleteLater()
        except Exception:
            pass

    return True

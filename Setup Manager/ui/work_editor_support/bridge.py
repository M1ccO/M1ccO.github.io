from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SelectorSessionBridge(QObject):
    """Manage cross-app selector sessions for the Work Editor.

    The dialog still owns UI decisions and how accepted selections are applied.
    This bridge keeps the transport details in one place: callback server setup,
    request tracking, retries, payload validation, and launching Tool Library
    when the selector app is not already running.
    """

    def __init__(
        self,
        *,
        translate: Callable[[str, str | None], str],
        show_warning: Callable[[str, str], None],
        normalize_head: Callable[[str | None], str],
        normalize_spindle: Callable[[str | None], str],
        default_spindle: Callable[[], str],
        initial_tool_assignment_buckets: Callable[[], dict[str, list[dict]]],
        apply_tool_result: Callable[[dict, list[dict]], bool],
        apply_jaw_result: Callable[[dict, list[dict]], bool],
        open_jaw_selector: Callable[[str | None], bool | None],
        tool_library_server_name: str,
        tool_library_main_path: Path,
        tool_library_project_dir: Path,
        tool_library_exe_candidates: list[Path],
        parent=None,
    ):
        super().__init__(parent)
        self._translate = translate
        self._show_warning = show_warning
        self._normalize_head = normalize_head
        self._normalize_spindle = normalize_spindle
        self._default_spindle = default_spindle
        self._initial_tool_assignment_buckets = initial_tool_assignment_buckets
        self._apply_tool_result = apply_tool_result
        self._apply_jaw_result = apply_jaw_result
        self._open_jaw_selector = open_jaw_selector
        self._tool_library_server_name = tool_library_server_name
        self._tool_library_main_path = Path(tool_library_main_path)
        self._tool_library_project_dir = Path(tool_library_project_dir)
        self._tool_library_exe_candidates = [Path(item) for item in tool_library_exe_candidates]
        self._callback_server: QLocalServer | None = None
        self._callback_server_name = ""
        self._pending_requests: dict[str, dict] = {}

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def ensure_server(self) -> bool:
        if self._callback_server is not None and self._callback_server.isListening():
            return True

        server_name = f"setup_manager_work_editor_{uuid.uuid4().hex}"
        server = QLocalServer(self)
        if not server.listen(server_name):
            QLocalServer.removeServer(server_name)
            if not server.listen(server_name):
                self._show_warning(
                    self._t("work_editor.selector.callback_unavailable.title", "Selection callback unavailable"),
                    self._t(
                        "work_editor.selector.callback_unavailable.body",
                        "Could not start the local selection callback server for Tool Library.",
                    ),
                )
                return False
        server.newConnection.connect(self._handle_callback_connections)
        self._callback_server = server
        self._callback_server_name = server_name
        return True

    def shutdown(self) -> None:
        self._pending_requests.clear()
        if self._callback_server is None:
            return
        server_name = self._callback_server_name
        try:
            self._callback_server.close()
        except Exception:
            pass
        self._callback_server.deleteLater()
        self._callback_server = None
        self._callback_server_name = ""
        if server_name:
            try:
                QLocalServer.removeServer(server_name)
            except Exception:
                pass

    def open_session(
        self,
        *,
        kind: str,
        head: str | None = None,
        spindle: str | None = None,
        follow_up: dict | None = None,
        initial_assignments: list[dict] | None = None,
    ) -> bool:
        selector_kind = "jaws" if str(kind or "").strip().lower() == "jaws" else "tools"
        if not self.ensure_server():
            return False

        request_id = uuid.uuid4().hex
        normalized_head = self._normalize_head(head) if head else ""
        normalized_spindle = self._normalize_spindle(spindle or self._default_spindle())
        payload = {
            "show": True,
            "module": selector_kind,
            "selector_mode": selector_kind,
            "selector_callback_server": self._callback_server_name,
            "selector_request_id": request_id,
        }
        if normalized_head:
            payload["selector_head"] = normalized_head
        if normalized_spindle:
            payload["selector_spindle"] = normalized_spindle
        if selector_kind == "tools" and isinstance(initial_assignments, list):
            payload["current_assignments"] = [dict(item) for item in initial_assignments if isinstance(item, dict)]
            # Tool Library may switch heads/spindles during a selector session,
            # so we send every bucket up front instead of only the active one.
            payload["current_assignments_by_target"] = self._initial_tool_assignment_buckets()

        self._pending_requests[request_id] = {
            "request_id": request_id,
            "kind": selector_kind,
            "head": normalized_head,
            "spindle": normalized_spindle,
            "follow_up": dict(follow_up) if isinstance(follow_up, dict) else None,
        }

        if self._send_to_tool_library(payload):
            return True

        if not self._launch_tool_library(["--hidden"]):
            self._pending_requests.pop(request_id, None)
            self._show_warning(
                self._t("work_editor.selector.library_unavailable.title", "Tool Library unavailable"),
                self._t(
                    "work_editor.selector.library_unavailable.body",
                    "Could not find a launchable Tool Library executable or source entry point.",
                ),
            )
            return False

        self._retry_selector_request_send(request_id, payload)
        return True

    def _handle_callback_connections(self) -> None:
        server = self._callback_server
        if server is None:
            return
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if socket is None:
                continue
            socket._selector_buffer = b""
            socket._selector_processed = False
            socket.readyRead.connect(lambda sock=socket: self._consume_callback_socket(sock))
            socket.disconnected.connect(lambda sock=socket: self._consume_callback_socket(sock, finalize=True))
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable() > 0:
                self._consume_callback_socket(socket)

    def _consume_callback_socket(self, socket: QLocalSocket, finalize: bool = False) -> None:
        if socket is None:
            return
        try:
            socket._selector_buffer += bytes(socket.readAll())
        except Exception:
            socket._selector_buffer = getattr(socket, "_selector_buffer", b"")

        if getattr(socket, "_selector_processed", False):
            return

        raw = bytes(getattr(socket, "_selector_buffer", b"")).decode("utf-8", errors="ignore").strip()
        if not raw:
            if finalize:
                self._show_warning(
                    self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                    self._t(
                        "work_editor.selector.malformed_callback.body",
                        "Tool Library returned an empty selection callback payload.",
                    ),
                )
            return

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            if finalize:
                self._show_warning(
                    self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                    self._t(
                        "work_editor.selector.malformed_callback.body",
                        "Tool Library returned an invalid selection callback payload.",
                    ),
                )
            return

        socket._selector_processed = True
        self._handle_callback_payload(payload)

    def _handle_callback_payload(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            self._show_warning(
                self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                self._t(
                    "work_editor.selector.malformed_callback.body",
                    "Tool Library returned an invalid selection callback payload.",
                ),
            )
            return

        if str(payload.get("command") or "").strip() != "selector_result":
            self._show_warning(
                self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                self._t(
                    "work_editor.selector.malformed_callback.body",
                    "Tool Library returned an invalid selection callback payload.",
                ),
            )
            return

        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            self._show_warning(
                self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                self._t(
                    "work_editor.selector.malformed_callback.body",
                    "Tool Library returned a selection callback without a request ID.",
                ),
            )
            return

        request = self._pending_requests.pop(request_id, None)
        if request is None:
            return

        kind = str(payload.get("kind") or request.get("kind") or "").strip().lower()
        handled = False
        if kind == "tools":
            selected_items = payload.get("tools")
            if not isinstance(selected_items, list):
                selected_items = payload.get("selected_items")
            if not isinstance(selected_items, list):
                self._show_warning(
                    self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                    self._t(
                        "work_editor.selector.malformed_callback.body",
                        "Tool Library returned an invalid tool selection payload.",
                    ),
                )
                return
            effective_request = dict(request)
            payload_head = self._normalize_head(payload.get("selector_head"))
            if payload_head:
                effective_request["head"] = payload_head
            payload_spindle = self._normalize_spindle(payload.get("selector_spindle"))
            if payload_spindle:
                effective_request["spindle"] = payload_spindle
            handled = self._apply_tool_result(effective_request, selected_items)
        elif kind == "jaws":
            selected_items = payload.get("jaws")
            if not isinstance(selected_items, list):
                selected_items = payload.get("selected_items")
            if not isinstance(selected_items, list):
                self._show_warning(
                    self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                    self._t(
                        "work_editor.selector.malformed_callback.body",
                        "Tool Library returned an invalid jaw selection payload.",
                    ),
                )
                return
            handled = self._apply_jaw_result(request, selected_items)
        else:
            self._show_warning(
                self._t("work_editor.selector.malformed_callback.title", "Selection callback failed"),
                self._t(
                    "work_editor.selector.malformed_callback.body",
                    "Tool Library returned an unsupported selection callback kind.",
                ),
            )
            return

        follow_up = request.get("follow_up")
        if handled and isinstance(follow_up, dict) and follow_up.get("kind") == "jaws":
            # Combined tool->jaw flows are staged as separate selector sessions
            # to keep the library app protocol backward compatible.
            self._open_jaw_selector(follow_up.get("spindle"))

    def _send_to_tool_library(self, payload: dict) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self._tool_library_server_name)
        if not socket.waitForConnected(300):
            return False
        try:
            socket.write(json.dumps(payload).encode("utf-8"))
            socket.flush()
            return socket.waitForBytesWritten(300)
        except Exception:
            return False
        finally:
            socket.disconnectFromServer()

    def _launch_tool_library(self, extra_args: list[str] | None = None) -> bool:
        args = list(extra_args or [])

        def _is_safe_exe_target(exe_path: Path) -> bool:
            try:
                resolved = exe_path.resolve()
                current = Path(sys.executable).resolve()
            except Exception:
                return False
            if not resolved.exists() or resolved == current:
                return False
            return "tool library" in resolved.name.lower()

        if self._tool_library_main_path.exists() and not getattr(sys, "frozen", False):
            candidates = [str(Path(sys.executable))]
            python_cmd = shutil.which("python")
            if python_cmd:
                candidates.append(python_cmd)
            py_launcher = shutil.which("py")
            if py_launcher:
                candidates.append(py_launcher)

            for candidate in candidates:
                cmd_args = [str(self._tool_library_main_path)] + args
                candidate_name = Path(candidate).name.lower()
                if candidate_name in {"py.exe", "py"}:
                    cmd_args = ["-3", str(self._tool_library_main_path)] + args
                if QProcess.startDetached(candidate, cmd_args, str(self._tool_library_project_dir)):
                    return True

        for exe_path in self._tool_library_exe_candidates:
            if _is_safe_exe_target(exe_path):
                if QProcess.startDetached(str(exe_path), args, str(exe_path.parent)):
                    return True
        return False

    def _retry_selector_request_send(
        self,
        request_id: str,
        payload: dict,
        attempts_remaining: int = 12,
        delay_ms: int = 250,
    ) -> None:
        if request_id not in self._pending_requests:
            return
        if self._send_to_tool_library(payload):
            return
        if attempts_remaining <= 1:
            self._pending_requests.pop(request_id, None)
            self._show_warning(
                self._t("work_editor.selector.library_unavailable.title", "Tool Library unavailable"),
                self._t(
                    "work_editor.selector.library_unavailable.body",
                    "Could not connect to Tool Library for selection.",
                ),
            )
            return
        QTimer.singleShot(
            delay_ms,
            lambda rid=request_id, data=dict(payload), remaining=attempts_remaining - 1: self._retry_selector_request_send(
                rid,
                data,
                remaining,
                delay_ms,
            ),
        )

"""Selector session controller for the Work Editor.

Owns all selector-related state and logic that was previously spread across
WorkEditorDialog.  Delegates session state tracking to the existing
SelectorSessionCoordinator (pure-logic state machine).

Public API
----------
open_tools(head, spindle, initial_assignments, initial_buckets)
open_jaws(spindle)
open_fixtures(operation_key)
receive_ipc_result(payload)
force_shutdown()
is_busy -> bool
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from uuid import uuid4

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from shared.selector.payloads import (
    JawSelectionPayload,
    SelectionBatch,
    SpindleKey,
    ToolBucket,
    ToolSelectionPayload,
)
from ui.work_editor_support.selector_adapter import (
    apply_fixture_selector_result,
    apply_jaw_selector_result,
    apply_tool_selector_result,
)
from ui.work_editor_support.selector_provider import (
    build_fixture_selector_request,
    build_initial_jaw_assignments,
    build_jaw_selector_request,
    build_tool_selector_request,
)
from ui.work_editor_support.selector_parity_factory import (
    build_embedded_selector_parity_widget,
    dispose_embedded_selector_runtime,
)
from ui.work_editor_support.selectors import (
    normalize_selector_head,
    normalize_selector_spindle,
    selector_initial_tool_assignments,
    selector_initial_tool_assignment_buckets,
)
from ui.work_editor_support.selector_state import selector_target_ordered_list

from config import (
    WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND,
    WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE,
    WORK_EDITOR_SELECTOR_TRACE_PAINT,
)

from services.selector_session import SelectorSessionCoordinator, make_file_trace_listener

from PySide6.QtCore import QEvent

_log = logging.getLogger(__name__)

_SELECTOR_TRACE_EVENT_NAMES = {
    QEvent.Show: "Show",
    QEvent.Hide: "Hide",
    QEvent.Paint: "Paint",
    QEvent.UpdateRequest: "UpdateRequest",
    QEvent.Resize: "Resize",
    QEvent.LayoutRequest: "LayoutRequest",
}


class WorkEditorSelectorController:
    """Encapsulates all selector session logic for the Work Editor dialog.

    Holds selector state attributes, manages session lifecycle via
    SelectorSessionCoordinator, and drives UI mode transitions on the
    dialog through a stored reference.
    """

    def __init__(self, dialog, *, coordinator: SelectorSessionCoordinator | None = None) -> None:
        self._dialog = dialog

        # Wire file-based trace listener for coordinator transitions
        trace_path = self._resolve_trace_path()
        trace_listener = make_file_trace_listener(trace_path) if trace_path else None
        self._coordinator = coordinator or SelectorSessionCoordinator(
            name="work_editor", trace_listener=trace_listener,
        )

        # Transport mode
        self._transport_mode = self._resolve_transport_mode()

        # UI mode state
        self._mode_active = False
        self._open_requested = False
        self._restore_state: dict | None = None
        self._hidden_editor_widgets: list[QWidget] = []

        # Transition shield
        self._transition_shield_pending_hide = False

        # Diagnostic trace
        self._trace_widgets: dict[int, tuple[str, QWidget]] = {}

        # Embedded selector widget
        self._active_embedded_widget: QWidget | None = None

        # IPC state
        self._pending_ipc_request_id: str | None = None
        self._pending_ipc_kind: str | None = None
        self._ipc_saved_geometry = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_busy(self) -> bool:
        return self._coordinator.is_busy or self._mode_active

    @property
    def mode_active(self) -> bool:
        return self._mode_active

    @property
    def session_phase(self) -> str:
        return self._coordinator.state.value

    @property
    def session_id(self):
        return self._coordinator.session_id

    def open_tools(
        self,
        initial_head: str | None = None,
        initial_spindle: str | None = None,
        initial_assignments: list[dict] | None = None,
    ) -> bool:
        dialog = self._dialog
        if hasattr(dialog, '_sync_mc_tools_operation_payload'):
            try:
                dialog._sync_mc_tools_operation_payload()
            except Exception:
                pass
        request = build_tool_selector_request(
            dialog,
            initial_head=initial_head,
            initial_spindle=initial_spindle,
            initial_assignments=initial_assignments,
        )
        self._log("open", kind="tools", head=request.get("head"), spindle=request.get("spindle"))
        return self._open_selector_request(
            kind=str(request.get("kind") or "tools"),
            head=str(request.get("head") or ""),
            spindle=str(request.get("spindle") or ""),
            initial_assignments=list(request.get("initial_assignments") or []),
            initial_assignment_buckets=dict(request.get("initial_assignment_buckets") or {}),
        )

    def open_tools_for_bucket(self, head_key: str, spindle: str) -> bool:
        target_head = normalize_selector_head(head_key)
        ordered_list = selector_target_ordered_list(self._dialog, target_head)
        assignments = selector_initial_tool_assignments(ordered_list, spindle)
        return self.open_tools(
            initial_head=head_key,
            initial_spindle=spindle,
            initial_assignments=assignments,
        )

    def open_jaws(self, initial_spindle: str | None = None) -> bool:
        request = build_jaw_selector_request(self._dialog, initial_spindle=initial_spindle)
        self._log("open", kind="jaws", spindle=request.get("spindle"))
        return self._open_selector_request(
            kind=str(request.get("kind") or "jaws"),
            spindle=str(request.get("spindle") or ""),
            initial_assignments=list(request.get("initial_assignments") or []),
        )

    def open_fixtures(self, operation_key: str | None = None) -> bool:
        request = build_fixture_selector_request(self._dialog, operation_key=operation_key)
        target_key = str((request.get("follow_up") or {}).get("target_key") or "").strip()
        self._log("open", kind="fixtures", target_key=target_key)
        return self._open_selector_request(
            kind="fixtures",
            target_key=target_key,
            initial_assignments=list(request.get("initial_assignments") or []),
            initial_assignment_buckets=dict(request.get("initial_assignment_buckets") or {}),
        )

    def receive_ipc_result(self, payload: dict) -> None:
        """Called by SM's IPC handler when Library sends back selector_result."""
        kind = str(payload.get("kind") or "")
        with self._trace("ipc_result.receive", kind=kind):
            self._pending_ipc_request_id = None
            self._pending_ipc_kind = None

            request = {
                "head": str(payload.get("selector_head") or ""),
                "spindle": str(payload.get("selector_spindle") or ""),
                "target_key": str(payload.get("target_key") or ""),
                "assignment_buckets_by_target": dict(payload.get("assignment_buckets_by_target") or {}),
                "print_pots": bool(payload.get("print_pots", False)),
            }
            result_payload = {
                "kind": kind,
                "selected_items": list(payload.get("selected_items") or payload.get("items") or []),
                "selector_head": request["head"],
                "selector_spindle": request["spindle"],
                "target_key": request["target_key"],
                "assignment_buckets_by_target": request["assignment_buckets_by_target"],
                "print_pots": request["print_pots"],
            }

            self._apply_selector_result(request, result_payload)
            dialog = self._dialog
            saved_geo = self._ipc_saved_geometry
            if saved_geo is not None:
                dialog.setGeometry(saved_geo)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

    def restore_if_waiting(self) -> None:
        """Show dialog if hidden waiting for IPC result (cancel path)."""
        dialog = self._dialog
        if dialog.isVisible():
            return
        if self._pending_ipc_request_id is None:
            return
        self._pending_ipc_request_id = None
        self._pending_ipc_kind = None
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def force_shutdown(self) -> None:
        """Force-close any active session. Safe to call from closeEvent."""
        with self._trace("force_shutdown"):
            self._coordinator.force_shutdown()
            self._detach_active_embedded_widget()
            dispose_embedded_selector_runtime(self._dialog)
            self._mode_active = False
            self._open_requested = False
            self._pending_ipc_request_id = None
            self._pending_ipc_kind = None

    def reset_for_reuse(self) -> None:
        """Reset controller state when the dialog is reused for a new work."""
        if self._coordinator.is_busy:
            self._coordinator.force_shutdown()
        self._mode_active = False
        self._open_requested = False
        self._pending_ipc_request_id = None
        self._pending_ipc_kind = None
        self._ipc_saved_geometry = None
        self._restore_state = None

    # ------------------------------------------------------------------
    # Transport resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_transport_mode() -> str:
        return "ipc"

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_trace_path() -> str:
        """Return path for the selector session trace log file."""
        try:
            from config import SOURCE_DIR
            from pathlib import Path
            return str(Path(SOURCE_DIR) / "temp" / "selector_session_trace.log")
        except Exception:
            return ""

    def _log(self, event: str, **fields) -> None:
        payload = {"event": event, "transport": self._transport_mode}
        payload.update({k: v for k, v in fields.items() if v not in (None, "")})
        _log.info("work_editor.selector %s", payload, extra={"selector": payload})

    @contextmanager
    def _trace(self, event: str, **fields):
        """Context manager that logs begin/end with duration for a scoped operation."""
        t0 = time.monotonic()
        self._log(f"{event}.begin", **fields)
        try:
            yield
        finally:
            duration_ms = int((time.monotonic() - t0) * 1000)
            self._log(f"{event}.end", duration_ms=duration_ms, **fields)

    # ------------------------------------------------------------------
    # Overlay / shield geometry
    # ------------------------------------------------------------------

    def _host_uses_overlay_mode(self) -> bool:
        mode = str(WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE or "").strip().lower()
        return mode == "overlay"

    def _current_mount_container(self) -> QWidget:
        dialog = self._dialog
        if self._host_uses_overlay_mode():
            return dialog._selector_overlay_mount_container
        return dialog._selector_mount_container

    def _sync_overlay_geometry(self) -> None:
        dialog = self._dialog
        overlay = getattr(dialog, "_selector_overlay_container", None)
        normal_page = getattr(dialog, "_normal_page", None)
        if not isinstance(overlay, QWidget) or not isinstance(normal_page, QWidget):
            return
        overlay.setGeometry(normal_page.rect())
        overlay.raise_()

    def _set_overlay_visible(self, visible: bool) -> None:
        dialog = self._dialog
        overlay = getattr(dialog, "_selector_overlay_container", None)
        if not isinstance(overlay, QWidget):
            return
        self._sync_overlay_geometry()
        overlay.setVisible(bool(visible))
        if visible:
            overlay.raise_()

    def _set_normal_surface_hidden(self, hidden: bool) -> None:
        dialog = self._dialog
        widgets: list[QWidget] = []
        tabs = getattr(dialog, "tabs", None)
        if isinstance(tabs, QWidget):
            widgets.append(tabs)
        dialog_buttons = getattr(dialog, "_dialog_buttons", None)
        if isinstance(dialog_buttons, QWidget):
            widgets.append(dialog_buttons)

        if hidden:
            retained: list[QWidget] = []
            for w in widgets:
                if not w.isHidden():
                    w.setVisible(False)
                    retained.append(w)
            self._hidden_editor_widgets = retained
            return

        for w in self._hidden_editor_widgets:
            if isinstance(w, QWidget):
                w.setVisible(True)
        self._hidden_editor_widgets = []

    def _uses_transition_shield(self) -> bool:
        return self._host_uses_overlay_mode()

    def _sync_shield_geometry(self) -> None:
        dialog = self._dialog
        shield = getattr(dialog, "_selector_transition_shield", None)
        root_stack = getattr(dialog, "_root_stack", None)
        if not isinstance(shield, QWidget) or not isinstance(root_stack, QWidget):
            return
        shield.setGeometry(root_stack.geometry())
        shield.raise_()

    def _hide_shield(self) -> None:
        dialog = self._dialog
        shield = getattr(dialog, "_selector_transition_shield", None)
        if not isinstance(shield, QWidget):
            return
        self._transition_shield_pending_hide = False
        shield.setVisible(False)

    def _set_shield_visible(self, visible: bool) -> None:
        dialog = self._dialog
        shield = getattr(dialog, "_selector_transition_shield", None)
        if not isinstance(shield, QWidget):
            return
        self._sync_shield_geometry()
        if visible:
            self._transition_shield_pending_hide = True
            shield.setVisible(True)
            shield.raise_()
            return
        self._hide_shield()

    # ------------------------------------------------------------------
    # Diagnostic trace filters
    # ------------------------------------------------------------------

    def install_trace_filters(self) -> None:
        if not WORK_EDITOR_SELECTOR_TRACE_PAINT:
            self._trace_widgets = {}
            return
        dialog = self._dialog
        trace_targets = {
            "dialog": dialog,
            "root_stack": getattr(dialog, "_root_stack", None),
            "normal_page": getattr(dialog, "_normal_page", None),
            "selector_page": getattr(dialog, "_selector_page", None),
            "selector_mount_container": getattr(dialog, "_selector_mount_container", None),
            "selector_overlay_container": getattr(dialog, "_selector_overlay_container", None),
            "selector_overlay_mount_container": getattr(dialog, "_selector_overlay_mount_container", None),
            "selector_transition_shield": getattr(dialog, "_selector_transition_shield", None),
        }
        watched: dict[int, tuple[str, QWidget]] = {}
        for label, widget in trace_targets.items():
            if not isinstance(widget, QWidget):
                continue
            widget.installEventFilter(dialog)
            watched[id(widget)] = (label, widget)
        self._trace_widgets = watched
        self._log(
            "trace.enabled",
            diagnostic_kind=WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND,
            host_diagnostic_mode=WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE,
            targets=list(trace_targets.keys()),
        )

    def trace_surface_event(self, obj, event) -> None:
        if not WORK_EDITOR_SELECTOR_TRACE_PAINT:
            return
        entry = self._trace_widgets.get(id(obj))
        if entry is None:
            return
        event_name = _SELECTOR_TRACE_EVENT_NAMES.get(event.type())
        if event_name is None:
            return
        label, widget = entry
        geometry = widget.geometry()
        dialog = self._dialog
        self._log(
            "surface.event",
            watched=label,
            qt_event=event_name,
            visible=bool(widget.isVisible()),
            updates_enabled=bool(widget.updatesEnabled()),
            current_page=(
                "overlay"
                if self._host_uses_overlay_mode()
                and getattr(dialog, "_selector_overlay_container", None) is not None
                and dialog._selector_overlay_container.isVisible()
                else "selector"
                if getattr(dialog, "_root_stack", None) is not None
                and getattr(dialog, "_selector_page", None) is not None
                and dialog._root_stack.currentWidget() is dialog._selector_page
                else "normal"
            ),
            x=geometry.x(),
            y=geometry.y(),
            width=geometry.width(),
            height=geometry.height(),
        )

    # ------------------------------------------------------------------
    # Enter / exit selector mode
    # ------------------------------------------------------------------

    def _enter_mode(self) -> None:
        dialog = self._dialog
        if self._mode_active:
            return
        if not isinstance(getattr(dialog, "_root_stack", None), QStackedWidget):
            return
        if not self._open_requested:
            _log.warning("work_editor.selector_mode ignored because no selector request is active")
            return

        with self._trace(
            "selector_mode.enter",
            session_id=str(self._coordinator.session_id or ""),
            host_diagnostic_mode=WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE,
        ):
            was_enabled = dialog.updatesEnabled()
            if was_enabled:
                dialog.setUpdatesEnabled(False)
            try:
                self._restore_state = self._capture_restore_state()
                self._mode_active = True
                if self._uses_transition_shield():
                    self._set_shield_visible(True)
                if self._host_uses_overlay_mode():
                    self._set_normal_surface_hidden(True)
                    self._set_overlay_visible(True)
                else:
                    dialog._root_stack.setCurrentWidget(dialog._selector_page)
                if dialog._RESIZE_FOR_SELECTOR_MODE:
                    self._expand_for_mode()
            finally:
                if was_enabled:
                    dialog.setUpdatesEnabled(True)
        if self._transition_shield_pending_hide:
            QTimer.singleShot(dialog._SELECTOR_TRANSITION_SHIELD_DELAY_MS, self._hide_shield)

    def _exit_mode(self) -> None:
        dialog = self._dialog

        with self._trace(
            "selector_mode.exit",
            session_id=str(self._coordinator.session_id or ""),
            current_page="overlay" if self._host_uses_overlay_mode() else "selector",
        ):
            was_enabled = dialog.updatesEnabled()
            if was_enabled:
                dialog.setUpdatesEnabled(False)
            try:
                if self._mode_active and isinstance(getattr(dialog, "_root_stack", None), QStackedWidget):
                    if self._host_uses_overlay_mode():
                        self._set_overlay_visible(False)
                        self._set_normal_surface_hidden(False)
                    else:
                        dialog._root_stack.setCurrentWidget(dialog._normal_page)
                    if self._uses_transition_shield():
                        self._set_shield_visible(False)

                if self._mode_active:
                    self._restore_from_state()
                self._restore_state = None
                self._mode_active = False
                self._open_requested = False
            finally:
                if was_enabled:
                    dialog.setUpdatesEnabled(True)

    def _expand_for_mode(self) -> None:
        dialog = self._dialog
        target_width = max(dialog.width() + dialog._SELECTOR_EXPAND_DELTA, dialog._SELECTOR_MIN_WIDTH)
        screen = dialog.screen()
        available = screen.availableGeometry() if screen is not None else None
        if available is not None:
            target_width = min(target_width, available.width())

        target_height = dialog.height()
        if available is not None:
            target_height = min(target_height, available.height())

        dialog.resize(target_width, target_height)
        if available is not None:
            geom = dialog.geometry()
            x = min(max(geom.x(), available.left()), available.right() - geom.width() + 1)
            y = min(max(geom.y(), available.top()), available.bottom() - geom.height() + 1)
            dialog.move(x, y)

    def _capture_restore_state(self) -> dict:
        dialog = self._dialog
        return {
            "geometry": dialog.geometry(),
            "minimum_size": dialog.minimumSize(),
            "maximum_size": dialog.maximumSize(),
        }

    def _restore_from_state(self) -> None:
        state = self._restore_state
        if not isinstance(state, dict):
            return
        dialog = self._dialog
        min_size = state.get("minimum_size")
        if isinstance(min_size, QSize):
            dialog.setMinimumSize(min_size)
        max_size = state.get("maximum_size")
        if isinstance(max_size, QSize):
            dialog.setMaximumSize(max_size)
        geometry = state.get("geometry")
        if geometry is not None:
            dialog.setGeometry(geometry)

    # ------------------------------------------------------------------
    # Request dispatch
    # ------------------------------------------------------------------

    def _open_selector_request(
        self,
        *,
        kind: str,
        head: str = "",
        spindle: str = "",
        target_key: str = "",
        initial_assignments: list[dict] | None = None,
        initial_assignment_buckets: dict[str, list[dict]] | None = None,
    ) -> bool:
        prefer_ipc = str(self._transport_mode or "").strip().lower() == "ipc"
        if prefer_ipc:
            return self._try_open_via_ipc(
                kind=kind,
                head=head,
                spindle=spindle,
                target_key=target_key,
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
            )
        return self._try_open_embedded(
            kind=kind,
            head=head,
            spindle=spindle,
            target_key=target_key,
            initial_assignments=initial_assignments,
            initial_assignment_buckets=initial_assignment_buckets,
        )

    def _build_session_geometry(self) -> str:
        dialog = self._dialog
        try:
            geometry = dialog.geometry()
            target_width = max(
                int(geometry.width()) + dialog._SELECTOR_DIALOG_WIDTH_PAD,
                dialog._SELECTOR_DIALOG_DEFAULT_WIDTH,
            )
            target_height = max(
                int(geometry.height()) + dialog._SELECTOR_DIALOG_HEIGHT_PAD,
                dialog._SELECTOR_DIALOG_DEFAULT_HEIGHT,
            )

            screen = dialog.screen()
            available = screen.availableGeometry() if screen is not None else None
            if available is not None:
                target_width = min(target_width, available.width())
                target_height = min(target_height, available.height())
                target_x = int(geometry.x()) - max(0, (target_width - int(geometry.width())) // 2)
                target_y = int(geometry.y()) - max(0, (target_height - int(geometry.height())) // 2)
                max_x = available.x() + max(0, available.width() - target_width)
                max_y = available.y() + max(0, available.height() - target_height)
                target_x = max(available.x(), min(target_x, max_x))
                target_y = max(available.y(), min(target_y, max_y))
            else:
                target_x = int(geometry.x()) - max(0, (target_width - int(geometry.width())) // 2)
                target_y = int(geometry.y()) - max(0, (target_height - int(geometry.height())) // 2)

            return f"{target_x},{target_y},{target_width},{target_height}"
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Embedded transport
    # ------------------------------------------------------------------

    def _clear_mount_container(self) -> None:
        mount = self._current_mount_container()
        layout = mount.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is None:
                continue
            child.hide()
            child.setParent(None)

    def _detach_active_embedded_widget(self) -> None:
        widget = self._active_embedded_widget
        self._active_embedded_widget = None
        self._clear_mount_container()
        if not isinstance(widget, QWidget):
            return
        if bool(getattr(widget, "_reuse_cached_selector_widget", False)):
            return
        try:
            widget.deleteLater()
        except Exception:
            pass

    def _try_open_embedded(
        self,
        *,
        kind: str,
        head: str = "",
        spindle: str = "",
        target_key: str = "",
        initial_assignments: list | None = None,
        initial_assignment_buckets: dict | None = None,
    ) -> bool:
        kind_key = str(kind or "").strip().lower()
        if kind_key not in {"tools", "jaws", "fixtures"}:
            return False

        if self._coordinator.is_busy:
            _log.warning(
                "work_editor.selector request ignored while session is active kind=%s state=%s",
                kind_key, self._coordinator.state.value,
            )
            return False

        session_id = self._coordinator.request_open(caller=f"embedded.{kind_key}")
        self._open_requested = True

        request = {
            "kind": kind_key,
            "head": head,
            "spindle": spindle,
            "target_key": target_key,
            "assignment_buckets_by_target": dict(initial_assignment_buckets or {}),
        }

        def _on_submit(payload: dict) -> None:
            try:
                self._coordinator.mark_mount_complete(caller="embedded.submit_premount")
            except Exception:
                pass
            try:
                batch = self._build_selection_batch(request, payload)
                self._coordinator.confirm(batch, caller="embedded.submit")
            except Exception:
                _log.debug("coordinator confirm failed, applying directly", exc_info=True)
            try:
                self._apply_selector_result(request, payload)
            finally:
                self._detach_active_embedded_widget()
                self._exit_mode()
                try:
                    self._coordinator.mark_teardown_complete(caller="embedded.submit.teardown")
                except Exception:
                    pass

        def _on_cancel() -> None:
            try:
                self._coordinator.cancel(caller="embedded.cancel")
            except Exception:
                pass
            self._detach_active_embedded_widget()
            self._exit_mode()
            self._log("cancel.embedded.request")
            try:
                self._coordinator.mark_teardown_complete(caller="embedded.cancel.teardown")
            except Exception:
                pass

        try:
            mount = self._current_mount_container()
            self._detach_active_embedded_widget()
            dialog = self._dialog
            widget = build_embedded_selector_parity_widget(
                dialog,
                mount_container=mount,
                kind=kind_key,
                head=head,
                spindle=spindle,
                follow_up={"target_key": target_key},
                initial_assignments=[dict(item) for item in (initial_assignments or []) if isinstance(item, dict)],
                initial_assignment_buckets={
                    str(k): [dict(item) for item in v if isinstance(item, dict)]
                    for k, v in dict(initial_assignment_buckets or {}).items()
                    if isinstance(v, list)
                },
                on_submit=_on_submit,
                on_cancel=_on_cancel,
            )
            layout = mount.layout()
            if layout is None:
                layout = QHBoxLayout(mount)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(0)
            layout.addWidget(widget)
            self._active_embedded_widget = widget

            self._coordinator.mark_mount_complete(caller="embedded.mounted")
            self._enter_mode()
            widget.show()
            widget.raise_()
            widget.activateWindow()
            self._log("open.embedded.ready", kind=kind_key, session_id=str(session_id))
            return True
        except Exception:
            _log.exception("work_editor.selector embedded open failed kind=%s", kind_key)
            self._detach_active_embedded_widget()
            self._exit_mode()
            try:
                self._coordinator.force_shutdown()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # IPC transport
    # ------------------------------------------------------------------

    def _try_open_via_ipc(
        self,
        *,
        kind: str,
        head: str = "",
        spindle: str = "",
        target_key: str = "",
        initial_assignments: list | None = None,
        initial_assignment_buckets: dict | None = None,
    ) -> bool:
        if kind not in {"tools", "jaws", "fixtures"}:
            return False
        try:
            from ui.main_window_support.library_ipc import (
                allow_set_foreground,
                is_tool_library_ready,
                launch_tool_library,
                send_request_with_retry,
                send_to_tool_library,
            )
            from config import (
                SETUP_MANAGER_SERVER_NAME,
                TOOL_LIBRARY_EXE_CANDIDATES,
                TOOL_LIBRARY_MAIN_PATH,
                TOOL_LIBRARY_PROJECT_DIR,
                TOOL_LIBRARY_READY_PATH,
                TOOL_LIBRARY_SERVER_NAME,
            )
        except Exception:
            return False

        dialog = self._dialog
        try:
            geometry_str = self._build_session_geometry()
        except Exception:
            geometry_str = ""

        machine_profile_key = str(getattr(dialog, "_machine_profile_key", "") or "")

        request_id = str(uuid4())
        payload = {
            "selector_mode": kind,
            "show": True,
            "selector_callback_server": SETUP_MANAGER_SERVER_NAME,
            "selector_request_id": request_id,
            "selector_head": head,
            "selector_spindle": spindle,
            "target_key": target_key,
            "current_assignments": list(initial_assignments or []),
            "current_assignments_by_target": dict(initial_assignment_buckets or {}),
            "print_pots": bool(
                kind == "tools"
                and getattr(dialog, "print_pots_checkbox", None)
                and dialog.print_pots_checkbox.isChecked()
            ),
            "machine_profile_key": machine_profile_key,
            "geometry": geometry_str,
        }

        def _selector_request_failed() -> None:
            self._pending_ipc_request_id = None
            self._pending_ipc_kind = None
            saved_geometry = self._ipc_saved_geometry
            if saved_geometry is not None:
                dialog.setGeometry(saved_geometry)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            QMessageBox.warning(
                dialog,
                dialog._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
                dialog._t(
                    "setup_manager.library_unavailable.start_timeout",
                    "Tool Library started but did not become ready in time. Please try again.",
                ),
            )

        allow_set_foreground()

        self._pending_ipc_request_id = request_id
        self._pending_ipc_kind = kind
        self._ipc_saved_geometry = dialog.geometry()

        sent = send_to_tool_library(TOOL_LIBRARY_SERVER_NAME, payload)
        if sent:
            self._log("open.ipc.sent", kind=kind, request_id=request_id)
            dialog.hide()
            return True

        launched = launch_tool_library(
            TOOL_LIBRARY_MAIN_PATH,
            TOOL_LIBRARY_EXE_CANDIDATES,
            TOOL_LIBRARY_PROJECT_DIR,
            extra_args=["--hidden"],
            ready_path=TOOL_LIBRARY_READY_PATH,
        )
        if launched:
            self._log("open.ipc.launching", kind=kind, request_id=request_id)
            dialog.hide()
            send_request_with_retry(
                lambda request_payload: send_to_tool_library(TOOL_LIBRARY_SERVER_NAME, request_payload),
                payload,
                on_success=lambda: self._log("open.ipc.sent", kind=kind, request_id=request_id),
                on_failed=_selector_request_failed,
                ready_check=lambda: is_tool_library_ready(TOOL_LIBRARY_SERVER_NAME, TOOL_LIBRARY_READY_PATH),
            )
            return True

        self._log("open.ipc.failed", kind=kind)
        self._pending_ipc_request_id = None
        self._pending_ipc_kind = None
        self._ipc_saved_geometry = None
        QMessageBox.warning(
            dialog,
            dialog._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
            dialog._t(
                "setup_manager.library_unavailable.body",
                "Could not find a launchable Tool Library executable or source entry point.",
            ),
        )
        return False

    # ------------------------------------------------------------------
    # Result routing
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_bucket_for_spindle(spindle: str) -> ToolBucket:
        return ToolBucket.SUB if normalize_selector_spindle(spindle) == "sub" else ToolBucket.MAIN

    def _build_selection_batch(self, request: dict, payload: dict) -> SelectionBatch:
        session_uuid = self._coordinator.session_id
        if session_uuid is None:
            raise RuntimeError("cannot build SelectionBatch without live session UUID")

        kind = str((payload or {}).get("kind") or request.get("kind") or "").strip().lower()
        source_rev_raw = (payload or {}).get("source_library_rev", 0)
        try:
            source_rev = max(int(source_rev_raw), 0)
        except Exception:
            source_rev = 0

        selected_items = [item for item in list((payload or {}).get("selected_items") or []) if isinstance(item, dict)]
        tool_entries: list[ToolSelectionPayload] = []
        jaw_entries: list[JawSelectionPayload] = []

        if kind == "tools":
            seen_tools: set[tuple[ToolBucket, str, str]] = set()
            buckets_by_target = (payload or {}).get("assignment_buckets_by_target")
            if isinstance(buckets_by_target, dict) and buckets_by_target:
                for raw_target, raw_bucket_items in buckets_by_target.items():
                    target = str(raw_target or "").strip()
                    if ":" not in target:
                        continue
                    head_key_raw, spindle_raw = target.split(":", 1)
                    head_key = normalize_selector_head(head_key_raw)
                    bucket = self._tool_bucket_for_spindle(spindle_raw)
                    for item in list(raw_bucket_items or []):
                        if not isinstance(item, dict):
                            continue
                        tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
                        if not tool_id:
                            continue
                        dedupe_key = (bucket, head_key, tool_id)
                        if dedupe_key in seen_tools:
                            continue
                        seen_tools.add(dedupe_key)
                        tool_entries.append(
                            ToolSelectionPayload(
                                bucket=bucket,
                                head_key=head_key,
                                tool_id=tool_id,
                                source_library_rev=source_rev,
                            )
                        )
            else:
                head_key = normalize_selector_head(request.get("head"))
                bucket = self._tool_bucket_for_spindle(str(request.get("spindle") or ""))
                for item in selected_items:
                    tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
                    if not tool_id:
                        continue
                    dedupe_key = (bucket, head_key, tool_id)
                    if dedupe_key in seen_tools:
                        continue
                    seen_tools.add(dedupe_key)
                    tool_entries.append(
                        ToolSelectionPayload(
                            bucket=bucket,
                            head_key=head_key,
                            tool_id=tool_id,
                            source_library_rev=source_rev,
                        )
                    )

        if kind == "jaws":
            default_spindle = normalize_selector_spindle(request.get("spindle"))
            seen_jaws: set[tuple[SpindleKey, str]] = set()
            for item in selected_items:
                jaw_id = str(item.get("jaw_id") or item.get("id") or "").strip()
                if not jaw_id:
                    continue
                spindle_raw = str(item.get("spindle") or item.get("slot") or default_spindle)
                spindle_key = SpindleKey.SUB if normalize_selector_spindle(spindle_raw) == "sub" else SpindleKey.MAIN
                dedupe_key = (spindle_key, jaw_id)
                if dedupe_key in seen_jaws:
                    continue
                seen_jaws.add(dedupe_key)
                jaw_entries.append(
                    JawSelectionPayload(
                        spindle=spindle_key,
                        jaw_id=jaw_id,
                        source_library_rev=source_rev,
                    )
                )

        return SelectionBatch(
            session_id=session_uuid,
            tools=tuple(tool_entries),
            jaws=tuple(jaw_entries),
        )

    def _apply_selector_result(self, request: dict, payload: dict) -> None:
        dialog = self._dialog
        kind = str((payload or {}).get("kind") or request.get("kind") or "").strip().lower()
        selected_items = list((payload or {}).get("selected_items") or [])

        selector_request = {
            "head": request.get("head") or (payload or {}).get("selector_head") or "",
            "spindle": request.get("spindle") or (payload or {}).get("selector_spindle") or "",
            "target_key": request.get("target_key") or (payload or {}).get("target_key") or "",
            "assignment_buckets_by_target": (payload or {}).get("assignment_buckets_by_target") or {},
            "print_pots": bool((payload or {}).get("print_pots", request.get("print_pots", False))),
        }

        applied = False
        if kind == "tools":
            applied = apply_tool_selector_result(dialog, selector_request, selected_items)
            if hasattr(dialog, "print_pots_checkbox"):
                dialog.print_pots_checkbox.setChecked(bool(selector_request.get("print_pots", False)))
        elif kind == "jaws":
            applied = apply_jaw_selector_result(dialog, selector_request, selected_items)
        elif kind == "fixtures":
            applied = apply_fixture_selector_result(dialog, selector_request, selected_items)

        self._log(
            "submit.applied",
            kind=kind,
            applied=bool(applied),
            selected_count=len(selected_items),
        )

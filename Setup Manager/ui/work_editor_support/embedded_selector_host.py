from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget


def _host_widget_snapshot(widget: QWidget | None) -> dict[str, Any]:
    if not isinstance(widget, QWidget):
        return {"widget_type": type(widget).__name__ if widget is not None else "None"}
    parent = widget.parentWidget()
    return {
        "widget_type": type(widget).__name__,
        "parent_type": type(parent).__name__ if parent is not None else None,
        "is_window": bool(widget.isWindow()),
        "window_type": int(widget.windowType()),
        "window_flags": int(widget.windowFlags()),
        "visible": bool(widget.isVisible()),
        "dont_show_on_screen": bool(widget.testAttribute(Qt.WA_DontShowOnScreen)),
    }


class WorkEditorSelectorHost(QObject):
    """Manage mounted selector widgets while Work Editor is in selector mode.

    This host is intentionally thin: dialog-level code owns selector lifecycle
    policy and this class only mounts/unmounts widgets.
    """

    def __init__(
        self,
        *,
        dialog: Any,
        mount_container: QWidget,
        auto_close_on_widget_signals: bool = False,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._dialog = dialog
        self._mount_container = mount_container
        self._auto_close_on_widget_signals = bool(auto_close_on_widget_signals)
        self._active_widget: QWidget | None = None

        layout = mount_container.layout()
        if layout is None:
            layout = QVBoxLayout(mount_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

    @property
    def active_widget(self) -> QWidget | None:
        return self._active_widget

    def open_widget(self, widget: QWidget, *, mount_container: QWidget | None = None) -> None:
        self.close_active_widget()
        self._active_widget = widget
        target_mount_container = mount_container or self._mount_container
        if hasattr(self._dialog, "_log_selector_event"):
            self._dialog._log_selector_event(
                "host.open.begin",
                dialog_updates_enabled=bool(getattr(self._dialog, "updatesEnabled", lambda: True)()),
                mount_container_type=type(target_mount_container).__name__,
                snapshot=_host_widget_snapshot(widget),
            )

        layout = target_mount_container.layout()
        if layout is None:
            layout = QVBoxLayout(target_mount_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        layout.addWidget(widget)
        if hasattr(self._dialog, "_log_selector_event"):
            self._dialog._log_selector_event(
                "host.open.mounted",
                dialog_updates_enabled=bool(getattr(self._dialog, "updatesEnabled", lambda: True)()),
                mount_container_type=type(target_mount_container).__name__,
                snapshot=_host_widget_snapshot(widget),
            )
        if self._auto_close_on_widget_signals:
            self._connect_selector_signals(widget)
        if hasattr(self._dialog, "_log_selector_event"):
            self._dialog._log_selector_event(
                "host.open.selector_mode_entered",
                dialog_updates_enabled=bool(getattr(self._dialog, "updatesEnabled", lambda: True)()),
                snapshot=_host_widget_snapshot(widget),
            )

    def close_active_widget(self) -> None:
        widget = self._active_widget
        if widget is None:
            return
        if hasattr(self._dialog, "_log_selector_event"):
            self._dialog._log_selector_event("host.close.begin", snapshot=_host_widget_snapshot(widget))

        try:
            preview_dialog = getattr(widget, "_detached_preview_dialog", None)
            if preview_dialog is not None:
                preview_dialog.close()
                setattr(widget, "_detached_preview_dialog", None)
        except Exception:
            if hasattr(self._dialog, "_LOGGER"):
                self._dialog._LOGGER.debug(
                    "Failed closing selector detached preview during host close",
                    exc_info=True,
                )
        for attr_name in ("_detached_preview_widget", "_detail_preview_widget", "_close_preview_shortcut"):
            try:
                child = getattr(widget, attr_name, None)
                if child is not None and hasattr(child, "deleteLater"):
                    child.deleteLater()
            except Exception:
                if hasattr(self._dialog, "_LOGGER"):
                    self._dialog._LOGGER.debug(
                        "Failed disposing selector child %s during host close",
                        attr_name,
                        exc_info=True,
                    )
            try:
                setattr(widget, attr_name, None)
            except Exception:
                pass

        parent_widget = widget.parentWidget()
        layout = parent_widget.layout() if parent_widget is not None else None
        if layout is not None:
            layout.removeWidget(widget)
        widget.setVisible(False)
        if bool(getattr(widget, "_reuse_cached_selector_widget", False)):
            widget.setParent(self._dialog, Qt.Widget)
        else:
            widget.setParent(None)
            widget.deleteLater()
        self._active_widget = None
        if hasattr(self._dialog, "_log_selector_event"):
            self._dialog._log_selector_event("host.close.detached", snapshot=_host_widget_snapshot(widget))

    def _connect_selector_signals(self, widget: QWidget) -> None:
        submitted = getattr(widget, "submitted", None)
        if submitted is not None and hasattr(submitted, "connect"):
            submitted.connect(self._on_selector_submitted)

        canceled = getattr(widget, "canceled", None)
        if canceled is not None and hasattr(canceled, "connect"):
            canceled.connect(self._on_selector_canceled)

    def _on_selector_submitted(self, _payload: dict) -> None:
        if hasattr(self._dialog, "_log_selector_event"):
            self._dialog._log_selector_event("submit.embedded")
        self.close_active_widget()

    def _on_selector_canceled(self) -> None:
        if hasattr(self._dialog, "_log_selector_event"):
            self._dialog._log_selector_event("cancel.embedded")
        self.close_active_widget()

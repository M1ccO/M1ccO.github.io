from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget


class WorkEditorSelectorHost(QObject):
    """Manage mounted selector widgets while Work Editor is in selector mode."""

    def __init__(
        self,
        *,
        dialog: Any,
        mount_container: QWidget,
        enter_selector_mode: Callable[[], None],
        exit_selector_mode: Callable[[], None],
        auto_close_on_widget_signals: bool = False,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._dialog = dialog
        self._mount_container = mount_container
        self._enter_selector_mode = enter_selector_mode
        self._exit_selector_mode = exit_selector_mode
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

    def open_widget(self, widget: QWidget) -> None:
        self.close_active_widget()
        self._active_widget = widget

        widget.setVisible(False)
        layout = self._mount_container.layout()
        layout.addWidget(widget)

        if self._auto_close_on_widget_signals:
            self._connect_selector_signals(widget)
        self._enter_selector_mode()
        widget.setVisible(True)

    def close_active_widget(self) -> None:
        widget = self._active_widget
        if widget is None:
            return

        layout = self._mount_container.layout()
        if layout is not None:
            layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()
        self._active_widget = None
        self._exit_selector_mode()

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

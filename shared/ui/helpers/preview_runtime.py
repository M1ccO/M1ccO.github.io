from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget


def _runtime_widgets(app) -> list[QWidget]:
    widgets = getattr(app, "_preview_runtime_available_widgets", None)
    if isinstance(widgets, list):
        return widgets
    widgets = []
    app._preview_runtime_available_widgets = widgets
    return widgets


def _remove_runtime_widget(app, widget: QWidget | None) -> None:
    if widget is None:
        return
    widgets = _runtime_widgets(app)
    while widget in widgets:
        widgets.remove(widget)


def _sync_runtime_state(app) -> None:
    widgets = _runtime_widgets(app)
    app._preview_runtime_ready = bool(widgets)
    app._preview_warmup_widget = widgets[0] if widgets else None


def preview_runtime_ready() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    _sync_runtime_state(app)
    return bool(getattr(app, "_preview_runtime_ready", False))


def register_preview_runtime_widget(widget: QWidget | None) -> None:
    if widget is None:
        return

    app = QApplication.instance()
    if app is None:
        return

    if bool(widget.property("_previewRuntimeRegistered")):
        if widget.parentWidget() is None and widget not in _runtime_widgets(app):
            _runtime_widgets(app).append(widget)
        _sync_runtime_state(app)
        return

    def _clear_if_current(*_args) -> None:
        _remove_runtime_widget(app, widget)
        _sync_runtime_state(app)

    widget.destroyed.connect(_clear_if_current)
    widget.setProperty("_previewRuntimeRegistered", True)
    if widget.parentWidget() is None and widget not in _runtime_widgets(app):
        _runtime_widgets(app).append(widget)
    _sync_runtime_state(app)


def claim_prewarmed_preview_widget(dialog: QDialog) -> QWidget | None:
    app = QApplication.instance()
    if app is None:
        return None

    widgets = list(_runtime_widgets(app))
    for widget in widgets:
        try:
            if widget.parentWidget() is not None:
                _remove_runtime_widget(app, widget)
                continue
        except Exception:
            _remove_runtime_widget(app, widget)
            continue

        try:
            widget.hide()
            widget.setParent(dialog, Qt.Widget)
        except Exception:
            _remove_runtime_widget(app, widget)
            continue

        try:
            clear_fn = getattr(widget, "clear", None)
            if callable(clear_fn):
                clear_fn()
        except Exception:
            pass

        _remove_runtime_widget(app, widget)
        _sync_runtime_state(app)
        return widget

    _sync_runtime_state(app)
    return None


def release_preview_runtime_widget(widget: QWidget | None) -> None:
    if widget is None:
        return

    app = QApplication.instance()
    if app is None:
        return

    try:
        widget.hide()
        if widget.parentWidget() is not None:
            widget.setParent(None)
    except Exception:
        _remove_runtime_widget(app, widget)
        _sync_runtime_state(app)
        return

    register_preview_runtime_widget(widget)
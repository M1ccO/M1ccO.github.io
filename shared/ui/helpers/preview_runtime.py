from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDialog, QWidget


def preview_runtime_ready() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return bool(getattr(app, "_preview_runtime_ready", False))


def register_preview_runtime_widget(widget: QWidget | None) -> None:
    if widget is None:
        return

    app = QApplication.instance()
    if app is None:
        return

    app._preview_warmup_widget = widget
    app._preview_runtime_ready = True

    if bool(widget.property("_previewRuntimeRegistered")):
        return

    def _clear_if_current(*_args) -> None:
        if getattr(app, "_preview_warmup_widget", None) is widget:
            app._preview_warmup_widget = None
            app._preview_runtime_ready = False

    widget.destroyed.connect(_clear_if_current)
    widget.setProperty("_previewRuntimeRegistered", True)


def claim_prewarmed_preview_widget(dialog: QDialog) -> QWidget | None:
    app = QApplication.instance()
    if app is None:
        return None

    widget = getattr(app, "_preview_warmup_widget", None)
    if widget is None:
        return None

    try:
        if widget.parentWidget() is not None:
            return None
    except Exception:
        app._preview_warmup_widget = None
        app._preview_runtime_ready = False
        return None

    try:
        widget.hide()
        widget.setParent(dialog)
    except Exception:
        app._preview_warmup_widget = None
        app._preview_runtime_ready = False
        return None

    register_preview_runtime_widget(widget)
    return widget
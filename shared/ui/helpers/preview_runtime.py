from __future__ import annotations

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget

try:
    from shared.ui.editor_launch_debug import editor_launch_debug as _eld
except Exception:
    def _eld(event, **kw): pass


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


def preview_runtime_count() -> int:
    app = QApplication.instance()
    if app is None:
        return 0
    _sync_runtime_state(app)
    return len(_runtime_widgets(app))


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
        import traceback as _tb
        _eld("preview_runtime.widget_destroyed", widget_type=type(widget).__name__, stack="".join(_tb.format_stack()[-8:-1]).replace("\n", "|"))
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

        _eld("preview_runtime.widget_claimed", widget_type=type(widget).__name__)
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

    _eld("preview_runtime.widget_released", widget_type=type(widget).__name__)
    try:
        widget.hide()
        if widget.parentWidget() is not None:
            widget.setParent(None)
    except Exception:
        _remove_runtime_widget(app, widget)
        _sync_runtime_state(app)
        return

    register_preview_runtime_widget(widget)


def _get_or_create_warmup_container(app) -> QWidget:
    """Return a persistent off-screen container whose HWND is never user-visible.

    QWebEngineView forces native-window creation on its ancestor chain when
    load() is called.  By hosting warmup widgets inside this container we
    keep the Chromium HWND under a single off-screen parent rather than
    creating a new top-level HWND per warmup widget (which Windows renders
    briefly as a flash).
    """
    container = getattr(app, "_preview_warmup_container", None)
    if isinstance(container, QWidget):
        try:
            if not container.isVisible() and container.testAttribute(Qt.WA_DontShowOnScreen):
                return container
        except Exception:
            pass
    from PySide6.QtWidgets import QVBoxLayout
    container = QWidget()
    container.setWindowFlag(Qt.Tool, True)
    container.setAttribute(Qt.WA_ShowWithoutActivating, True)
    container.setAttribute(Qt.WA_DontShowOnScreen, True)
    container.setWindowOpacity(0.0)
    container.setGeometry(-32000, -32000, 4, 4)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    # Show the container with WA_DontShowOnScreen — Qt considers it visible
    # for rendering purposes but Windows never creates a user-visible HWND.
    container.show()
    app._preview_warmup_container = container
    return container


def ensure_preview_runtime_widgets(factory, *, count: int = 1) -> list[QWidget]:
    """Create and register prewarmed preview widgets until the pool reaches ``count``.

    Warmup widgets are hosted inside a single hidden off-screen container so
    Chromium/WebEngine HWND creation never produces a user-visible window flash.
    """
    app = QApplication.instance()
    if app is None:
        return []

    widgets = _runtime_widgets(app)
    created: list[QWidget] = []
    target = max(0, int(count))
    if target <= 0:
        _sync_runtime_state(app)
        return created

    while len(widgets) < target:
        widget = factory()
        if widget is None:
            break
        _eld("preview_runtime.warmup_widget.init", widget_type=type(widget).__name__, pool_size_before=len(_runtime_widgets(app)))
        try:
            # Parent the warmup widget under the hidden container so Chromium's
            # native surface is realized under the container's HWND rather than
            # creating a new top-level HWND that Windows would flash briefly.
            container = _get_or_create_warmup_container(app)
            widget.setParent(container, Qt.Widget)
            widget.show()
        except Exception:
            pass
        ensure_fn = getattr(widget, "_ensure_web_view", None)
        if callable(ensure_fn):
            try:
                ensure_fn()
            except Exception:
                pass
        app.processEvents()
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(500)
        loop.exec()
        timer.stop()
        app.processEvents()
        _eld("preview_runtime.warmup_widget.ready", widget_type=type(widget).__name__)
        # Detach from container before registering in the pool — claim_prewarmed_preview_widget
        # checks parentWidget() is None and reparents to the dialog.
        try:
            widget.hide()
            widget.setParent(None)
        except Exception:
            pass
        register_preview_runtime_widget(widget)
        created.append(widget)
        widgets = _runtime_widgets(app)

    _sync_runtime_state(app)
    return created

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QWidget

from shared.ui.main_window_helpers import is_interactive_widget_click


def clear_active_page_selection_on_background_click(window, obj) -> None:
    if is_interactive_widget_click(obj, window):
        return
    page = window.stack.currentWidget() if hasattr(window, "stack") else None
    if page is not None:
        clear_page_selection(page)


def clear_page_selection(page: QWidget) -> None:
    clear_fn = getattr(page, "_clear_selection", None) or getattr(page, "clear_selection", None)
    if callable(clear_fn):
        clear_fn()
        return
    for view in page.findChildren(QAbstractItemView):
        try:
            view.clearSelection()
        except Exception:
            pass

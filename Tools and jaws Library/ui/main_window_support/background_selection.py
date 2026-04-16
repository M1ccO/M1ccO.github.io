from __future__ import annotations

from shared.ui.main_window_helpers import is_interactive_widget_click


def clear_active_page_selection_on_background_click(window, obj) -> None:
    if is_interactive_widget_click(obj, window):
        return

    page = window.stack.currentWidget() if hasattr(window, "stack") else None
    if page is None:
        return

    catalog_view = getattr(page, "tool_list", None) or getattr(page, "jaw_list", None)
    if catalog_view is not None:
        current = obj
        while current is not None:
            if current is catalog_view:
                return
            current = current.parentWidget()

    if hasattr(page, "_clear_selection"):
        page._clear_selection()

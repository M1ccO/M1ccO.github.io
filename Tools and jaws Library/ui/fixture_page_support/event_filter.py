"""Event filter handler for FixturePage.

Extracted from fixture_page.py (Phase 5 Pass 7).  The single public function
handle_jaw_page_event() replaces the large eventFilter override in
fixture_page.py, keeping that file focused on orchestration logic.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent
from shiboken6 import isValid

from ui.fixture_page_support.selector_actions import (
    selector_drag_payload_jaw_ids,
    selector_remove_btn_contains_global_point,
)

__all__ = ["handle_jaw_page_event"]


def _alive(widget) -> bool:
    """Return True when a Qt widget still has a valid C++ backing object."""
    return widget is not None and isValid(widget)


def _safe_viewport(widget):
    """Return viewport if widget is valid; otherwise None."""
    if not _alive(widget):
        return None
    try:
        viewport = widget.viewport()
    except RuntimeError:
        return None
    return viewport if _alive(viewport) else None


def handle_jaw_page_event(page, obj, event) -> bool:
    """Handle Qt events for FixturePage.

    Returns True if the event was consumed, False to continue default handling.
    Called from FixturePage.eventFilter(); the caller is responsible for falling
    through to super().eventFilter() when this returns False.
    """
    # Suppress combo popup flicker during search-toggle rebuild
    jaw_type_filter = getattr(page, 'jaw_type_filter', None)
    spindle_filter = getattr(page, 'spindle_filter', None)
    combo_widgets = {
        jaw_type_filter if _alive(jaw_type_filter) else None,
        jaw_type_filter.view() if _alive(jaw_type_filter) else None,
        spindle_filter if _alive(spindle_filter) else None,
        spindle_filter.view() if _alive(spindle_filter) else None,
    }
    if obj in combo_widgets:
        if getattr(page, '_suppress_combo', False) and event.type() in (QEvent.Show, QEvent.ShowToParent):
            return True

    # Drag-and-drop into selector zone
    selector_scroll = getattr(page, 'selector_scroll', None)
    selector_drag_targets = {
        getattr(page, 'selector_card', None),
        getattr(page, 'selector_panel', None),
        _safe_viewport(selector_scroll),
    }
    if (
        page._selector_active
        and obj in selector_drag_targets
        and event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop)
        and hasattr(event, 'mimeData')
    ):
        jaw_ids = selector_drag_payload_jaw_ids(page, event.mimeData())
        point = event.position().toPoint() if hasattr(event, 'position') else None
        if jaw_ids and point is not None:
            global_pos = obj.mapToGlobal(point)
            if selector_remove_btn_contains_global_point(page, global_pos):
                if event.type() == QEvent.Drop:
                    page._selector_slot_controller.remove_selector_jaws_by_ids(jaw_ids)
                event.acceptProposedAction()
                return True

    # Click outside slots clears slot selection
    selector_click_targets = {
        getattr(page, 'selector_card', None),
        getattr(page, 'selector_panel', None),
        getattr(page, 'detail_container', None),
        getattr(page, 'splitter', None),
        getattr(page, 'button_bar', None),
        getattr(page, 'selector_bottom_bar', None),
        getattr(page, 'filter_pane', None),
        getattr(page, 'detail_header_container', None),
        _safe_viewport(selector_scroll),
    }
    if (
        page._selector_active
        and event.type() == QEvent.MouseButtonPress
        and obj in selector_click_targets
        and hasattr(event, 'pos')
    ):
        global_pos = obj.mapToGlobal(event.pos())
        on_slot = False
        for slot_widget in (
            getattr(page, 'selector_sp1_slot', None),
            getattr(page, 'selector_sp2_slot', None),
        ):
            if slot_widget is None:
                continue
            local_pos = slot_widget.mapFromGlobal(global_pos)
            if slot_widget.rect().contains(local_pos):
                on_slot = True
                break
        if not on_slot and hasattr(page, 'selector_remove_btn'):
            remove_local = page.selector_remove_btn.mapFromGlobal(global_pos)
            if page.selector_remove_btn.rect().contains(remove_local):
                on_slot = True
        if not on_slot and page._selector_selected_slots:
            page._selector_selected_slots.clear()
            page._selector_slot_controller.refresh_selector_slots()

    # Click on empty list area clears item selection
    jaw_list = getattr(page, 'jaw_list', None)
    jaw_list_viewport = _safe_viewport(jaw_list)
    if _alive(jaw_list) and obj in (jaw_list, jaw_list_viewport):
        if event.type() == QEvent.MouseButtonPress and not jaw_list.indexAt(event.pos()).isValid():
            page._clear_selection()

    return False

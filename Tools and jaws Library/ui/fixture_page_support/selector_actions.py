"""Selector action helpers for FixturePage."""

from __future__ import annotations

from ui.selector_mime import fixture_payload_ids
from ui.selector_state_helpers import has_any_selector_assignment
from ui.selector_ui_helpers import event_point, normalize_selector_spindle, selector_spindle_label, widget_contains_global_point


def update_selector_spindle_ui(page) -> None:
    spindle = normalize_selector_spindle(page._selector_spindle)
    if hasattr(page, "selector_spindle_value_label"):
        page.selector_spindle_value_label.setText(selector_spindle_label(spindle))


def apply_selector_slot_selection(page) -> None:
    if hasattr(page, "selector_sp1_slot"):
        page.selector_sp1_slot.set_selected("main" in page._selector_selected_slots)
    if hasattr(page, "selector_sp2_slot"):
        page.selector_sp2_slot.set_selected("sub" in page._selector_selected_slots)


def update_selector_remove_button(page) -> None:
    if not hasattr(page, "selector_remove_btn"):
        return
    has_selected = any(page._selector_assignments.get(slot) is not None for slot in page._selector_selected_slots)
    has_assigned = has_any_selector_assignment(page._selector_assignments)
    page.selector_remove_btn.setEnabled(has_selected or has_assigned)


def selector_remove_btn_contains_global_point(page, global_pos) -> bool:
    return widget_contains_global_point(getattr(page, "selector_remove_btn", None), global_pos)


def selector_drag_payload_fixture_ids(page, mime) -> list[str]:
    remove_btn = getattr(page, "selector_remove_btn", None)
    if remove_btn is not None and hasattr(remove_btn, "_payload_fixture_ids"):
        return remove_btn._payload_fixture_ids(mime)
    return fixture_payload_ids(mime)


def on_selector_cancel(page) -> None:
    main_win = page.window()
    if hasattr(main_win, "_clear_selector_session"):
        main_win._clear_selector_session()
    if hasattr(main_win, "_back_to_setup_manager"):
        main_win._back_to_setup_manager()


def on_selector_done(page) -> None:
    main_win = page.window()
    if hasattr(main_win, "_send_selector_selection"):
        main_win._send_selector_selection()


def on_selector_toggle_clicked(page) -> None:
    if not page._selector_active:
        return
    if page.selector_toggle_btn.isChecked():
        page._selector_slot_controller.set_selector_panel_mode("selector")
    else:
        page._selector_slot_controller.set_selector_panel_mode("details")



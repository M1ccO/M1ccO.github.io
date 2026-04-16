"""Support helpers for Jaw Page UI logic.

This package intentionally uses lazy exports so importing a single submodule
(e.g. from selector dialogs) does not eagerly import all jaw-page dependencies.
"""

from __future__ import annotations

import importlib

_EXPORTS = {
    "batch_edit_jaws": ".batch_actions",
    "group_edit_jaws": ".batch_actions",
    "prompt_batch_cancel_behavior": ".batch_actions",
    "apply_jaw_detail_grid_rules": ".detail_layout_rules",
    "apply_detached_measurement_state": ".detached_preview",
    "apply_detached_preview_default_bounds": ".detached_preview",
    "close_detached_preview": ".detached_preview",
    "ensure_detached_preview_dialog": ".detached_preview",
    "load_preview_content": ".detached_preview",
    "on_detached_measurements_toggled": ".detached_preview",
    "on_detached_preview_closed": ".detached_preview",
    "set_preview_button_checked": ".detached_preview",
    "sync_detached_preview": ".detached_preview",
    "toggle_preview_window": ".detached_preview",
    "update_detached_measurement_toggle_icon": ".detached_preview",
    "apply_jaw_preview_transform": ".preview_rules",
    "jaw_preview_has_model_payload": ".preview_rules",
    "jaw_preview_label": ".preview_rules",
    "jaw_preview_measurement_overlays": ".preview_rules",
    "jaw_preview_parts_payload": ".preview_rules",
    "jaw_preview_plane": ".preview_rules",
    "jaw_preview_rotation": ".preview_rules",
    "jaw_preview_stl_path": ".preview_rules",
    "jaw_preview_transform_signature": ".preview_rules",
    "on_selector_cancel": ".selector_actions",
    "on_selector_done": ".selector_actions",
    "on_selector_toggle_clicked": ".selector_actions",
    "selector_drag_payload_jaw_ids": ".selector_actions",
    "selector_remove_btn_contains_global_point": ".selector_actions",
    "update_selector_remove_button": ".selector_actions",
    "SelectorSlotController": ".selector_slot_controller",
    "JawAssignmentSlot": ".selector_widgets",
    "SelectorRemoveDropButton": ".selector_widgets",
    "JawCatalogListView": ".catalog_list_widgets",
    "build_filter_toolbar": ".topbar_builder",
    "populate_jaw_type_filter": ".topbar_builder",
    "rebuild_filter_row": ".topbar_builder",
    "retranslate_filter_toolbar": ".topbar_builder",
    "populate_detail_panel": ".detail_panel_builder",
    "build_bottom_bars": ".bottom_bars_builder",
    "retranslate_bottom_bars": ".bottom_bars_builder",
    "build_jaw_page_layout": ".page_builders",
    "handle_jaw_page_event": ".event_filter",
    "add_jaw": ".crud_actions",
    "copy_jaw": ".crud_actions",
    "delete_jaw": ".crud_actions",
    "edit_jaw": ".crud_actions",
    "prompt_text": ".crud_actions",
    "save_from_dialog": ".crud_actions",
    "apply_jaw_page_localization": ".retranslate_page",
    "hide_jaw_details": ".detail_visibility",
    "show_jaw_details": ".detail_visibility",
    "toggle_jaw_details": ".detail_visibility",
    "clear_jaw_selection": ".selection_helpers",
    "selected_jaw_ids": ".selection_helpers",
    "selected_jaws_for_setup_assignment": ".selection_helpers",
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value

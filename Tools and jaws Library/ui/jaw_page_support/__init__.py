"""Support helpers for Jaw Page UI logic."""

from .batch_actions import (
    batch_edit_jaws,
    group_edit_jaws,
    prompt_batch_cancel_behavior,
)
from .detail_layout_rules import apply_jaw_detail_grid_rules
from .detached_preview import (
    apply_detached_measurement_state,
    apply_detached_preview_default_bounds,
    close_detached_preview,
    ensure_detached_preview_dialog,
    load_preview_content,
    on_detached_measurements_toggled,
    on_detached_preview_closed,
    set_preview_button_checked,
    sync_detached_preview,
    toggle_preview_window,
    update_detached_measurement_toggle_icon,
)
from .preview_rules import (
    apply_jaw_preview_transform,
    jaw_preview_has_model_payload,
    jaw_preview_label,
    jaw_preview_measurement_overlays,
    jaw_preview_parts_payload,
    jaw_preview_plane,
    jaw_preview_rotation,
    jaw_preview_stl_path,
    jaw_preview_transform_signature,
)
from .selector_actions import (
    on_selector_cancel,
    on_selector_done,
    on_selector_toggle_clicked,
    selector_drag_payload_jaw_ids,
    selector_remove_btn_contains_global_point,
    update_selector_remove_button,
)
from .selector_slot_controller import SelectorSlotController
from .selector_widgets import JawAssignmentSlot, SelectorRemoveDropButton
from .catalog_list_widgets import JawCatalogListView
from .topbar_builder import build_filter_toolbar, populate_jaw_type_filter, rebuild_filter_row, retranslate_filter_toolbar
from .detail_panel_builder import populate_detail_panel
from .bottom_bars_builder import build_bottom_bars, retranslate_bottom_bars
from .page_builders import build_jaw_page_layout
from .event_filter import handle_jaw_page_event
from .crud_actions import add_jaw, copy_jaw, delete_jaw, edit_jaw, prompt_text, save_from_dialog
from .retranslate_page import apply_jaw_page_localization
from .detail_visibility import hide_jaw_details, show_jaw_details, toggle_jaw_details
from .selection_helpers import clear_jaw_selection, selected_jaw_ids, selected_jaws_for_setup_assignment

__all__ = [
    "apply_detached_measurement_state",
    "apply_jaw_preview_transform",
    "apply_detached_preview_default_bounds",
    "apply_jaw_detail_grid_rules",
    "batch_edit_jaws",
    "build_bottom_bars",
    "build_filter_toolbar",
    "close_detached_preview",
    "ensure_detached_preview_dialog",
    "group_edit_jaws",
    "JawCatalogListView",
    "jaw_preview_has_model_payload",
    "jaw_preview_label",
    "jaw_preview_measurement_overlays",
    "jaw_preview_parts_payload",
    "jaw_preview_plane",
    "jaw_preview_rotation",
    "jaw_preview_stl_path",
    "jaw_preview_transform_signature",
    "load_preview_content",
    "on_detached_measurements_toggled",
    "on_detached_preview_closed",
    "on_selector_cancel",
    "on_selector_done",
    "on_selector_toggle_clicked",
    "populate_detail_panel",
    "populate_jaw_type_filter",
    "prompt_batch_cancel_behavior",
    "rebuild_filter_row",
    "retranslate_bottom_bars",
    "retranslate_filter_toolbar",
    "selector_drag_payload_jaw_ids",
    "selector_remove_btn_contains_global_point",
    "set_preview_button_checked",
    "sync_detached_preview",
    "toggle_preview_window",
    "update_detached_measurement_toggle_icon",
    "update_selector_remove_button",
    "SelectorSlotController",
    "JawAssignmentSlot",
    "SelectorRemoveDropButton",
    "add_jaw",
    "apply_jaw_page_localization",
    "build_jaw_page_layout",
    "clear_jaw_selection",
    "copy_jaw",
    "delete_jaw",
    "edit_jaw",
    "handle_jaw_page_event",
    "hide_jaw_details",
    "prompt_text",
    "save_from_dialog",
    "selected_jaw_ids",
    "selected_jaws_for_setup_assignment",
    "show_jaw_details",
    "toggle_jaw_details",
]

"""Support helpers for Fixture Page UI logic."""

from .batch_actions import (
    batch_edit_fixtures,
    group_edit_fixtures,
    prompt_batch_cancel_behavior,
)
from .detail_layout_rules import apply_fixture_detail_grid_rules
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
    apply_fixture_preview_transform,
    fixture_preview_has_model_payload,
    fixture_preview_label,
    fixture_preview_measurement_overlays,
    fixture_preview_parts_payload,
    fixture_preview_plane,
    fixture_preview_rotation,
    fixture_preview_stl_path,
    fixture_preview_transform_signature,
)
from .selector_actions import (
    on_selector_cancel,
    on_selector_done,
    on_selector_toggle_clicked,
    selector_drag_payload_fixture_ids,
    selector_remove_btn_contains_global_point,
    update_selector_remove_button,
)
from .selector_slot_controller import SelectorSlotController
from .selector_widgets import FixtureAssignmentSlot, SelectorRemoveDropButton
from .catalog_list_widgets import FixtureCatalogListView
from .topbar_builder import build_filter_toolbar, populate_fixture_type_filter, rebuild_filter_row, retranslate_filter_toolbar
from .detail_panel_builder import populate_detail_panel
from .bottom_bars_builder import build_bottom_bars, retranslate_bottom_bars
from .page_builders import build_fixture_page_layout
from .event_filter import handle_fixture_page_event
from .crud_actions import add_fixture, copy_fixture, delete_fixture, edit_fixture, prompt_text, save_from_dialog
from .retranslate_page import apply_fixture_page_localization
from .detail_visibility import hide_fixture_details, show_fixture_details, toggle_fixture_details
from .selection_helpers import clear_fixture_selection, selected_fixture_ids, selected_fixtures_for_setup_assignment

__all__ = [
    "apply_detached_measurement_state",
    "apply_fixture_preview_transform",
    "apply_detached_preview_default_bounds",
    "apply_fixture_detail_grid_rules",
    "batch_edit_fixtures",
    "build_bottom_bars",
    "build_filter_toolbar",
    "close_detached_preview",
    "ensure_detached_preview_dialog",
    "group_edit_fixtures",
    "FixtureCatalogListView",
    "fixture_preview_has_model_payload",
    "fixture_preview_label",
    "fixture_preview_measurement_overlays",
    "fixture_preview_parts_payload",
    "fixture_preview_plane",
    "fixture_preview_rotation",
    "fixture_preview_stl_path",
    "fixture_preview_transform_signature",
    "load_preview_content",
    "on_detached_measurements_toggled",
    "on_detached_preview_closed",
    "on_selector_cancel",
    "on_selector_done",
    "on_selector_toggle_clicked",
    "populate_detail_panel",
    "populate_fixture_type_filter",
    "prompt_batch_cancel_behavior",
    "rebuild_filter_row",
    "retranslate_bottom_bars",
    "retranslate_filter_toolbar",
    "selector_drag_payload_fixture_ids",
    "selector_remove_btn_contains_global_point",
    "set_preview_button_checked",
    "sync_detached_preview",
    "toggle_preview_window",
    "update_detached_measurement_toggle_icon",
    "update_selector_remove_button",
    "SelectorSlotController",
    "FixtureAssignmentSlot",
    "SelectorRemoveDropButton",
    "add_fixture",
    "apply_fixture_page_localization",
    "build_fixture_page_layout",
    "clear_fixture_selection",
    "copy_fixture",
    "delete_fixture",
    "edit_fixture",
    "handle_fixture_page_event",
    "hide_fixture_details",
    "prompt_text",
    "save_from_dialog",
    "selected_fixture_ids",
    "selected_fixtures_for_setup_assignment",
    "show_fixture_details",
    "toggle_fixture_details",
]


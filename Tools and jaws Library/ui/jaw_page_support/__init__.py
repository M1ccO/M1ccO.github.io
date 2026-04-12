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
    jaw_preview_has_model_payload,
    jaw_preview_label,
    jaw_preview_measurement_overlays,
    jaw_preview_parts_payload,
    jaw_preview_stl_path,
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

__all__ = [
    "apply_detached_measurement_state",
    "apply_detached_preview_default_bounds",
    "apply_jaw_detail_grid_rules",
    "batch_edit_jaws",
    "close_detached_preview",
    "ensure_detached_preview_dialog",
    "group_edit_jaws",
    "jaw_preview_has_model_payload",
    "jaw_preview_label",
    "jaw_preview_measurement_overlays",
    "jaw_preview_parts_payload",
    "jaw_preview_stl_path",
    "load_preview_content",
    "on_detached_measurements_toggled",
    "on_detached_preview_closed",
    "on_selector_cancel",
    "on_selector_done",
    "on_selector_toggle_clicked",
    "prompt_batch_cancel_behavior",
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
]

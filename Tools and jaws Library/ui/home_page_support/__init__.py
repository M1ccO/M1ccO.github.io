"""Support helpers for Home Page UI logic."""

from .batch_actions import (
    batch_edit_tools,
    group_edit_tools,
    prompt_batch_cancel_behavior,
)
from .dialog_helpers import confirm_yes_no, prompt_text
from .bottom_bars_builder import build_bottom_bars
from .catalog_list_widgets import (
    SelectorAssignmentRowWidget,
    SelectorToolRemoveDropButton,
    ToolAssignmentListWidget,
    ToolCatalogListView,
)
from .components_panel_builder import build_components_panel
from .detail_fields_builder import add_three_box_row, add_two_box_row, build_detail_field
from .detail_layout_rules import apply_tool_detail_layout_rules
from .detached_preview import (
    close_detached_preview,
    load_preview_content,
    ensure_detached_preview_dialog,
    sync_detached_preview,
    toggle_preview_window,
)
from .preview_panel_builder import build_preview_panel
from .selector_card_builder import build_selector_card
from .selector_assignment_state import SelectorAssignmentState
from .selector_actions import (
    add_selector_comment,
    delete_selector_comment,
    move_selector_down,
    move_selector_up,
    on_selector_cancel,
    on_selector_done,
    on_selector_toggle_clicked,
    on_selector_tools_dropped,
    remove_selector_assignment,
    remove_selector_assignments_by_keys,
    sync_selector_assignment_order,
    sync_selector_card_selection_states,
    update_selector_assignment_buttons,
)
from .selector_model import (
    normalize_selector_head_value,
    normalize_selector_spindle_value,
    normalize_selector_tool,
    normalize_tool_spindle_orientation,
    selector_target_key,
    selector_tool_key,
)
from .topbar_builder import build_catalog_list_panel, build_filter_toolbar

__all__ = [
    "add_three_box_row",
    "add_two_box_row",
    "apply_tool_detail_layout_rules",
    "build_components_panel",
    "build_bottom_bars",
    "build_catalog_list_panel",
    "build_detail_field",
    "build_filter_toolbar",
    "build_preview_panel",
    "build_selector_card",
    "close_detached_preview",
    "ensure_detached_preview_dialog",
    "load_preview_content",
    "sync_detached_preview",
    "toggle_preview_window",
    "SelectorAssignmentRowWidget",
    "SelectorToolRemoveDropButton",
    "ToolAssignmentListWidget",
    "ToolCatalogListView",
    "add_selector_comment",
    "delete_selector_comment",
    "move_selector_down",
    "move_selector_up",
    "on_selector_cancel",
    "on_selector_done",
    "on_selector_toggle_clicked",
    "on_selector_tools_dropped",
    "remove_selector_assignment",
    "remove_selector_assignments_by_keys",
    "sync_selector_assignment_order",
    "sync_selector_card_selection_states",
    "update_selector_assignment_buttons",
    "SelectorAssignmentState",
    "confirm_yes_no",
    "normalize_selector_head_value",
    "normalize_selector_spindle_value",
    "normalize_selector_tool",
    "normalize_tool_spindle_orientation",
    "prompt_text",
    "selector_target_key",
    "selector_tool_key",
]

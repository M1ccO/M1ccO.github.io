from __future__ import annotations

from typing import Any, Callable

from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout

try:
    from shared.ui.helpers.editor_helpers import ResponsiveColumnsHost, apply_shared_checkbox_style
except ModuleNotFoundError:
    from editor_helpers import ResponsiveColumnsHost, apply_shared_checkbox_style
from .tool_actions import (
    on_tool_list_interaction,
    remove_dragged_tool_assignments,
    shared_add_tool_comment,
    shared_delete_tool_comment,
    shared_move_tool_down,
    shared_move_tool_up,
    shared_remove_selected_tool,
    sync_tool_head_view,
    update_shared_tool_actions,
)


def build_tools_tab_ui(
    dialog: Any,
    *,
    ordered_tool_list_cls: type,
    remove_drop_button_cls: type,
    section_label_factory: Callable[[str], object],
) -> None:
    """Build the Tools tab while keeping dialog state ownership intact."""
    layout = QVBoxLayout(dialog.tools_tab)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    toolbar = QHBoxLayout()
    toolbar.setContentsMargins(0, 0, 0, 0)
    toolbar.setSpacing(8)
    toolbar.addWidget(section_label_factory(dialog._t("work_editor.tools.head_view", "View")))

    dialog.tools_head_switch = QPushButton()
    dialog.tools_head_switch.setProperty("panelActionButton", True)
    dialog.tools_head_switch.setCheckable(True)
    dialog.tools_head_switch.setMinimumWidth(112)
    dialog.tools_head_switch.setMaximumWidth(146)
    dialog.tools_head_switch.setFixedHeight(30)
    dialog.tools_head_switch.clicked.connect(dialog._toggle_tools_head_view)
    dialog.tools_head_switch.setProperty("head", next(iter(dialog._head_profiles.keys()), "HEAD1"))
    dialog._update_tools_head_switch_text()
    dialog.tools_head_switch.setVisible(len(dialog.machine_profile.heads) > 1)
    toolbar.addWidget(dialog.tools_head_switch)

    dialog.open_tool_selector_btn = QPushButton(
        dialog._t("work_editor.selector.tools_button", "Select Tools")
    )
    dialog.open_tool_selector_btn.setProperty("panelActionButton", True)
    dialog.open_tool_selector_btn.clicked.connect(dialog._open_tool_selector)
    toolbar.addWidget(dialog.open_tool_selector_btn)

    toolbar.addStretch(1)

    dialog.print_pots_checkbox = QCheckBox(
        dialog._t("work_editor.tools.print_pot_numbers", "Print Pot Numbers")
    )
    apply_shared_checkbox_style(dialog.print_pots_checkbox, indicator_size=16, min_height=30)
    dialog.print_pots_checkbox.setFixedHeight(30)
    dialog.print_pots_checkbox.setVisible(dialog.machine_profile.supports_print_pots)

    dialog.edit_pots_btn = QPushButton(dialog._t("work_editor.tools.edit_pots", "Edit Pots"))
    dialog.edit_pots_btn.setProperty("secondaryButton", True)
    dialog.edit_pots_btn.setFixedHeight(30)
    button_metrics = QFontMetrics(dialog.edit_pots_btn.font())
    button_text = dialog.edit_pots_btn.text().upper()
    button_width = max(180, button_metrics.horizontalAdvance(button_text) + 42)
    dialog.edit_pots_btn.setFixedWidth(button_width)
    edit_pots_size_policy = dialog.edit_pots_btn.sizePolicy()
    edit_pots_size_policy.setRetainSizeWhenHidden(True)
    dialog.edit_pots_btn.setSizePolicy(edit_pots_size_policy)
    dialog.edit_pots_btn.setVisible(False)
    dialog.edit_pots_btn.clicked.connect(dialog._open_pot_editor)
    toolbar.addWidget(dialog.edit_pots_btn)
    toolbar.addWidget(dialog.print_pots_checkbox)

    dialog.print_pots_checkbox.toggled.connect(
        lambda checked: dialog.edit_pots_btn.setVisible(
            dialog.machine_profile.supports_print_pots and checked
        )
    )
    dialog.print_pots_checkbox.toggled.connect(dialog._on_print_pots_toggled)

    layout.addLayout(toolbar)

    host = ResponsiveColumnsHost(switch_width=820)
    for head in dialog.machine_profile.heads:
        # Main/sub columns of the same head must stay in lockstep with one backing
        # assignment store so drag/drop and selector callbacks stay deterministic.
        shared_assignments = {"main": [], "sub": []}
        main_ordered = ordered_tool_list_cls(
            dialog._spindle_label("main", "Main spindle tools"),
            head.key,
            translate=dialog._t,
        )
        sub_ordered = ordered_tool_list_cls(
            dialog._spindle_label("sub", "Sub spindle tools"),
            head.key,
            translate=dialog._t,
        )
        main_ordered.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sub_ordered.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_ordered.spindle_selector.setVisible(False)
        sub_ordered.spindle_selector.setVisible(False)
        main_ordered.set_controls_visible(False)
        sub_ordered.set_controls_visible(False)
        main_ordered.set_current_spindle("main")
        sub_ordered.set_current_spindle("sub")
        main_ordered._assignments_by_spindle = shared_assignments
        sub_ordered._assignments_by_spindle = shared_assignments
        main_ordered.selectorRequested.connect(dialog._open_tool_selector_for_bucket)
        sub_ordered.selectorRequested.connect(dialog._open_tool_selector_for_bucket)
        main_ordered.tool_list.currentRowChanged.connect(
            lambda _row, ordered=main_ordered: on_tool_list_interaction(dialog, ordered)
        )
        sub_ordered.tool_list.currentRowChanged.connect(
            lambda _row, ordered=sub_ordered: on_tool_list_interaction(dialog, ordered)
        )
        main_ordered.tool_list.itemSelectionChanged.connect(
            lambda ordered=main_ordered: on_tool_list_interaction(dialog, ordered)
        )
        sub_ordered.tool_list.itemSelectionChanged.connect(
            lambda ordered=sub_ordered: on_tool_list_interaction(dialog, ordered)
        )
        dialog._ordered_tool_lists[head.key] = main_ordered
        dialog._tool_column_lists[head.key] = {"main": main_ordered, "sub": sub_ordered}
        dialog._all_tool_list_widgets.extend([main_ordered, sub_ordered])
        if head.key == "HEAD1":
            dialog.head1_ordered = main_ordered
        elif head.key == "HEAD2":
            dialog.head2_ordered = main_ordered
        host.add_widget(main_ordered, 1)
        host.add_widget(sub_ordered, 1)

    host_surface = QFrame()
    host_surface.setProperty("toolIdsHostSurface", True)
    host_surface_layout = QVBoxLayout(host_surface)
    host_surface_layout.setContentsMargins(8, 8, 8, 8)
    host_surface_layout.setSpacing(0)
    host_surface_layout.addWidget(host, 1)
    layout.addWidget(host_surface, 1)

    dialog.shared_tool_actions = QFrame()
    shared_actions_layout = QHBoxLayout(dialog.shared_tool_actions)
    shared_actions_layout.setContentsMargins(8, 8, 8, 0)
    shared_actions_layout.setSpacing(8)

    dialog.shared_move_up_btn = QPushButton(dialog._t("work_editor.tools.move_up", "\u25B2"))
    dialog.shared_move_down_btn = QPushButton(dialog._t("work_editor.tools.move_down", "\u25BC"))
    for btn in (dialog.shared_move_up_btn, dialog.shared_move_down_btn):
        btn.setProperty("panelActionButton", True)
        btn.setMinimumWidth(52)
        btn.setMaximumWidth(64)
        btn.setStyleSheet("font-size: 16px; font-weight: 700;")

    dialog.shared_remove_btn = remove_drop_button_cls()
    ordered_tool_list_cls._configure_icon_action(
        dialog.shared_remove_btn,
        "delete",
        dialog._t("work_editor.tools.remove", "Remove Tool"),
        danger=True,
    )

    dialog.shared_comment_btn = QPushButton()
    ordered_tool_list_cls._configure_icon_action(
        dialog.shared_comment_btn,
        "comment",
        dialog._t("work_editor.tools.add_comment", "Add Comment"),
    )

    dialog.shared_delete_comment_btn = QPushButton()
    ordered_tool_list_cls._configure_icon_action(
        dialog.shared_delete_comment_btn,
        "comment_delete",
        dialog._t("work_editor.tools.delete_comment", "Delete Comment"),
    )
    dialog.shared_delete_comment_btn.setVisible(False)

    dialog.shared_move_up_btn.clicked.connect(lambda: shared_move_tool_up(dialog))
    dialog.shared_move_down_btn.clicked.connect(lambda: shared_move_tool_down(dialog))
    dialog.shared_remove_btn.clicked.connect(lambda: shared_remove_selected_tool(dialog))
    dialog.shared_remove_btn.assignmentsDropped.connect(
        lambda dropped: remove_dragged_tool_assignments(dialog, dropped)
    )
    dialog.shared_comment_btn.clicked.connect(lambda: shared_add_tool_comment(dialog))
    dialog.shared_delete_comment_btn.clicked.connect(lambda: shared_delete_tool_comment(dialog))

    shared_actions_layout.addStretch(1)
    shared_actions_layout.addWidget(dialog.shared_move_up_btn)
    shared_actions_layout.addWidget(dialog.shared_move_down_btn)
    shared_actions_layout.addWidget(dialog.shared_remove_btn)
    shared_actions_layout.addWidget(dialog.shared_comment_btn)
    shared_actions_layout.addWidget(dialog.shared_delete_comment_btn)
    shared_actions_layout.addStretch(1)
    layout.addWidget(dialog.shared_tool_actions, 0)
    sync_tool_head_view(dialog)
    update_shared_tool_actions(dialog)


"""Selector-card builder for HomePage."""

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout

from shared.editor_helpers import create_titled_section, style_move_arrow_button, style_panel_action_button
from .selector_actions import (
    add_selector_comment,
    delete_selector_comment,
    move_selector_down,
    move_selector_up,
    on_selector_toggle_clicked,
    on_selector_tools_dropped,
    remove_selector_assignment,
    remove_selector_assignments_by_keys,
    sync_selector_assignment_order,
    sync_selector_card_selection_states,
    update_selector_assignment_buttons,
)
from ui.shared.selector_panel_builders import (
    apply_selector_icon_button,
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_hint_label,
    build_selector_info_header,
    build_selector_toggle_button,
)


def build_selector_card(
    page,
    *,
    dc_layout: QVBoxLayout,
    assignment_list_cls,
    remove_drop_button_cls,
    tool_icons_dir,
) -> None:
    """Build the selector context card shown when assigning tools externally."""
    page.selector_card, page.selector_scroll, page.selector_panel, selector_layout = build_selector_card_shell(spacing=8)
    selector_card_layout = QVBoxLayout(page.selector_card)
    selector_card_layout.setContentsMargins(0, 0, 0, 0)
    selector_card_layout.setSpacing(0)

    (
        page.selector_info_header,
        page.selector_header_title_label,
        page.selector_spindle_value_label,
        page.selector_head_value_label,
    ) = build_selector_info_header(
        title_text=page._t("tool_library.selector.header_title", "Tool Selector"),
        left_badge_text="SP1",
        right_badge_text="HEAD1",
    )
    selector_layout.addWidget(page.selector_info_header, 0)

    ctx_row = QHBoxLayout()
    ctx_row.setContentsMargins(0, 0, 0, 0)
    ctx_row.setSpacing(10)
    ctx_row.addStretch(1)

    page.selector_toggle_btn = build_selector_toggle_button(
        text=page._t("tool_library.selector.mode_details", "DETAILS"),
        on_clicked=lambda: on_selector_toggle_clicked(page),
    )
    ctx_row.addWidget(page.selector_toggle_btn, 0)

    page.selector_spindle_btn = QPushButton("SP1")
    page.selector_spindle_btn.setProperty("panelActionButton", True)
    page.selector_spindle_btn.setCheckable(True)
    page.selector_spindle_btn.setMinimumWidth(120)
    page.selector_spindle_btn.setMaximumWidth(140)
    page.selector_spindle_btn.setFixedHeight(30)
    page.selector_spindle_btn.setProperty("spindle", "main")
    page.selector_spindle_btn.clicked.connect(page._toggle_selector_spindle)
    style_panel_action_button(page.selector_spindle_btn)
    ctx_row.addWidget(page.selector_spindle_btn, 0)
    ctx_row.addStretch(1)
    selector_layout.addLayout(ctx_row)

    page.selector_drop_hint = build_selector_hint_label(
        text=page._t(
            "tool_library.selector.drop_hint",
            "Drag tools from the catalog to this list and reorder them by dragging.",
        ),
        multiline=True,
    )
    selector_layout.addWidget(page.selector_drop_hint, 0)

    page.selector_assignment_list = assignment_list_cls()
    page.selector_assignment_list.setObjectName("toolIdsOrderList")
    page.selector_assignment_list.setStyleSheet(
        "#toolIdsOrderList { background: transparent; border: none; }"
        "#toolIdsOrderList::viewport { background: transparent; border: none; }"
        "#toolIdsOrderList::item { background: transparent; border: none; }"
    )
    page.selector_assignment_list.externalToolsDropped.connect(
        lambda dropped, insert_row: on_selector_tools_dropped(page, dropped, insert_row)
    )
    page.selector_assignment_list.orderChanged.connect(lambda: sync_selector_assignment_order(page))
    page.selector_assignment_list.itemSelectionChanged.connect(
        lambda: update_selector_assignment_buttons(page)
    )
    page.selector_assignment_list.itemSelectionChanged.connect(
        lambda: sync_selector_card_selection_states(page)
    )

    page.selector_assignments_frame = create_titled_section(page._selector_assignments_section_title())
    page.selector_assignments_frame.setProperty("selectorAssignmentsFrame", True)
    page.selector_assignments_frame.setProperty("toolIdsPanel", True)
    page.selector_assignments_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    selector_assignments_layout = QVBoxLayout(page.selector_assignments_frame)
    selector_assignments_layout.setContentsMargins(8, 10, 8, 8)
    selector_assignments_layout.setSpacing(0)
    selector_assignments_layout.addWidget(page.selector_assignment_list, 1)
    selector_layout.addWidget(page.selector_assignments_frame, 1)

    selector_actions = build_selector_actions_row(spacing=4)
    selector_actions.addStretch(1)

    page.selector_move_up_btn = QPushButton("\u25B2")
    style_move_arrow_button(
        page.selector_move_up_btn,
        "\u25B2",
        page._t("tool_library.selector.move_up", "Move Up"),
    )
    page.selector_move_up_btn.clicked.connect(lambda: move_selector_up(page))
    selector_actions.addWidget(page.selector_move_up_btn)

    page.selector_move_down_btn = QPushButton("\u25BC")
    style_move_arrow_button(
        page.selector_move_down_btn,
        "\u25BC",
        page._t("tool_library.selector.move_down", "Move Down"),
    )
    page.selector_move_down_btn.clicked.connect(lambda: move_selector_down(page))
    selector_actions.addWidget(page.selector_move_down_btn)

    page.selector_remove_btn = remove_drop_button_cls()
    apply_selector_icon_button(
        page.selector_remove_btn,
        icon_path=tool_icons_dir / "delete.svg",
        tooltip=page._t("tool_library.selector.remove", "Remove"),
        danger=True,
    )
    page.selector_remove_btn.clicked.connect(lambda: remove_selector_assignment(page))
    page.selector_remove_btn.toolsDropped.connect(
        lambda keys: remove_selector_assignments_by_keys(page, keys)
    )
    selector_actions.addWidget(page.selector_remove_btn)

    page.selector_comment_btn = QPushButton()
    apply_selector_icon_button(
        page.selector_comment_btn,
        icon_path=tool_icons_dir / "comment.svg",
        tooltip=page._t("tool_library.selector.add_comment", "Add Comment"),
    )
    page.selector_comment_btn.clicked.connect(lambda: add_selector_comment(page))
    selector_actions.addWidget(page.selector_comment_btn)

    page.selector_delete_comment_btn = QPushButton()
    apply_selector_icon_button(
        page.selector_delete_comment_btn,
        icon_path=tool_icons_dir / "comment_disable.svg",
        tooltip=page._t("tool_library.selector.delete_comment", "Delete Comment"),
    )
    page.selector_delete_comment_btn.clicked.connect(lambda: delete_selector_comment(page))
    page.selector_delete_comment_btn.setVisible(False)
    selector_actions.addWidget(page.selector_delete_comment_btn)

    selector_actions.addStretch(1)
    selector_layout.addLayout(selector_actions)
    page.selector_scroll.setWidget(page.selector_panel)
    selector_card_layout.addWidget(page.selector_scroll, 1)
    dc_layout.addWidget(page.selector_card, 1)

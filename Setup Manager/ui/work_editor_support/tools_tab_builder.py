from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from ui.widgets.common import apply_tool_library_combo_style

try:
    from shared.ui.helpers.editor_helpers import ResponsiveColumnsHost, apply_shared_checkbox_style
except ModuleNotFoundError:
    from editor_helpers import ResponsiveColumnsHost, apply_shared_checkbox_style
from machine_profiles import is_machining_center
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


class _ElidingLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._full_text = str(text or '')
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(24)
        self._apply_elided_text()

    def set_full_text(self, text: str) -> None:
        self._full_text = str(text or '')
        self._apply_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elided_text()

    def _apply_elided_text(self) -> None:
        metrics = self.fontMetrics()
        self.setText(metrics.elidedText(self._full_text, Qt.ElideRight, max(0, self.width())))
        self.setToolTip(self._full_text if self.text() != self._full_text else '')


def _build_eliding_checkbox(checkbox: QCheckBox, text: str) -> QWidget:
    checkbox.setText('')
    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(6)
    row_layout.addWidget(checkbox, 0, Qt.AlignVCenter)
    label = _ElidingLabel(text)
    row_layout.addWidget(label, 1)
    row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return row


def _build_machining_center_tools_tab_ui(
    dialog: Any,
    *,
    ordered_tool_list_cls: type,
    remove_drop_button_cls: type,
    section_label_factory: Callable[[str], object],
) -> None:
    layout = QVBoxLayout(dialog.tools_tab)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    toolbar = QHBoxLayout()
    toolbar.setContentsMargins(0, 0, 0, 0)
    toolbar.setSpacing(8)
    toolbar.addWidget(section_label_factory(dialog._t("work_editor.tools.operation", "Operation")))

    dialog.mc_tools_op_combo = QComboBox(dialog.tools_tab)
    dialog.mc_tools_op_combo.setProperty("modernDropdown", True)
    apply_tool_library_combo_style(dialog.mc_tools_op_combo)
    dialog.mc_tools_op_combo.setMinimumWidth(170)
    toolbar.addWidget(dialog.mc_tools_op_combo, 0)

    dialog.open_tool_selector_btn = QPushButton(
        dialog._t("work_editor.selector.tools_button", "Select Tools"),
        dialog.tools_tab,
    )
    dialog.open_tool_selector_btn.setProperty("panelActionButton", True)
    dialog.open_tool_selector_btn.clicked.connect(dialog._open_tool_selector)
    toolbar.addWidget(dialog.open_tool_selector_btn, 0)
    toolbar.addStretch(1)
    layout.addLayout(toolbar)

    host = ResponsiveColumnsHost(switch_width=820)
    ordered = ordered_tool_list_cls(
        dialog._t("work_editor.tools.op_tools", "Operation tools"),
        "HEAD1",
        parent=dialog.tools_tab,
        translate=dialog._t,
    )
    ordered.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    ordered.spindle_selector.setVisible(False)
    ordered.set_controls_visible(False)
    ordered.set_current_spindle("main")
    ordered._assignments_by_spindle = {"main": [], "sub": []}
    ordered.selectorRequested.connect(dialog._open_tool_selector_for_bucket)
    ordered.tool_list.currentRowChanged.connect(
        lambda _row, ordered_list=ordered: on_tool_list_interaction(dialog, ordered_list)
    )
    ordered.tool_list.itemSelectionChanged.connect(
        lambda ordered_list=ordered: on_tool_list_interaction(dialog, ordered_list)
    )

    dialog._ordered_tool_lists["HEAD1"] = ordered
    dialog._tool_column_lists["HEAD1"] = {"main": ordered, "sub": ordered}
    dialog._all_tool_list_widgets.append(ordered)
    dialog.head1_ordered = ordered
    dialog._mc_tools_ordered = ordered

    host.add_widget(ordered, 1)
    tool_ids_scroll_surface = QFrame(dialog.tools_tab)
    tool_ids_scroll_surface.setProperty("toolIdsScrollSurface", True)
    tool_ids_scroll_surface_layout = QVBoxLayout(tool_ids_scroll_surface)
    tool_ids_scroll_surface_layout.setContentsMargins(8, 8, 8, 8)
    tool_ids_scroll_surface_layout.setSpacing(0)
    tool_ids_scroll_surface_layout.addWidget(host, 1)
    tool_ids_scroll_surface.setMinimumHeight(280)
    layout.addWidget(tool_ids_scroll_surface, 2)

    dialog.shared_tool_actions = QFrame(dialog.tools_tab)
    shared_actions_layout = QHBoxLayout(dialog.shared_tool_actions)
    shared_actions_layout.setContentsMargins(8, 8, 8, 0)
    shared_actions_layout.setSpacing(8)

    dialog.shared_move_up_btn = QPushButton(dialog._t("work_editor.tools.move_up", "\u25B2"), dialog.tools_tab)
    dialog.shared_move_down_btn = QPushButton(dialog._t("work_editor.tools.move_down", "\u25BC"), dialog.tools_tab)
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

    def _sync_active_op_tools() -> None:
        active_key = str(getattr(dialog, '_mc_active_tools_op_key', '') or '').strip()
        if not active_key:
            return
        op = next(
            (item for item in (getattr(dialog, '_mc_operations', []) or []) if str(item.get('op_key') or '').strip() == active_key),
            None,
        )
        if op is None:
            return
        assignments = dialog._mc_tools_ordered.get_tool_assignments()
        op['tool_assignments'] = [dict(item) for item in assignments if isinstance(item, dict)]
        op['tool_ids'] = dialog._mc_tools_ordered.get_tool_ids()

    def _load_op_tools(op_key: str) -> None:
        op = next(
            (item for item in (getattr(dialog, '_mc_operations', []) or []) if str(item.get('op_key') or '').strip() == op_key),
            None,
        )
        dialog._mc_active_tools_op_key = op_key
        dialog._mc_tools_ordered.set_tool_assignments(list((op or {}).get('tool_assignments') or []))
        on_tool_list_interaction(dialog, dialog._mc_tools_ordered)

    def _refresh_mc_tools_op_options() -> None:
        previous = str(getattr(dialog, '_mc_active_tools_op_key', '') or '').strip()
        dialog.mc_tools_op_combo.blockSignals(True)
        dialog.mc_tools_op_combo.clear()
        for op in (getattr(dialog, '_mc_operations', []) or []):
            op_key = str(op.get('op_key') or '').strip()
            if op_key:
                dialog.mc_tools_op_combo.addItem(op_key, op_key)
        dialog.mc_tools_op_combo.blockSignals(False)
        if dialog.mc_tools_op_combo.count() == 0:
            dialog._mc_active_tools_op_key = ''
            dialog._mc_tools_ordered.set_tool_assignments([])
            return
        idx = dialog.mc_tools_op_combo.findData(previous)
        if idx < 0:
            idx = 0
        dialog.mc_tools_op_combo.setCurrentIndex(idx)
        _load_op_tools(str(dialog.mc_tools_op_combo.currentData() or ''))

    def _on_op_changed(_index: int) -> None:
        _sync_active_op_tools()
        _load_op_tools(str(dialog.mc_tools_op_combo.currentData() or ''))

    dialog.mc_tools_op_combo.currentIndexChanged.connect(_on_op_changed)
    dialog._sync_mc_tools_operation_payload = _sync_active_op_tools
    dialog._refresh_mc_tools_op_options = _refresh_mc_tools_op_options

    _refresh_mc_tools_op_options()
    update_shared_tool_actions(dialog)


def build_tools_tab_ui(
    dialog: Any,
    *,
    ordered_tool_list_cls: type,
    remove_drop_button_cls: type,
    section_label_factory: Callable[[str], object],
) -> None:
    """Build the Tools tab while keeping dialog state ownership intact."""
    if is_machining_center(dialog.machine_profile):
        _build_machining_center_tools_tab_ui(
            dialog,
            ordered_tool_list_cls=ordered_tool_list_cls,
            remove_drop_button_cls=remove_drop_button_cls,
            section_label_factory=section_label_factory,
        )
        return

    layout = QVBoxLayout(dialog.tools_tab)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    dialog.open_tool_selector_btn = QPushButton(
        dialog._t("work_editor.selector.tools_button", "Select Tools")
    )
    dialog.open_tool_selector_btn.setProperty("panelActionButton", True)
    dialog.open_tool_selector_btn.setMinimumWidth(280)
    dialog.open_tool_selector_btn.setMaximumWidth(380)
    dialog.open_tool_selector_btn.setFixedHeight(34)
    dialog.open_tool_selector_btn.clicked.connect(dialog._open_tool_selector)

    toolbar = QHBoxLayout()
    toolbar.setContentsMargins(0, 0, 0, 0)
    toolbar.setSpacing(8)

    _is_single_spindle = dialog.machine_profile.spindle_count == 1
    dialog.op20_tools_checkbox = QCheckBox(
        dialog._t("work_editor.tools.include_op20", "Include OP20 tools")
    )
    apply_shared_checkbox_style(dialog.op20_tools_checkbox, indicator_size=16, min_height=30)
    dialog.op20_tools_checkbox.setFixedHeight(30)
    dialog.op20_tools_checkbox.setChecked(getattr(dialog, '_op20_tools_enabled', False))
    dialog.op20_tools_checkbox.setVisible(_is_single_spindle)
    left_controls = QWidget()
    left_controls_layout = QHBoxLayout(left_controls)
    left_controls_layout.setContentsMargins(0, 0, 0, 0)
    left_controls_layout.setSpacing(10)
    left_controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    left_controls_layout.addWidget(dialog.op20_tools_checkbox, 0)

    dialog.print_pots_checkbox = QCheckBox(
        dialog._t("work_editor.tools.print_pot_numbers", "Print Pot Numbers")
    )
    apply_shared_checkbox_style(dialog.print_pots_checkbox, indicator_size=16, min_height=30)
    dialog.print_pots_checkbox.setFixedHeight(30)
    dialog.print_pots_checkbox.setVisible(dialog.machine_profile.supports_print_pots)
    print_pots_row = _build_eliding_checkbox(
        dialog.print_pots_checkbox,
        dialog._t("work_editor.tools.print_pot_numbers", "Print Pot Numbers"),
    )
    print_pots_row.setVisible(dialog.machine_profile.supports_print_pots)
    left_controls_layout.addWidget(print_pots_row, 1)

    toolbar.addWidget(left_controls, 1)
    toolbar.addWidget(dialog.open_tool_selector_btn, 0, Qt.AlignHCenter)

    right_controls = QWidget()
    right_controls_layout = QHBoxLayout(right_controls)
    right_controls_layout.setContentsMargins(0, 0, 0, 0)
    right_controls_layout.setSpacing(0)
    right_controls_layout.addStretch(1)
    right_controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    toolbar.addWidget(right_controls, 1)

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
    right_controls_layout.addWidget(dialog.edit_pots_btn, 0)

    dialog.print_pots_checkbox.toggled.connect(
        lambda checked: dialog.edit_pots_btn.setVisible(
            dialog.machine_profile.supports_print_pots and checked
        )
    )
    dialog.print_pots_checkbox.toggled.connect(dialog._on_print_pots_toggled)

    layout.addLayout(toolbar)

    tools_scroll = QScrollArea()
    tools_scroll.setProperty("toolIdsScrollArea", True)
    tools_scroll.setWidgetResizable(True)
    tools_scroll.setFrameShape(QFrame.NoFrame)
    tools_scroll.setMinimumHeight(360)
    tools_scroll_content = QWidget()
    tools_scroll_content.setObjectName("toolIdsScrollContent")
    tools_scroll_content.setAttribute(Qt.WA_StyledBackground, False)
    tools_scroll.viewport().setAutoFillBackground(False)
    tools_scroll_layout = QVBoxLayout(tools_scroll_content)
    tools_scroll_layout.setContentsMargins(0, 0, 0, 0)
    tools_scroll_layout.setSpacing(10)
    tools_scroll.setWidget(tools_scroll_content)

    _is_single_sp_tools = dialog.machine_profile.spindle_count == 1
    for head in dialog.machine_profile.heads:
        # Main/sub columns of the same head must stay in lockstep with one backing
        # assignment store so drag/drop and selector callbacks stay deterministic.
        shared_assignments = {"main": [], "sub": []}
        if _is_single_sp_tools:
            _main_lbl = dialog._t("work_editor.tools.op10_tools", "OP10 tools")
            _sub_lbl  = dialog._t("work_editor.tools.op20_tools", "OP20 tools")
        else:
            _main_lbl = dialog._t("work_editor.tools.main_spindle_tools", "Main spindle tools")
            _sub_lbl  = dialog._t("work_editor.tools.sub_spindle_tools", "Sub spindle tools")
        main_ordered = ordered_tool_list_cls(_main_lbl, head.key, translate=dialog._t)
        sub_ordered  = ordered_tool_list_cls(_sub_lbl,  head.key, translate=dialog._t)
        main_ordered.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sub_ordered.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        main_ordered.set_list_scrolling_enabled(False)
        sub_ordered.set_list_scrolling_enabled(False)
        # Single-spindle: OP20 column hidden until user enables it via checkbox.
        if _is_single_sp_tools:
            sub_ordered.setVisible(getattr(dialog, '_op20_tools_enabled', False))
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

        head_title = dialog._head_label(head.key, head.label_default)
        head_block = QWidget()
        head_block.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        head_block_layout = QVBoxLayout(head_block)
        head_block_layout.setContentsMargins(0, 0, 0, 0)
        head_block_layout.setSpacing(4)

        head_label = QLabel(head_title)
        head_label.setStyleSheet("font-size: 20px; font-weight: 700; padding-left: 2px;")
        head_block_layout.addWidget(head_label)

        columns_row = QHBoxLayout()
        columns_row.setContentsMargins(0, 0, 0, 0)
        columns_row.setSpacing(10)
        columns_row.addWidget(main_ordered, 1, Qt.AlignTop)
        columns_row.addWidget(sub_ordered, 1, Qt.AlignTop)
        head_block_layout.addLayout(columns_row)
        tools_scroll_layout.addWidget(head_block)

    tools_scroll_layout.addStretch(1)

    tool_ids_scroll_surface = QFrame(dialog.tools_tab)
    tool_ids_scroll_surface.setProperty("toolIdsScrollSurface", True)
    tool_ids_scroll_surface_layout = QVBoxLayout(tool_ids_scroll_surface)
    tool_ids_scroll_surface_layout.setContentsMargins(8, 8, 8, 8)
    tool_ids_scroll_surface_layout.setSpacing(0)
    tool_ids_scroll_surface_layout.addWidget(tools_scroll, 1)

    layout.addWidget(tool_ids_scroll_surface, 2)

    dialog.shared_tool_actions = QFrame(dialog.tools_tab)
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
    # Wire OP20 tools checkbox (single-spindle only) to show/hide all sub columns.
    if _is_single_sp_tools and hasattr(dialog, 'op20_tools_checkbox'):
        def _apply_op20_tools(checked: bool, _d=dialog):
            _d._op20_tools_enabled = checked
            _d._sync_tool_head_view()
        dialog.op20_tools_checkbox.toggled.connect(_apply_op20_tools)

    sync_tool_head_view(dialog)
    update_shared_tool_actions(dialog)


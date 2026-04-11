"""Tab builders for the Tool Editor components and spare parts pages.

The dialog keeps the behavior and controller methods; this module only
constructs the widgets, assigns them back onto the dialog, and wires the
existing callbacks.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import TOOL_ICONS_DIR
from shared.editor_helpers import style_icon_action_button, style_move_arrow_button
from ui.widgets.parts_table import PartsTable

__all__ = ["build_components_tab", "build_spare_parts_tab"]


def _t(dialog, key: str, default: str | None = None, **kwargs) -> str:
    return dialog._t(key, default, **kwargs)


def _configure_parts_table(table: PartsTable, *, hide_column: int | None, widths: dict[int, int], minimum_height: int = 320):
    """Apply the same table behavior used by the current dialog."""
    table.setSelectionMode(PartsTable.ExtendedSelection)
    table.setEditTriggers(
        QAbstractItemView.DoubleClicked
        | QAbstractItemView.SelectedClicked
        | QAbstractItemView.EditKeyPressed
        | QAbstractItemView.AnyKeyPressed
    )
    table.horizontalHeader().setStretchLastSection(False)
    header = table.horizontalHeader()
    for column, mode in widths.items():
        header.setSectionResizeMode(column, mode)
    table.verticalHeader().setDefaultSectionSize(32)
    table.verticalHeader().setMinimumSectionSize(28)
    table.setMinimumHeight(minimum_height)
    if hide_column is not None:
        table.setColumnHidden(hide_column, True)


def _build_parts_panel(titleless_table: QWidget) -> QFrame:
    panel = QFrame()
    panel.setProperty("editorPartsPanel", True)
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(8, 10, 8, 8)
    panel_layout.setSpacing(8)
    panel_layout.addWidget(titleless_table, 1)
    return panel


def build_components_tab(dialog, root_tabs) -> QWidget:
    """Build the COMPONENTS tab and wire it to the dialog callbacks."""
    parts_tab = QWidget()
    parts_tab.setProperty("editorPageSurface", True)
    parts_tab_layout = QVBoxLayout(parts_tab)
    parts_tab_layout.setContentsMargins(18, 18, 18, 18)
    parts_tab_layout.setSpacing(8)

    parts_panel = QFrame()
    parts_panel.setProperty("editorPartsPanel", True)
    parts_panel_layout = QVBoxLayout(parts_panel)
    parts_panel_layout.setContentsMargins(8, 10, 8, 8)
    parts_panel_layout.setSpacing(8)

    dialog.parts_table = PartsTable([
        _t(dialog, "tool_editor.table.role", "Role"),
        _t(dialog, "tool_editor.table.part_name", "Label"),
        _t(dialog, "tool_editor.table.code", "Code"),
        _t(dialog, "tool_editor.table.link", "Link"),
        _t(dialog, "tool_editor.table.group", "Group"),
    ])
    dialog.parts_table.set_column_keys(["role", "label", "code", "link", "group"])
    dialog.parts_table.setObjectName("editorPartsTable")
    _configure_parts_table(
        dialog.parts_table,
        hide_column=0,
        widths={
            0: QHeaderView.Interactive,
            1: QHeaderView.Interactive,
            2: QHeaderView.Interactive,
            3: QHeaderView.Stretch,
            4: QHeaderView.Interactive,
        },
    )
    dialog.parts_table.setColumnWidth(0, 90)
    dialog.parts_table.setColumnWidth(1, 190)
    dialog.parts_table.setColumnWidth(2, 230)
    dialog.parts_table.setColumnWidth(4, 120)
    parts_panel_layout.addWidget(dialog.parts_table, 1)
    parts_tab_layout.addWidget(parts_panel, 1)

    parts_btn_bar = QFrame()
    parts_btn_bar.setProperty("editorButtonBar", True)
    p_btns = QHBoxLayout(parts_btn_bar)
    p_btns.setContentsMargins(2, 6, 2, 2)
    p_btns.setSpacing(8)

    dialog.add_part_btn = QPushButton()
    dialog.remove_part_btn = QPushButton()
    style_icon_action_button(
        dialog.add_part_btn,
        TOOL_ICONS_DIR / "Plus_icon.svg",
        _t(dialog, "tool_editor.action.add_component", "Add component"),
    )
    style_icon_action_button(
        dialog.remove_part_btn,
        TOOL_ICONS_DIR / "remove.svg",
        _t(dialog, "tool_editor.action.remove_selected_part", "Remove selected part"),
        danger=True,
    )

    dialog.part_up_btn = QPushButton()
    dialog.part_down_btn = QPushButton()
    style_move_arrow_button(
        dialog.part_up_btn,
        _t(dialog, "work_editor.tools.move_up", "\u25b2"),
        _t(dialog, "tool_editor.tooltip.move_row_up", "Move selected row up"),
    )
    style_move_arrow_button(
        dialog.part_down_btn,
        _t(dialog, "work_editor.tools.move_down", "\u25bc"),
        _t(dialog, "tool_editor.tooltip.move_row_down", "Move selected row down"),
    )

    dialog.pick_part_btn = dialog._make_arrow_button(
        "menu_open.svg",
        _t(dialog, "tool_editor.tooltip.pick_additional_part", "Pick additional part from existing tools"),
    )
    dialog.group_btn = QPushButton()
    style_icon_action_button(
        dialog.group_btn,
        TOOL_ICONS_DIR / "assemblies_icon.svg",
        _t(dialog, "tool_editor.action.group_parts", "Group selected parts"),
    )
    dialog.group_btn.setVisible(True)

    dialog.group_name_edit = QLineEdit()
    dialog.group_name_edit.setPlaceholderText(_t(dialog, "tool_editor.placeholder.group_name", "Group name..."))
    dialog.group_name_edit.setVisible(False)
    dialog.group_name_edit.setMinimumHeight(34)
    dialog.group_name_edit.setMaximumWidth(160)

    dialog.group_hint_label = QLabel(_t(dialog, "tool_editor.hint.press_enter_to_add", "Press Enter to add"))
    dialog.group_hint_label.setVisible(False)
    dialog.group_hint_label.setStyleSheet(
        "background: transparent; font-size: 12px; color: #7a8a9a; font-style: italic;"
    )

    dialog.group_select_hint_label = QLabel(
        _t(dialog, "tool_editor.hint.select_multiple", "Select part(s) to make a group")
    )
    dialog.group_select_hint_label.setStyleSheet(
        "background: transparent; font-size: 12px; color: #9aabb8; font-style: italic;"
    )

    # The dialog remains the source of truth for all component actions.
    dialog.add_part_btn.clicked.connect(lambda: dialog._add_component_row("holder"))
    dialog.remove_part_btn.clicked.connect(dialog._remove_component_row)
    dialog.part_up_btn.clicked.connect(lambda: dialog._move_component_row(-1))
    dialog.part_down_btn.clicked.connect(lambda: dialog._move_component_row(1))
    dialog.pick_part_btn.clicked.connect(dialog._pick_additional_part)
    dialog.group_btn.clicked.connect(dialog._toggle_group)
    dialog.group_name_edit.installEventFilter(dialog)
    dialog.parts_table.itemSelectionChanged.connect(dialog._update_group_button_visibility)
    dialog.parts_table.itemChanged.connect(dialog._schedule_spare_component_refresh)

    p_btns.addWidget(dialog.add_part_btn)
    p_btns.addWidget(dialog.remove_part_btn)
    p_btns.addWidget(dialog.part_up_btn)
    p_btns.addWidget(dialog.part_down_btn)
    p_btns.addWidget(dialog.group_btn)
    p_btns.addWidget(dialog.group_name_edit)
    p_btns.addWidget(dialog.group_hint_label)
    p_btns.addWidget(dialog.group_select_hint_label)
    p_btns.addStretch(1)
    p_btns.addWidget(dialog.pick_part_btn)
    parts_tab_layout.addWidget(parts_btn_bar)

    root_tabs.addTab(parts_tab, _t(dialog, "tool_editor.tab.components", "Components"))
    return parts_tab


def build_spare_parts_tab(dialog, root_tabs) -> QWidget:
    """Build the SPARE PARTS tab and wire it to the dialog callbacks."""
    spare_tab = QWidget()
    spare_tab.setProperty("editorPageSurface", True)
    spare_tab_layout = QVBoxLayout(spare_tab)
    spare_tab_layout.setContentsMargins(18, 18, 18, 18)
    spare_tab_layout.setSpacing(8)

    spare_panel = QFrame()
    spare_panel.setProperty("editorPartsPanel", True)
    spare_panel_layout = QVBoxLayout(spare_panel)
    spare_panel_layout.setContentsMargins(8, 10, 8, 8)
    spare_panel_layout.setSpacing(8)

    dialog.spare_parts_table = PartsTable([
        _t(dialog, "tool_editor.table.part_name", "Part name"),
        _t(dialog, "tool_editor.table.code", "Code"),
        _t(dialog, "tool_editor.table.link", "Link"),
        _t(dialog, "tool_editor.table.linked_component", "Linked Component"),
        _t(dialog, "tool_editor.table.group", "Group"),
    ])
    dialog.spare_parts_table.set_column_keys(["name", "code", "link", "linked_component", "group"])
    dialog.spare_parts_table.set_read_only_columns(["linked_component"])
    dialog.spare_parts_table.setObjectName("editorSparePartsTable")
    dialog.spare_parts_table.setSelectionMode(PartsTable.ExtendedSelection)
    dialog.spare_parts_table.setEditTriggers(
        QAbstractItemView.DoubleClicked
        | QAbstractItemView.SelectedClicked
        | QAbstractItemView.EditKeyPressed
        | QAbstractItemView.AnyKeyPressed
    )
    dialog.spare_parts_table.setCornerButtonEnabled(False)
    spare_header = dialog.spare_parts_table.horizontalHeader()
    spare_header.setStretchLastSection(False)
    spare_header.setSectionResizeMode(0, QHeaderView.Interactive)
    spare_header.setSectionResizeMode(1, QHeaderView.Interactive)
    spare_header.setSectionResizeMode(2, QHeaderView.Stretch)
    spare_header.setSectionResizeMode(3, QHeaderView.Interactive)
    spare_header.setSectionResizeMode(4, QHeaderView.Interactive)
    dialog.spare_parts_table.setColumnWidth(0, 190)
    dialog.spare_parts_table.setColumnWidth(1, 220)
    dialog.spare_parts_table.setColumnWidth(3, 200)
    dialog.spare_parts_table.setColumnWidth(4, 120)
    dialog.spare_parts_table.verticalHeader().setDefaultSectionSize(32)
    dialog.spare_parts_table.verticalHeader().setMinimumSectionSize(28)
    dialog.spare_parts_table.setMinimumHeight(320)
    dialog.spare_parts_table.setColumnHidden(4, True)
    spare_panel_layout.addWidget(dialog.spare_parts_table, 1)
    spare_tab_layout.addWidget(spare_panel, 1)

    spare_btn_bar = QFrame()
    spare_btn_bar.setProperty("editorButtonBar", True)
    s_btns = QHBoxLayout(spare_btn_bar)
    s_btns.setContentsMargins(2, 6, 2, 2)
    s_btns.setSpacing(8)

    dialog.add_spare_btn = QPushButton()
    dialog.remove_spare_btn = QPushButton()
    style_icon_action_button(
        dialog.add_spare_btn,
        TOOL_ICONS_DIR / "Plus_icon.svg",
        _t(dialog, "tool_editor.action.add_spare_part", "Add spare part"),
    )
    style_icon_action_button(
        dialog.remove_spare_btn,
        TOOL_ICONS_DIR / "remove.svg",
        _t(dialog, "tool_editor.action.remove_selected_part", "Remove selected part"),
        danger=True,
    )

    dialog.spare_up_btn = QPushButton()
    dialog.spare_down_btn = QPushButton()
    style_move_arrow_button(
        dialog.spare_up_btn,
        _t(dialog, "work_editor.tools.move_up", "\u25b2"),
        _t(dialog, "tool_editor.tooltip.move_row_up", "Move selected row up"),
    )
    style_move_arrow_button(
        dialog.spare_down_btn,
        _t(dialog, "work_editor.tools.move_down", "\u25bc"),
        _t(dialog, "tool_editor.tooltip.move_row_down", "Move selected row down"),
    )

    dialog.pick_spare_btn = dialog._make_arrow_button(
        "menu_open.svg",
        _t(dialog, "tool_editor.tooltip.pick_additional_part", "Pick additional part from existing tools"),
    )
    dialog.link_spare_btn = QPushButton()
    style_icon_action_button(
        dialog.link_spare_btn,
        TOOL_ICONS_DIR / "assemblies_icon.svg",
        _t(dialog, "tool_editor.action.link_spare_to_component", "Link to selected component"),
    )

    dialog.spare_link_hint_label = QLabel(
        _t(
            dialog,
            "tool_editor.hint.link_spares_from_table",
            "Link part(s) to components by selecting them in the table",
        )
    )
    dialog.spare_link_hint_label.setStyleSheet(
        "background: transparent; font-size: 12px; color: #9aabb8; font-style: italic;"
    )

    dialog.add_spare_btn.clicked.connect(dialog._add_spare_part_row)
    dialog.remove_spare_btn.clicked.connect(dialog.spare_parts_table.remove_selected_row)
    dialog.spare_up_btn.clicked.connect(lambda: dialog.spare_parts_table.move_selected_row(-1))
    dialog.spare_down_btn.clicked.connect(lambda: dialog.spare_parts_table.move_selected_row(1))
    dialog.pick_spare_btn.clicked.connect(dialog._pick_spare_part)
    dialog.link_spare_btn.clicked.connect(dialog._link_spares_to_selected_component)

    s_btns.addWidget(dialog.add_spare_btn)
    s_btns.addWidget(dialog.remove_spare_btn)
    s_btns.addWidget(dialog.spare_up_btn)
    s_btns.addWidget(dialog.spare_down_btn)
    s_btns.addWidget(dialog.link_spare_btn)
    s_btns.addWidget(dialog.spare_link_hint_label)
    s_btns.addStretch(1)
    s_btns.addWidget(dialog.pick_spare_btn)
    spare_tab_layout.addWidget(spare_btn_bar)

    root_tabs.addTab(spare_tab, _t(dialog, "tool_editor.tab.spare_parts", "Spare parts"))
    return spare_tab

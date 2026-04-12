"""General-tab builder for ToolEditorDialog.

This keeps the main dialog smaller by moving the large widget-construction
block into a single place without changing the dialog-owned helper methods.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import ALL_TOOL_TYPES
from shared.ui.helpers.editor_helpers import apply_secondary_button_theme

__all__ = ["build_general_tab"]


def _raise_header_font(label: QLabel) -> None:
    """Keep the general-tab header visually closer to the detail title style."""
    font = label.font()
    font.setPointSizeF(max(15.0, font.pointSizeF() + 1.5))
    label.setFont(font)


def _build_header(dialog) -> QFrame:
    header = QFrame()
    header.setProperty("detailHeader", True)

    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(14, 12, 14, 12)
    header_layout.setSpacing(4)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(10)

    dialog.editor_header_title = QLabel(dialog._t("tool_editor.header.new_tool", "New tool"))
    dialog.editor_header_title.setProperty("detailHeroTitle", True)
    dialog.editor_header_title.setWordWrap(True)
    dialog.editor_header_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    dialog.editor_header_title.setStyleSheet("font-size: 18px; font-weight: 700;")
    _raise_header_font(dialog.editor_header_title)

    dialog.editor_header_id = QLabel("")
    dialog.editor_header_id.setProperty("detailHeroTitle", True)
    dialog.editor_header_id.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    dialog.editor_header_id.setStyleSheet("font-size: 18px; font-weight: 700;")
    _raise_header_font(dialog.editor_header_id)

    title_row.addWidget(dialog.editor_header_title, 1)
    title_row.addWidget(dialog.editor_header_id, 0, Qt.AlignRight)

    meta_row = QHBoxLayout()
    meta_row.setContentsMargins(0, 0, 0, 0)
    dialog.editor_type_badge = QLabel("")
    dialog.editor_type_badge.setProperty("toolBadge", True)
    meta_row.addWidget(dialog.editor_type_badge, 0, Qt.AlignLeft)
    meta_row.addStretch(1)

    header_layout.addLayout(title_row)
    header_layout.addLayout(meta_row)
    return header


def _build_identity_group(dialog) -> QWidget:
    dialog.tool_id = QLineEdit()

    dialog.tool_head = QPushButton(dialog._localized_tool_head("HEAD1"))
    dialog.tool_head.setCheckable(True)
    dialog.tool_head.clicked.connect(dialog._toggle_tool_head)
    apply_secondary_button_theme(dialog.tool_head)
    dialog.tool_head.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    dialog.tool_head.setFixedWidth(118)

    dialog.spindle_orientation_btn = QPushButton(dialog._localized_spindle_orientation("main"))
    dialog.spindle_orientation_btn.setCheckable(True)
    dialog.spindle_orientation_btn.clicked.connect(dialog._toggle_spindle_orientation)
    dialog.spindle_orientation_btn.setContextMenuPolicy(Qt.CustomContextMenu)
    dialog.spindle_orientation_btn.customContextMenuRequested.connect(
        lambda _pos: dialog._set_spindle_orientation_both()
    )
    apply_secondary_button_theme(dialog.spindle_orientation_btn)
    dialog.spindle_orientation_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    dialog.spindle_orientation_btn.setFixedWidth(148)

    dialog.tool_type = QComboBox()
    for raw_type in ALL_TOOL_TYPES:
        dialog.tool_type.addItem(dialog._localized_tool_type(raw_type), raw_type)
    dialog.tool_type.currentTextChanged.connect(dialog._update_tool_type_fields)
    dialog._style_combo(dialog.tool_type)
    dialog.tool_type.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    dialog.tool_type.setFixedWidth(330)
    dialog.tool_type.setMaxVisibleItems(8)
    dialog._configure_combo_popup(dialog.tool_type, max_rows=8, row_height=44)

    dialog.tool_type_row = QWidget()
    dialog.tool_type_row.setProperty("editorInlineRow", True)
    tool_type_row_layout = QHBoxLayout(dialog.tool_type_row)
    tool_type_row_layout.setContentsMargins(0, 0, 0, 0)
    tool_type_row_layout.setSpacing(10)
    tool_type_row_layout.addWidget(dialog.tool_type)
    tool_type_row_layout.addWidget(dialog.tool_head)
    tool_type_row_layout.addWidget(dialog.spindle_orientation_btn)
    tool_type_row_layout.addStretch(1)

    dialog.description = QLineEdit()
    dialog.default_pot = QLineEdit()

    dialog._style_general_editor(dialog.tool_id)
    dialog._style_general_editor(dialog.tool_head)
    dialog._style_general_editor(dialog.tool_type)
    dialog._style_general_editor(dialog.description)
    dialog._style_general_editor(dialog.default_pot)

    group = dialog._build_field_group([
        dialog._build_edit_field(dialog._t("tool_library.row.tool_id", "Tool ID"), dialog.tool_id),
        dialog._build_edit_field(dialog._t("tool_editor.field.tool_type", "Tool type"), dialog.tool_type_row),
        dialog._build_edit_field(dialog._t("tool_editor.field.default_pot", "Default pot"), dialog.default_pot),
        dialog._build_edit_field(dialog._t("setup_page.field.description", "Description"), dialog.description),
    ])
    return group


def _build_geometry_group(dialog) -> QWidget:
    dialog.geom_x = QLineEdit()
    dialog.geom_z = QLineEdit()
    dialog.b_axis_angle = QLineEdit()
    dialog.radius = QLineEdit()
    dialog.nose_corner_radius = QLineEdit()
    dialog.mill_cutting_edges = QLineEdit()
    dialog.drill_nose_angle = QLineEdit()
    dialog.drill_row_label = QLabel(dialog._t("tool_library.field.nose_angle", "Nose angle"))
    dialog.mill_row_label = QLabel(dialog._t("tool_library.field.number_of_flutes", "Number of flutes"))

    dialog.corner_or_nose_label = QLabel(dialog._t("tool_library.field.nose_corner_radius", "Nose R / Corner R"))
    dialog.corner_or_nose_field = dialog._build_edit_field("", dialog.nose_corner_radius, key_label=dialog.corner_or_nose_label)
    dialog.mill_field = dialog._build_edit_field("", dialog.mill_cutting_edges, key_label=dialog.mill_row_label)
    dialog.mill_field.setVisible(False)
    dialog.radius_field = dialog._build_edit_field(dialog._t("tool_library.field.radius", "Radius"), dialog.radius)
    dialog.b_axis_field = dialog._build_edit_field(dialog._t("tool_library.field.b_axis_angle", "B-axis angle"), dialog.b_axis_angle)
    dialog.b_axis_field.setVisible(False)
    dialog.drill_field = dialog._build_edit_field("", dialog.drill_nose_angle, key_label=dialog.drill_row_label)

    for widget in [
        dialog.geom_x,
        dialog.geom_z,
        dialog.b_axis_angle,
        dialog.radius,
        dialog.nose_corner_radius,
        dialog.mill_cutting_edges,
        dialog.drill_nose_angle,
    ]:
        dialog._style_general_editor(widget)

    return dialog._build_field_group([
        dialog._build_edit_field(dialog._t("tool_library.field.geom_x", "Geom X"), dialog.geom_x),
        dialog._build_edit_field(dialog._t("tool_library.field.geom_z", "Geom Z"), dialog.geom_z),
        dialog.radius_field,
        dialog.b_axis_field,
        dialog.corner_or_nose_field,
        dialog.mill_field,
    ])


def _build_holder_group(dialog) -> QWidget:
    dialog.holder_code = QLineEdit()
    dialog.holder_link = QLineEdit()
    dialog.holder_add_element = QLineEdit()
    dialog.holder_add_element_link = QLineEdit()
    dialog.holder_code_row = dialog._build_picker_row(
        dialog.holder_code,
        dialog._pick_holder_component,
        dialog._t("tool_editor.tooltip.pick_holder", "Pick holder from existing tools"),
    )

    dialog.holder_code_field = dialog._build_edit_field(dialog._t("tool_library.field.holder_code", "Holder code"), dialog.holder_code_row)
    dialog.holder_link_field = dialog._build_edit_field(dialog._t("tool_editor.field.holder_link", "Holder link"), dialog.holder_link)
    dialog.holder_add_field = dialog._build_edit_field(dialog._t("tool_library.field.add_element", "Add. Element"), dialog.holder_add_element)
    dialog.holder_add_link_field = dialog._build_edit_field(dialog._t("tool_editor.field.add_element_link", "Add. Element link"), dialog.holder_add_element_link)
    dialog.holder_link_field.setVisible(False)
    dialog.holder_add_link_field.setVisible(False)

    for widget in [
        dialog.holder_code,
        dialog.holder_link,
        dialog.holder_add_element,
        dialog.holder_add_element_link,
    ]:
        dialog._style_general_editor(widget)

    return dialog._build_field_group([
        dialog.holder_code_field,
        dialog.holder_link_field,
        dialog.holder_add_field,
        dialog.holder_add_link_field,
    ])


def _build_cutting_group(dialog) -> QWidget:
    dialog.cutting_type = QComboBox()
    dialog.cutting_type.setObjectName("cuttingTypeCombo")
    for raw_cutting in ["Insert", "Drill", "Center drill", "Mill"]:
        dialog.cutting_type.addItem(dialog._localized_cutting_type(raw_cutting), raw_cutting)
    dialog.cutting_type.currentTextChanged.connect(dialog._update_tool_type_fields)
    dialog._style_combo(dialog.cutting_type)
    dialog.cutting_type.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    dialog.cutting_type.setMinimumWidth(180)

    dialog.cutting_type_row = QWidget()
    dialog.cutting_type_row.setProperty("editorInlineRow", True)
    cutting_type_row_layout = QHBoxLayout(dialog.cutting_type_row)
    cutting_type_row_layout.setContentsMargins(0, 0, 0, 0)
    cutting_type_row_layout.addWidget(dialog.cutting_type)
    cutting_type_row_layout.addStretch(1)

    dialog.cutting_code = QLineEdit()
    dialog.cutting_link = QLineEdit()
    dialog.cutting_add_element = QLineEdit()
    dialog.cutting_add_element_link = QLineEdit()
    dialog.cutting_code_row = dialog._build_picker_row(
        dialog.cutting_code,
        dialog._pick_cutting_component,
        dialog._t("tool_editor.tooltip.pick_cutting", "Pick cutting component from existing tools"),
    )
    dialog.cutting_code_label = QLabel(
        dialog._t(
            "tool_library.field.cutting_code",
            "{cutting_type} code",
            cutting_type=dialog._localized_cutting_type("Insert"),
        )
    )
    dialog.cutting_code_field = dialog._build_edit_field("", dialog.cutting_code_row, key_label=dialog.cutting_code_label)
    dialog.cutting_link_field = dialog._build_edit_field(dialog._t("tool_editor.field.cutting_component_link", "Cutting component link"), dialog.cutting_link)
    dialog.cutting_add_field = dialog._build_edit_field(dialog._t("tool_editor.field.add_cutting_any", "Add. Insert/Drill/Mill"), dialog.cutting_add_element)
    dialog.cutting_add_link_field = dialog._build_edit_field(dialog._t("tool_editor.field.add_cutting_any_link", "Add. Insert/Drill/Mill link"), dialog.cutting_add_element_link)
    dialog.cutting_link_field.setVisible(False)
    dialog.cutting_add_link_field.setVisible(False)

    dialog._style_general_editor(dialog.cutting_type)
    dialog._style_general_editor(dialog.cutting_code)
    dialog._style_general_editor(dialog.cutting_link)
    dialog._style_general_editor(dialog.cutting_add_element)
    dialog._style_general_editor(dialog.cutting_add_element_link)

    return dialog._build_field_group([
        dialog._build_edit_field(dialog._t("tool_editor.field.cutting_component_type", "Cutting component type"), dialog.cutting_type_row),
        dialog.cutting_code_field,
        dialog.cutting_link_field,
        dialog.cutting_add_field,
        dialog.cutting_add_link_field,
        dialog.drill_field,
    ])


def _build_notes_group(dialog) -> QWidget:
    dialog.notes = QTextEdit()
    dialog.notes.setAcceptRichText(False)
    dialog.notes.setLineWrapMode(QTextEdit.WidgetWidth)
    dialog.notes.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    dialog.notes.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    dialog.notes.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    dialog.notes.setPlaceholderText(dialog._t("tool_editor.placeholder.notes_shift_enter", "Use Shift+Enter for new line"))
    dialog.notes.setStyleSheet("")
    dialog.notes.textChanged.connect(dialog._update_notes_editor_height)

    dialog._style_general_editor(dialog.notes)
    return dialog._build_field_group([
        dialog._build_edit_field(dialog._t("tool_library.field.notes", "Notes"), dialog.notes),
    ])


def build_general_tab(dialog, root_tabs) -> QWidget:
    """Build and register the General tab on ``root_tabs``."""
    general_tab = QWidget()
    general_tab.setProperty("editorPageSurface", True)

    general_layout = QVBoxLayout(general_tab)
    general_layout.setContentsMargins(0, 0, 0, 0)
    general_layout.setSpacing(0)

    general_scroll = QScrollArea()
    dialog.general_scroll = general_scroll
    general_scroll.setWidgetResizable(True)
    general_scroll.setFrameShape(QFrame.NoFrame)
    general_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    general_layout.addWidget(general_scroll, 1)

    general_content = QWidget()
    general_content.setProperty("editorFieldsViewport", True)
    general_content.setProperty("editorPageSurface", True)
    general_content_layout = QVBoxLayout(general_content)
    general_content_layout.setContentsMargins(0, 0, 0, 0)
    general_content_layout.setSpacing(0)
    general_scroll.setWidget(general_content)

    form_frame = QFrame()
    form_frame.setProperty("subCard", True)
    form_layout = QVBoxLayout(form_frame)
    form_layout.setContentsMargins(14, 14, 14, 14)
    form_layout.setSpacing(10)

    form_layout.addWidget(_build_header(dialog))

    dialog.general_fields_grid = None  # Groups handle layout directly.

    identity_group = _build_identity_group(dialog)
    geometry_group = _build_geometry_group(dialog)
    holder_group = _build_holder_group(dialog)
    cutting_group = _build_cutting_group(dialog)
    notes_group = _build_notes_group(dialog)

    dialog._general_field_order = []

    form_layout.addWidget(identity_group)
    form_layout.addWidget(geometry_group)
    holder_group.setVisible(False)
    form_layout.addWidget(holder_group)
    cutting_group.setVisible(False)
    form_layout.addWidget(cutting_group)
    form_layout.addWidget(notes_group)

    general_content_layout.addWidget(form_frame)
    general_content_layout.addStretch(1)
    root_tabs.addTab(general_tab, dialog._t("tool_editor.tab.general", "General"))
    return general_tab


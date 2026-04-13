"""QUICK REFERENCE: DetailPanelBuilder API

One-page cheat sheet for DetailPanelBuilder class.
"""

# ============================================================================
# INSTANTIATION
# ============================================================================

from ui.home_page_support.detail_panel_builder import DetailPanelBuilder

# In HomePage.__init__():
self._detail_builder = DetailPanelBuilder(self)


# ============================================================================
# PUBLIC API
# ============================================================================

class DetailPanelBuilder:
    """Coordinator for rendering Tool details into HomePage detail panel."""

    def __init__(self, page: HomePage) -> None:
        """Initialize builder with HomePage reference.
        
        Args:
            page: HomePage instance providing rendering context
        """

    def populate_details(self, tool: dict | None) -> None:
        """Main entry point: render all tool details to detail panel.
        
        Args:
            tool: Tool dict {description, id, tool_type, tool_head, etc.}
                  or None to show empty state
        
        Clears detail_layout and adds:
          1. Header frame (title + ID + badges)
          2. Info grid (specifications)
          3. Components panel (holder, cutting, spares)
          4. Preview panel (3D viewer)
          
        Example:
            tool = self._get_selected_tool()
            self._detail_builder.populate_details(tool)
        """


# ============================================================================
# HOMEPAGE INTEGRATION
# ============================================================================

# REPLACE ALL:
self.populate_details(tool)

# WITH:
self._detail_builder.populate_details(tool)

# Call sites in HomePage:
# - _on_current_changed()      [list selection]
# - _on_double_clicked()       [list double-click]
# - _save_from_dialog()        [after save]
# - delete_tool()              [after delete]
# - toggle_details()           [detail toggle]
# - expand_details()           [detail show]
# - collapse_details()         [detail hide]


# ============================================================================
# RENDERING CONTEXT: Methods HomePage Must Provide
# ============================================================================

# Builder calls these on self.page:

# Localization/Translation:
page._t(key, default, **kwargs) → str
page._localized_tool_type(raw_type) → str
page._localized_cutting_type(raw_type) → str
page._is_turning_drill_tool_type(raw_type) → bool

# Display:
page._tool_id_display_value(id_value) → str
page.font() → QFont  # for arrow pixmaps

# Previews & Actions:
page._load_preview_content(viewer, stl_path, label) → bool
page.part_clicked(part_dict) → None

# UI Management:
page._refresh_elided_group_title(field_group) → None

# Widget Ownership:
page.detail_layout → QVBoxLayout  # where builder adds widgets


# ============================================================================
# WIDGET STRUCTURE CREATED BY populate_details()
# ============================================================================

detail_layout
└── card (QFrame, property='subCard')
    └── QVBoxLayout
        ├── header (QFrame, property='detailHeader')
        │   └── QVBoxLayout
        │       ├── title_row (QHBoxLayout) [name label + ID label]
        │       └── meta_row (QHBoxLayout) [type badge + head badge]
        │
        ├── info_grid (QGridLayout, 6 columns)
        │   ├── field 1 (detail_field_builder creates title + value)
        │   ├── field 2 (2-column spanning)
        │   ├── field 3 (3-column spanning)
        │   └── notes_field (full width if present)
        │
        ├── components_panel (QFrame, property='subCard')
        │   └── QVBoxLayout
        │       ├── section_title ("Tool components")
        │       └── body_host (QFrame, objectName='toolComponentsBodyHost')
        │           └── item_list (QVBoxLayout)
        │               ├── component_row_1
        │               │   ├── arrow_label (collapse/expand toggle)
        │               │   ├── component_btn (link)
        │               │   └── code_label (component code)
        │               ├── spares_host_1 (hidden by default)
        │               │   ├── spare_row_1 [spare button + code]
        │               │   └── spare_row_2 [spare button + code]
        │               └── component_row_2 ...
        │
        ├── preview_panel (QFrame, property='subCard')
        │   └── QVBoxLayout
        │       ├── section_title ("Preview")
        │       └── diagram (QWidget, objectName='detailPreviewGradientHost')
        │           └── QVBoxLayout
        │               ├── viewer (StlPreviewWidget, if loaded)
        │               └── placeholder_label (if not loaded)
        │
        └── stretch


# ============================================================================
# DETAIL FIELD STRUCTURE
# ============================================================================

# Each field created by build_detail_field() from detail_fields_builder.py:

detail_field (QFrame, property='detailFieldCard')
└── QVBoxLayout
    ├── field_label (QLabel, property='detailFieldKey')
    │   └── label_text
    └── value_widget
        └── QLineEdit (read-only, single-line)
            or QLabel (multiline, word-wrapped)


# ============================================================================
# COMPONENT ROW STRUCTURE
# ============================================================================

# Each component row:

component_row (QFrame, property='editorFieldCard')
└── QHBoxLayout
    ├── arrow_label (QLabel, only if spares linked)
    │   └── pixmap (left/up toggle arrow)
    ├── component_btn (QPushButton, property='panelActionButton')
    │   └── component name (e.g., "Holder")
    ├── code_label (QLabel)
    │   └── component code (e.g., "T123")
    └── [spare rows follow if expanded]

spares_host (QFrame, initially hidden)
└── QVBoxLayout
    ├── spare_row
    │   ├── spare_btn (QPushButton)
    │   └── spare_code_label (QLabel)
    └── spare_row...


# ============================================================================
# INTERNAL METHODS (Private)
# ============================================================================

# Detail panel building:
_build_detail_header(tool) → QFrame
_build_info_grid(tool) → QGridLayout
_build_components_panel(tool, support_parts) → QFrame
_build_preview_panel(stl_path) → QFrame
_build_placeholder_details() → QFrame

# Component rendering:
_build_component_row_widget(item, display_name) → (QFrame, QLabel, str, str)
_build_component_spare_host(linked_spares) → QFrame
_wire_spare_toggle(...) → None
_add_two_box_row(info, row, ll, lv, rl, rv) → None
_add_three_box_row(info, row, l1, v1, l2, v2, l3, v3) → None

# Component data processing:
_normalized_component_items(tool) → list[dict]
_spare_index_by_component(support_parts) → dict[str, list[dict]]
_legacy_component_candidates(tool) → list[dict]
_component_key(item, fallback_idx) → str
_component_toggle_arrow_pixmaps() → (QPixmap, QPixmap)

# Cleanup:
_clear_details() → None


# ============================================================================
# TOOL DICT FORMAT
# ============================================================================

Tool dict passed to populate_details():

{
    'id': 'T123',
    'description': 'Drill 10mm',
    'tool_type': 'Drill',
    'tool_head': 'HEAD1',
    'cutting_type': 'Carbide Insert',
    
    # Spec fields:
    'cutting_diameter': '10',
    'drill_nose_angle': '118',
    'flute_length': '76.2',
    'overall_length': '135',
    'shank_diameter': '10',
    'corner_radius': '',
    'nose_corner_radius': '',  # fallback for angle
    
    # Components (new format):
    'component_items': '[
        {"role": "holder", "label": "Holder", "code": "ER11007", "group": ""},
        {"role": "cutting", "label": "Insert", "code": "DCMT1104M0", "group": ""}
    ]' or [],
    
    # Components (legacy format):
    'holder_code': 'ER11007',
    'holder_link': 'https://...',
    'holder_add_element': '',
    'cutting_code': 'DCMT1104M0',
    'cutting_link': 'https://...',
    'cutting_add_element': '',
    
    # Spare parts:
    'support_parts': '[
        {"code": "SPARE001", "name": "Spring", "component_key": "holder:ER11007"},
        ...
    ]' or [],
    
    # 3D Preview:
    'stl_path': '/path/to/tool.stl' or None,
    
    # Notes:
    'notes': 'Some notes...' or '',
    'spare_parts': 'Old notes field (fallback)',
}


# ============================================================================
# SIGNAL FLOW
# ============================================================================

User interaction:
  Tool list selection (click/arrow keys)
  └─> QListView.currentChanged(QModelIndex)
      └─> HomePage._on_current_changed(current, previous)
          ├─ Extract tool ID/UID
          ├─ If details visible:
          │   ├─ tool = self._get_selected_tool()
          │   └─> self._detail_builder.populate_details(tool)
          └─ [detail panel repaints]

User interaction:
  Double-click tool in list
  └─> QListView.doubleClicked(QModelIndex)
      └─> HomePage._on_double_clicked(index)
          ├─ If details hidden:
          │   ├─> self._detail_builder.populate_details(tool)
          │   └─> self.show_details()  [slide animation]
          └─ Else:
              └─> self.hide_details()  [slide animation]

User action:
  Save/edit tool via dialog
  └─> HomePage._save_from_dialog(dlg)
      ├─ Save to service
      ├─ Refresh list
      └─> self._detail_builder.populate_details(saved_tool)
          └─ [detail panel updates]

User action:
  Delete tool
  └─> HomePage.delete_tool()
      ├─ Confirm dialog
      ├─ Delete from service
      ├─ Refresh list
      └─> self._detail_builder.populate_details(None)
          └─ [detail panel shows placeholder]


# ============================================================================
# DEBUGGING TIPS
# ============================================================================

# Check builder is instantiated:
print(self._detail_builder)  # should be DetailPanelBuilder instance

# Check detail_layout is empty after clear:
print(self.detail_layout.count())  # should be 0 before populate_details

# Check populated widgets:
print(self.detail_layout.count())  # should be 1 after populate_details

# Check widget structure:
widget = self.detail_layout.itemAt(0).widget()
print(widget.property('subCard'))  # should be True for main card

# Debug component normalization:
components = builder._normalized_component_items(tool)
print(f"Normalized components: {len(components)}")

# Debug spare indexing:
spare_index = builder._spare_index_by_component(support_parts)
print(f"Spares: {spare_index}")

# Check rendering context:
print(self.page._t('tool_library.field.holder', 'Holder'))
print(self.page._localized_tool_type('Drill'))
"""

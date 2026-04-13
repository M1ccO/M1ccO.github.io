"""DESIGN: DetailPanelBuilder Extraction

Complete design showing:
1. DetailPanelBuilder class structure & responsibilities
2. Before/after HomePage integration
3. Signal flow: tool selection → builder
4. Method mapping (what moves, what stays)
5. Call patterns & ownership
"""

# ============================================================================
# 1. DETAILPANELBUILDER CLASS STRUCTURE
# ============================================================================

"""
Class: DetailPanelBuilder
Location: ui/home_page_support/detail_panel_builder.py
Responsibility: Coordinator for rendering Tool details into HomePage detail panel
Size: ~750 lines

Key Methods:
  - __init__(page: HomePage)
    Constructor stores reference to HomePage for rendering context (localization, widget refs)
  
  - populate_details(tool: dict | None) → None
    Main entry point. Clears and rebuilds entire detail panel.
    Signal flow: HomePage tool selection → HomePage calls builder.populate_details(tool)
    
    Steps:
      1. Call _clear_details() to reset layout
      2. If tool is None, show placeholder (empty state)
      3. Parse support_parts from tool (handle legacy JSON strings)
      4. Create main card frame with VBoxLayout
      5. Build and add Header (title + metadata row)
      6. Build and add Info Grid (specs using detail_layout_rules)
      7. Build and add Components Panel (holder, cutting, spares)
      8. Build and add Preview Panel (3D viewer)
      9. Add stretch to bottom
      10. Add card to HomePage.detail_layout

  - _build_detail_header(tool: dict) → QFrame
    Builds title/metadata row: description + tool ID + type badge + head
  
  - _build_info_grid(tool: dict) → QGridLayout
    Builds 6-column grid of tool specs (dimensions, angles, etc.)
    Uses shared apply_tool_detail_layout_rules to determine field layout
    Returns layout (not widget) for direct insertion
  
  - _build_components_panel(tool, support_parts) → QFrame
    Builds holder/cutting/spare components section
    Handles:
      - Component normalization (legacy + new format)
      - Component grouping
      - Spare parts indexing
      - Spare parts collapse/expand toggle
  
  - _build_preview_panel(stl_path) → QFrame
    Builds 3D STL viewer section
    Delegates to page._load_preview_content() for actual loading
  
  - _build_placeholder_details() → QFrame
    Shows "Select a tool to view details" when no tool selected

Helper Methods:
  - _clear_details() → None
    Clears and deletes all widgets from page.detail_layout
  
  - _component_toggle_arrow_pixmaps() → (QPixmap, QPixmap)
    Returns cached or generates left/up arrow pixmaps
  
  - _component_key(item, fallback_idx) → str
    Generates unique key for component (for spare indexing)
  
  - _normalized_component_items(tool) → list[dict]
    Normalizes component_items from tool (handles legacy format)
  
  - _spare_index_by_component(support_parts) → dict[str, list[dict]]
    Indexes spare parts by component key for lookup
  
  - _legacy_component_candidates(tool) → list[dict]
    Builds fallback component rows when tool predates component_items
  
  - _build_component_row_widget(item, display_name) → (QFrame, QLabel, str, str)
    Builds single component row: button + code label + toggle arrow
    Returns: row_card, code_label, default_style, hover_style
  
  - _build_component_spare_host(linked_spares) → QFrame
    Builds container for spare parts (initially hidden)
  
  - _wire_spare_toggle(...) → None
    Wires click handlers for spare expand/collapse
  
  - _add_two_box_row(info, row, ll, lv, rl, rv) → None
    Adds 2-column detail field row to grid (cols 0-3 and 3-6)
  
  - _add_three_box_row(info, row, l1, v1, l2, v2, l3, v3) → None
    Adds 3-column detail field row to grid (cols 0-2, 2-4, 4-6)


# ============================================================================
# 2. BEFORE/AFTER CODE: HomePage Integration
# ============================================================================

## BEFORE (Current State)
# ============================================

class HomePage(QWidget):
    def __init__(self, tool_service, export_service, settings_service, ...):
        super().__init__(parent)
        self.tool_service = tool_service
        self.export_service = export_service
        self.settings_service = settings_service
        # ... 30+ instance variables
        self._build_ui()
        self.refresh_list()

    def _build_ui(self):
        # ... build toolbar, search, filters ...
        # Build detail panel (still here, owns detail_layout, detail_panel, detail_scroll)
        self.detail_scroll = QScrollArea()
        self.detail_panel = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.addWidget(self._build_placeholder_details())

    def populate_details(self, tool):
        """~100 lines: orchestrates entire detail rendering"""
        self._clear_details()
        if not tool:
            self.detail_layout.addWidget(self._build_placeholder_details())
            return

        support_parts = tool.get('support_parts', []) if isinstance(...) else json.loads(...)
        
        card = QFrame()
        # ... build header ...
        # ... build info grid using apply_tool_detail_layout_rules ...
        layout.addWidget(self._build_components_panel(tool, support_parts))
        layout.addWidget(self._build_preview_panel(tool.get('stl_path')))

    def _build_components_panel(self, tool, support_parts):
        """~90 lines: builds components section"""
        # ... normalization, spare indexing, toggle wiring ...

    def _build_preview_panel(self, stl_path):
        """~60 lines: builds preview section"""
        # ... STL viewer loading ...

    # ~20 helper methods for component rendering
    def _normalized_component_items(self, tool): ...
    def _spare_index_by_component(support_parts): ...
    def _build_component_row_widget(self, item, display_name): ...
    # ... etc ...


## AFTER (With DetailPanelBuilder)
# ============================================

from ui.home_page_support.detail_panel_builder import DetailPanelBuilder

class HomePage(QWidget):
    def __init__(self, tool_service, export_service, settings_service, ...):
        super().__init__(parent)
        self.tool_service = tool_service
        self.export_service = export_service
        self.settings_service = settings_service
        # ... 30+ instance variables (same as before)
        self._detail_builder = DetailPanelBuilder(self)  # ← NEW: Create builder
        self._build_ui()
        self.refresh_list()

    def _build_ui(self):
        # ... build toolbar, search, filters (unchanged) ...
        # Detail panel ownership stays here (unchanged)
        self.detail_scroll = QScrollArea()
        self.detail_panel = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.addWidget(self._build_placeholder_details())

    # Signal Connections (unchanged):
    def _on_current_changed(self, current, previous):
        # if details pane is already visible, refresh its contents
        if not self._details_hidden:
            tool = self._get_selected_tool()
            self._detail_builder.populate_details(tool)  # ← CHANGED: Use builder
        if self.preview_window_btn.isChecked():
            self._sync_detached_preview(show_errors=False)

    def _on_double_clicked(self, index):
        # if detail window already open, close it; otherwise open/update
        if not self._details_hidden:
            self.hide_details()
        else:
            self._detail_builder.populate_details(self._get_selected_tool())  # ← CHANGED
            self.show_details()

    # Calls to populate_details now go through builder (multiple locations):
    #   Line 1257: self._detail_builder.populate_details(tool)
    #   Line 1328: self._detail_builder.populate_details(None)
    #   Line 1478: self._detail_builder.populate_details(None)
    #   Line 1488: self._detail_builder.populate_details(tool)
    #   Line 1502: self._detail_builder.populate_details(self._get_selected_tool())
    #   Line 2214: self._detail_builder.populate_details(saved_tool)
    #   Line 2336: self._detail_builder.populate_details(self._get_selected_tool())
    #   etc...

    # REMOVED from HomePage (now in DetailPanelBuilder):
    #   - populate_details()
    #   - _build_components_panel()
    #   - _build_preview_panel()
    #   - _build_detail_header()
    #   - _build_info_grid()
    #   - _add_two_box_row()
    #   - _add_three_box_row()
    #   - _clear_details()
    #   - _component_toggle_arrow_pixmaps()
    #   - _component_key() ← Note: still static at HomPage level for backward compat
    #   - _legacy_component_candidates()
    #   - _normalized_component_items()
    #   - _spare_index_by_component()
    #   - _build_component_row_widget()
    #   - _build_component_spare_host()
    #   - _wire_spare_toggle()

    # STAYS in HomePage (detail panel ownership):
    #   - detail_scroll (QScrollArea widget)
    #   - detail_layout (VBoxLayout for widgets)
    #   - detail_panel (QWidget container)
    #   - detail_container (parent widget)
    #   - _build_placeholder_details() ← Can move to builder too, but keeping for now
    #   - _details_hidden (state flag)
    #   - expand_details(), collapse_details(), toggle_details(), show_details(), hide_details()
    #   - part_clicked() callback (parts click handler)
    #   - _load_preview_content() (preview loading logic)


# ============================================================================
# 3. SIGNAL FLOW: Tool Selection → Detail Rendering
# ============================================================================

"""
Sequence: User clicks tool in list → Details show

1. HomePage.tool_list (QListView) emits currentChanged(QModelIndex)

2. HomePage._on_current_changed(current, previous) is called
   - Extract tool ID/UID from current index
   - If details pane not visible, return (no repaint)
   - If visible:
     → tool = self._get_selected_tool()
     → self._detail_builder.populate_details(tool)  ← BUILD DETAILS

3. DetailPanelBuilder.populate_details(tool)
   - Call self._clear_details() to remove old widgets
   - Parse support_parts
   - Build detail card with header + info grid + components + preview
   - Add to self.page.detail_layout

4. HomePage.detail_layout updates on screen
   (QWidget auto-repaints, scroll area adjusts)

5. User double-clicks tool in list

6. HomePage._on_double_clicked(index) is called
   - If details hidden:
     → self._detail_builder.populate_details(self._get_selected_tool())
     → self.show_details()  (slides in detail panel)
   - Else:
     → self.hide_details()  (slides out detail panel)

7. User saves a tool via AddEditToolDialog

8. HomePage._save_from_dialog(dlg) is called
   - Save tool via tool_service
   - Refresh list
   → self._detail_builder.populate_details(saved_tool)  ← REFRESH DETAILS

9. User clicks delete tool button

10. HomePage code calls on_delete_tool()
    → self._detail_builder.populate_details(None)  ← CLEAR DETAILS


# ============================================================================
# 4. IMPORTS & DEPENDENCIES
# ============================================================================

## New Imports in detail_panel_builder.py:
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)
from shared.ui.helpers.editor_helpers import create_titled_section
from shared.ui.stl_preview import StlPreviewWidget
from config import MILLING_TOOL_TYPES, TURNING_TOOL_TYPES
from ui.home_page_support.detail_fields_builder import build_detail_field
from ui.home_page_support.detail_layout_rules import apply_tool_detail_layout_rules

## HomePage imports (add):
from ui.home_page_support.detail_panel_builder import DetailPanelBuilder

## DetailPanelBuilder still delegates to HomePage for:
- page._t(key, default, **kwargs)  ← localization
- page._load_preview_content()     ← STL viewer loading
- page._localized_tool_type()      ← tool type names
- page._localized_cutting_type()   ← cutting type names
- page._is_turning_drill_tool_type() ← tool classification
- page._tool_id_display_value()    ← ID formatting
- page.part_clicked()              ← part click handler
- page._refresh_elided_group_title() ← title elision
- page.font()                      ← for arrow pixmaps


# ============================================================================
# 5. METHOD MAPPING: What Moves, What Stays
# ============================================================================

## MOVES TO DetailPanelBuilder.py:
┌─ Core Detail Panel Methods
│  ├─ populate_details(tool)
│  ├─ _build_detail_header(tool)
│  ├─ _build_info_grid(tool)
│  ├─ _build_components_panel(tool, support_parts)
│  ├─ _build_preview_panel(stl_path)
│  ├─ _clear_details()
│  └─ _build_placeholder_details()  ← optional, could stay in HomePage
│
├─ Component Rendering Methods
│  ├─ _build_component_row_widget(item, display_name)
│  ├─ _build_component_spare_host(linked_spares)
│  ├─ _wire_spare_toggle(...)
│  ├─ _add_two_box_row(...)
│  └─ _add_three_box_row(...)
│
└─ Component Data Processing Methods
   ├─ _normalized_component_items(tool)
   ├─ _spare_index_by_component(support_parts)
   ├─ _legacy_component_candidates(tool)
   ├─ _component_key(item, fallback_idx)
   ├─ _component_toggle_arrow_pixmaps()
   └─ (static method)

## STAYS IN HomePage:
├─ Detail Panel Ownership
│  ├─ detail_scroll        (QScrollArea widget reference)
│  ├─ detail_panel         (QWidget container reference)
│  ├─ detail_layout        (VBoxLayout for widgets)
│  ├─ detail_container     (parent widget reference)
│  ├─ _details_hidden      (visibility state flag)
│  ├─ expand_details()     (slide animation)
│  ├─ collapse_details()   (slide animation)
│  ├─ toggle_details()     (visibility toggle)
│  ├─ show_details()       (show detail panel)
│  └─ hide_details()       (hide detail panel)
│
├─ Local Rendering Context
│  ├─ part_clicked()       (part link click handler)
│  ├─ _load_preview_content() (delegates to STL loader service)
│  ├─ _localized_tool_type(raw_type) ← called by builder
│  ├─ _localized_cutting_type(raw_type) ← called by builder
│  ├─ _is_turning_drill_tool_type(raw_type) ← called by builder
│  ├─ _tool_id_display_value(value) ← called by builder
│  ├─ _t(key, default, **kwargs) ← called by builder
│  └─ font() ← called by builder for arrow pixmaps
│
├─ Tool List Management
│  ├─ _get_selected_tool()     (query current selection)
│  ├─ _on_current_changed()    (list selection signal)
│  ├─ _on_double_clicked()     (list double-click signal)
│  ├─ refresh_list()           (reload list from service)
│  └─ tool_list               (QListView widget)
│
└─ Tool CRUD & Dialogs
   ├─ add_tool()           (open editor dialog)
   ├─ edit_tool()          (open editor dialog)
   ├─ delete_tool()        (confirm & remove)
   ├─ duplicate_tool()     (copy tool)
   └─ export_tools()       (bulk export)


# ============================================================================
# 6. CALL PATTERNS: HomePage → DetailPanelBuilder
# ============================================================================

## In __init__:
    self._detail_builder = DetailPanelBuilder(self)

## In _build_ui() [detail panel setup]:
    # (no change needed, detail_layout still managed here)

## In signal handlers (_on_current_changed, _on_double_clicked, etc):
    if not self._details_hidden:
        tool = self._get_selected_tool()
        self._detail_builder.populate_details(tool)  # ← CALL BUILDER
    # or
    self._detail_builder.populate_details(None)  # ← clear details

## In add/edit dialogs (_save_from_dialog):
    saved_tool = self.tool_service.get_tool_by_uid(saved_uid)
    self._detail_builder.populate_details(saved_tool)  # ← REFRESH DETAILS

## In delete tool (on_delete_tool):
    self._detail_builder.populate_details(None)  # ← CLEAR DETAILS


# ============================================================================
# 7. IMPLEMENTATION CHECKLIST
# ============================================================================

STEP 1: Create detail_panel_builder.py
  ☑ Create file with DetailPanelBuilder class
  ☑ Import all dependencies
  ☑ Move populate_details() from HomePage
  ☑ Move _build_detail_header()
  ☑ Move _build_info_grid()
  ☑ Move _build_components_panel()
  ☑ Move _build_preview_panel()
  ☑ Move _clear_details()
  ☑ Move _build_placeholder_details()
  ☑ Move all component rendering methods
  ☑ Move all component data processing methods

STEP 2: Update HomePage to use builder
  ☑ Import DetailPanelBuilder
  ☑ Create self._detail_builder = DetailPanelBuilder(self) in __init__
  ☑ Replace all populate_details() calls with self._detail_builder.populate_details()
  ☑ Remove all moved methods from HomePage
  ☑ Test detail panel still renders correctly
  ☑ Test tool selection updates details
  ☑ Test tool save/delete updates details
  ☑ Test preview panel still loads
  ☑ Test components/spares still collapse/expand

STEP 3: Quality checks
  ☑ Run import_path_checker.py (check for cross-app imports)
  ☑ Run smoke_test.py (check basic functionality)
  ☑ Review signal flow (selection → details rendering)
  ☑ Check pixel-perfect rendering matches original
  ☑ Verify no behavior changes
  ☑ Check performance (no slowdowns from builder overhead)


# ============================================================================
# 8. ARCHITECTURE NOTES
# ============================================================================

## Design Rationale
- DetailPanelBuilder is a coordinator/builder, not a data owner
- HomePage retains widget ownership (detail_layout, detail_panel, etc.)
- Builder receives HomePage reference to access rendering context
- No new signals or callbacks needed (HomePage still drives everything)
- Minimal coupling: builder only knows how to render, not about tool selection

## Ownership Model
HomePage:
  - Owns detail_layout (QVBoxLayout)
  - Owns detail_panel (QWidget)
  - Owns detail_scroll (QScrollArea)
  - Owns visibility state (_details_hidden)
  - Owns show/hide animation logic
  - Drives selection logic

DetailPanelBuilder:
  - Constructs widgets on demand
  - Uses HomePage's detail_layout to add widgets
  - Delegates to HomePage for rendering context
  - Stateless (no member variables except self.page)

## Memory Model
- No circular references (builder doesn't hold detail_layout directly)
- Builder cleans up via _clear_details() before new render
- Qt parent/child hierarchy handles deletion on detail_panel cleanup
- Cache (page._component_toggle_arrows) stored on HomePage (owned by HomePage)

## Testing Strategy
- Unit tests: DetailPanelBuilder renders correct widget structure
- Integration tests: HomePage → builder → rendered output
- Regression tests: Pixel-perfect rendering matches original
- Signal flow tests: Selection → populate_details → repaint

## Performance Notes
- Builder instantiated once in __init__ (no repeated object creation)
- populate_details() called only on selection changes (not on every repaint)
- Widget cleanup via _clear_details() is efficient (Qt handles native cleanup)
- Arrow pixmap caching prevents regeneration on each spares toggle


# ============================================================================
# 9. EDGE CASES & MIGRATION NOTES
# ============================================================================

## Legacy Component Format
- Tool dict may have old-style component fields (holder_code, cutting_code, etc.)
- _legacy_component_candidates() provides fallback for tools predating component_items
- Transparent migration: user sees nothing different

## STL Preview Loading
- Delegates to page._load_preview_content() for actual loading
- If StlPreviewWidget is None, shows placeholder text
- If stl_path is None or invalid, shows "No 3D model assigned"

## Localization
- All strings use page._t() for translation lookup
- Same keys/defaults as original HomePage code
- No breaking changes to i18n

## Type Hints
- Added type hints: tool: dict | None, return types on public methods
- Helps IDE support and future refactors
- TYPE_CHECKING import prevents circular dependencies


# ============================================================================
# 10. ESTIMATED LINES OF CODE
# ============================================================================

DetailPanelBuilder:
  - Class prologue/init:            ~20 lines
  - populate_details():             ~50 lines
  - _build_detail_header():         ~40 lines
  - _build_info_grid():             ~60 lines
  - _build_components_panel():      ~100 lines
  - _build_preview_panel():         ~55 lines
  - _build_placeholder_details():   ~20 lines
  - Component rendering methods:    ~200 lines
  - Helper methods:                 ~150 lines
  - ───────────────────────────────
  Total:                            ~695 lines

HomePage reduction:
  - Removed methods:               -~250 lines
  - New imports:                    +5 lines
  - New instance variable:          +1 line
  - Updated signal handlers:        +10 lines (changed calls)
  ───────────────────────────────
  Net change:                      -234 lines

Project total:
  - Added:                          +700 lines
  - Removed:                        -250 lines
  ───────────────────────────────
  Net change:                       +450 lines
  (But improved modularity, reduced HomePage complexity)
"""

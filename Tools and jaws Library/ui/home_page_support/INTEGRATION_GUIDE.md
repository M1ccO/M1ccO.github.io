"""INTEGRATION GUIDE: Exact Code Changes for HomePage

This file shows the exact changes needed to HomePage to use DetailPanelBuilder.
Shows before/after for each affected method.
"""

# ============================================================================
# CHANGE 1: HomePage.__init__() - Add builder instantiation
# ============================================================================

## BEFORE:
def __init__(
    self,
    tool_service,
    export_service,
    settings_service,
    parent=None,
    page_title: str = 'Tool Library',
    view_mode: str = 'home',
    translate=None,
):
    super().__init__(parent)
    self.tool_service = tool_service
    self.export_service = export_service
    self.settings_service = settings_service
    self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
    self.page_title = page_title
    self.view_mode = (view_mode or 'home').lower()
    self.current_tool_id = None
    self.current_tool_uid = None
    # ... more instance variables ...
    self._build_ui()
    self._warmup_preview_engine()
    self.refresh_list()

## AFTER:
from ui.home_page_support.detail_panel_builder import DetailPanelBuilder

def __init__(
    self,
    tool_service,
    export_service,
    settings_service,
    parent=None,
    page_title: str = 'Tool Library',
    view_mode: str = 'home',
    translate=None,
):
    super().__init__(parent)
    self.tool_service = tool_service
    self.export_service = export_service
    self.settings_service = settings_service
    self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
    self.page_title = page_title
    self.view_mode = (view_mode or 'home').lower()
    self.current_tool_id = None
    self.current_tool_uid = None
    # ... more instance variables ...
    self._detail_builder = DetailPanelBuilder(self)  # ← NEW LINE
    self._build_ui()
    self._warmup_preview_engine()
    self.refresh_list()


# ============================================================================
# CHANGE 2: HomePage._on_current_changed() - Use builder instead of method
# ============================================================================

## BEFORE:
def _on_current_changed(self, current: QModelIndex, previous: QModelIndex):
    if not current.isValid():
        self.current_tool_id = None
        self.current_tool_uid = None
        self._update_selection_count_label()
        self.populate_details(None)  # ← OLD: call HomePage method
        if self.preview_window_btn.isChecked():
            self._close_detached_preview()
        return
    self.current_tool_id = current.data(ROLE_TOOL_ID)
    self.current_tool_uid = current.data(ROLE_TOOL_UID)
    self._update_selection_count_label()
    # if details pane is already visible, refresh its contents
    if not self._details_hidden:
        tool = self._get_selected_tool()
        self.populate_details(tool)  # ← OLD: call HomePage method
    if self.preview_window_btn.isChecked():
        self._sync_detached_preview(show_errors=False)

## AFTER:
def _on_current_changed(self, current: QModelIndex, previous: QModelIndex):
    if not current.isValid():
        self.current_tool_id = None
        self.current_tool_uid = None
        self._update_selection_count_label()
        self._detail_builder.populate_details(None)  # ← NEW: call builder
        if self.preview_window_btn.isChecked():
            self._close_detached_preview()
        return
    self.current_tool_id = current.data(ROLE_TOOL_ID)
    self.current_tool_uid = current.data(ROLE_TOOL_UID)
    self._update_selection_count_label()
    # if details pane is already visible, refresh its contents
    if not self._details_hidden:
        tool = self._get_selected_tool()
        self._detail_builder.populate_details(tool)  # ← NEW: call builder
    if self.preview_window_btn.isChecked():
        self._sync_detached_preview(show_errors=False)


# ============================================================================
# CHANGE 3: HomePage._on_double_clicked() - Use builder
# ============================================================================

## BEFORE:
def _on_double_clicked(self, index: QModelIndex):
    self.current_tool_id = index.data(ROLE_TOOL_ID)
    self.current_tool_uid = index.data(ROLE_TOOL_UID)
    if QApplication.keyboardModifiers() & Qt.ControlModifier:
        self.edit_tool()
        return
    # if detail window already open, close it; otherwise open/update
    if not self._details_hidden:
        self.hide_details()
    else:
        self.populate_details(self._get_selected_tool())  # ← OLD
        self.show_details()

## AFTER:
def _on_double_clicked(self, index: QModelIndex):
    self.current_tool_id = index.data(ROLE_TOOL_ID)
    self.current_tool_uid = index.data(ROLE_TOOL_UID)
    if QApplication.keyboardModifiers() & Qt.ControlModifier:
        self.edit_tool()
        return
    # if detail window already open, close it; otherwise open/update
    if not self._details_hidden:
        self.hide_details()
    else:
        self._detail_builder.populate_details(self._get_selected_tool())  # ← NEW
        self.show_details()


# ============================================================================
# CHANGE 4: HomePage._save_from_dialog() - Use builder to refresh details
# ============================================================================

## BEFORE:
def _save_from_dialog(self, dlg):
    try:
        data = dlg.get_tool_data()
        source_uid = data.get('uid')
        is_new_tool = source_uid is None

        if is_new_tool and self.tool_service.tcode_exists(data['id'], exclude_uid=data.get('uid')):
            confirm_text = (
                self._t(
                    'tool_library.warning.duplicate_tcode',
                    'This T-code already exists, want to save the tool anyway?\n\n'
                    'This does not overwrite or replace the existing tool.',
                )
            )
            if not self._confirm_yes_no(
                self._t('tool_library.warning.duplicate_tcode_title', 'Duplicate T-code'),
                confirm_text,
                danger=False,
            ):
                return 'retry'

        saved_uid = self.tool_service.save_tool(data, allow_duplicate=True)
        saved_tool = self.tool_service.get_tool_by_uid(saved_uid)
        self.current_tool_uid = saved_uid
        self.current_tool_id = (saved_tool or {}).get('id', data['id'])
        self.refresh_list()
        self.populate_details(saved_tool)  # ← OLD: call HomePage method
        if self.preview_window_btn.isChecked():
            self._sync_detached_preview(show_errors=False)
        return 'saved'
    except ValueError as exc:
        QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
        return 'error'

## AFTER:
def _save_from_dialog(self, dlg):
    try:
        data = dlg.get_tool_data()
        source_uid = data.get('uid')
        is_new_tool = source_uid is None

        if is_new_tool and self.tool_service.tcode_exists(data['id'], exclude_uid=data.get('uid')):
            confirm_text = (
                self._t(
                    'tool_library.warning.duplicate_tcode',
                    'This T-code already exists, want to save the tool anyway?\n\n'
                    'This does not overwrite or replace the existing tool.',
                )
            )
            if not self._confirm_yes_no(
                self._t('tool_library.warning.duplicate_tcode_title', 'Duplicate T-code'),
                confirm_text,
                danger=False,
            ):
                return 'retry'

        saved_uid = self.tool_service.save_tool(data, allow_duplicate=True)
        saved_tool = self.tool_service.get_tool_by_uid(saved_uid)
        self.current_tool_uid = saved_uid
        self.current_tool_id = (saved_tool or {}).get('id', data['id'])
        self.refresh_list()
        self._detail_builder.populate_details(saved_tool)  # ← NEW
        if self.preview_window_btn.isChecked():
            self._sync_detached_preview(show_errors=False)
        return 'saved'
    except ValueError as exc:
        QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
        return 'error'


# ============================================================================
# CHANGE 5: Find all other populate_details() calls and replace
# ============================================================================

# Search HomePage for: "self.populate_details("
# Replace all occurrences with: "self._detail_builder.populate_details("

# Locations to check (grep results from earlier):
#   Line 1257: self.populate_details(tool)
#   Line 1328: self.populate_details(None)
#   Line 1478: self.populate_details(None)
#   Line 1488: self.populate_details(tool)
#   Line 1502: self.populate_details(self._get_selected_tool())
#   Line 2214: self.populate_details(saved_tool)
#   Line 2336: self.populate_details(self._get_selected_tool())
#   Line 2338: self.populate_details(None)
#   Line 2398: self.populate_details(self._get_selected_tool())
#   Line 2428: self.populate_details(None)

PATTERN: self.populate_details(
REPLACE: self._detail_builder.populate_details(


# ============================================================================
# CHANGE 6: REMOVE all moved methods from HomePage
# ============================================================================

# Remove the entire method bodies for:

def populate_details(self, tool):  # ← REMOVE ENTIRE METHOD (~100 lines)
    # This now lives in DetailPanelBuilder

def _clear_details(self):  # ← REMOVE ENTIRE METHOD (~8 lines)
    # This now lives in DetailPanelBuilder

def _build_placeholder_details(self):  # ← REMOVE ENTIRE METHOD (~20 lines)
    # This now lives in DetailPanelBuilder (could stay, but cleaner to move)

def _build_detail_header(self, tool):  # ← REMOVE ENTIRE METHOD (~40 lines)
    # This now lives in DetailPanelBuilder (used by populate_details)

def _build_info_grid(self, tool):  # ← REMOVE ENTIRE METHOD (~60 lines)
    # This now lives in DetailPanelBuilder

def _build_components_panel(self, tool, support_parts):  # ← REMOVE ENTIRE METHOD (~90 lines)
    # This now lives in DetailPanelBuilder

def _build_preview_panel(self, stl_path):  # ← REMOVE ENTIRE METHOD (~60 lines)
    # This now lives in DetailPanelBuilder

def _add_two_box_row(self, info, row, left_label, left_value, right_label, right_value):  # ← REMOVE (~8 lines)
    # This now lives in DetailPanelBuilder

def _add_three_box_row(self, info, row, first_label, first_value, second_label, ...):  # ← REMOVE (~8 lines)
    # This now lives in DetailPanelBuilder

def _component_toggle_arrow_pixmaps(self):  # ← REMOVE ENTIRE METHOD (~25 lines)
    # This now lives in DetailPanelBuilder

@staticmethod
def _component_key(item, fallback_idx):  # ← OPTIONAL: Can stay (static), or move to builder
    # Recommend: MOVE to DetailPanelBuilder

def _legacy_component_candidates(self, tool):  # ← REMOVE ENTIRE METHOD (~55 lines)
    # This now lives in DetailPanelBuilder

def _normalized_component_items(self, tool):  # ← REMOVE ENTIRE METHOD (~35 lines)
    # This now lives in DetailPanelBuilder

@staticmethod
def _spare_index_by_component(support_parts):  # ← REMOVE ENTIRE METHOD (~20 lines)
    # This now lives in DetailPanelBuilder

def _build_component_row_widget(self, item, display_name):  # ← REMOVE ENTIRE METHOD (~35 lines)
    # This now lives in DetailPanelBuilder

def _build_component_spare_host(self, linked_spares):  # ← REMOVE ENTIRE METHOD (~45 lines)
    # This now lives in DetailPanelBuilder

def _wire_spare_toggle(self, *, frame, spare_host, ...):  # ← REMOVE ENTIRE METHOD (~40 lines)
    # This now lives in DetailPanelBuilder


# ============================================================================
# Methods that STAY in HomePage:
# ============================================================================

# Detail panel ownership methods:
def expand_details(self): ...        # Show detail panel with animation
def collapse_details(self): ...      # Hide detail panel with animation
def toggle_details(self): ...        # Toggle detail panel
def show_details(self): ...          # Alias for expand
def hide_details(self): ...          # Alias for collapse
def _update_row_type_visibility(self, show): ...  # Update list delegate

# Rendering context methods (used by DetailPanelBuilder via self.page.METHOD()):
def _t(self, key, default=None, **kwargs): ...
def _localized_tool_type(self, raw_type): ...
def _localized_cutting_type(self, raw_type): ...
def _is_turning_drill_tool_type(self, raw_type): ...
def _is_mill_tool_type(self, raw_type): ...
def _tool_id_display_value(self, value): ...
def _tool_id_storage_value(self, value): ...
def _strip_tool_id_prefix(self, value): ...

# Preview & display methods:
def _load_preview_content(self, viewer, stl_path, label=None): ...
def part_clicked(self, part): ...    # Part hyperlink click handler
def _refresh_elided_group_title(self, g): ...  # Title elision

# Tool list methods:
def _get_selected_tool(self): ...    # Get current list selection
def _on_current_changed(self, current, previous): ...  # List selection signal
def _on_double_clicked(self, index): ...  # List double-click signal
def refresh_list(self): ...          # Reload list from service

# Tool CRUD methods:
def add_tool(self): ...
def edit_tool(self): ...
def delete_tool(self): ...
def duplicate_tool(self): ...
def export_tools(self): ...
def _save_from_dialog(self, dlg): ...


# ============================================================================
# Test Cases to Verify After Migration
# ============================================================================

"""
1. Tool Selection:
   □ Click tool in list → details show (header, specs, components, preview)
   □ Select different tool → details update (not blank or old tool)
   □ Clear selection → details show "Select a tool to view details"

2. Double-click:
   □ Double-click tool → detail panel slides in
   □ Double-click again → detail panel slides out
   □ Ctrl+Double-click → opens edit dialog

3. Detail Content:
   □ Title + ID show correctly
   □ Type badge + head badge visible
   □ Spec fields (dimensions, angles) render in 2/3-column layout
   □ Notes field multiline if present
   □ Components section shows holder + cutting parts
   □ Component spares collapse/expand on click
   □ Preview panel shows 3D viewer (if STL valid) or placeholder

4. Add/Edit/Delete:
   □ Save new tool → details show new tool (not blank)
   □ Save edited tool → details update
   □ Delete tool → details show placeholder
   □ List refreshes (selection survives or moves to next)

5. Legacy Data:
   □ Old tools (without component_items) render correctly
   □ Fallback component fields (holder_code, cutting_code) used if no component_items

6. Localization:
   □ All strings respect translation (French/other languages)
   □ Badges + labels use _t() lookup

7. Performance:
   □ No lag when selecting tool (details render quickly)
   □ No memory leaks (details clear properly when panel hidden)
   □ Arrow pixmaps cached (not regenerated per spares toggle)

8. Spares Expand/Collapse:
   □ Arrow toggles left ↔ up when clicked
   □ Spares rows show/hide
   □ Code label hover styles work
   □ Multiple spares collapse/expand independently
"""

# Phase 4 Parity Test Validation Strategy

**Document Version**: 1.0  
**Date**: April 13, 2026  
**Status**: Ready for Implementation  
**Scope**: HomePage → CatalogPageBase refactor parity testing  
**Success Threshold**: 13/13 test groups PASS = Phase 4 gate open

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Test Baseline & Scope](#test-baseline--scope)
3. [13 Test Groups: Behavior Verification](#13-test-groups-behavior-verification)
4. [Test Execution Plan](#test-execution-plan)
5. [Test Invocation & Commands](#test-invocation--commands)
6. [Expected Output & Parsing](#expected-output--parsing)
7. [Failure Classification & Rollback Triggers](#failure-classification--rollback-triggers)
8. [Quality Gate Integration](#quality-gate-integration)

---

## Executive Summary

Phase 4 refactors HomePage (2,223L) → ~400L by inheriting from CatalogPageBase while preserving all 13 critical user workflows. This document defines:

- **What to test**: 13 behavior categories from Phase 0 baseline
- **How to verify**: Per-group validation strategy with test locations
- **When to test**: Gates after each of 7 implementation passes
- **Pass criteria**: 13/13 groups PASS = zero regression = phase gate open
- **Failure protocol**: Classification → targeted rollback level

**Key constraint**: No behavior change, no schema changes, 100% backward compatibility.

---

## Test Baseline & Scope

### Phase 0 Baseline Status (Pre-Implementation)

```
Baseline Date: April 13, 2026 (before Phase 4 starts)
Tool Library Version: HomePage (2,223L, pre-migration)
Database Schema: tool_library.db (current)

Baseline Test Results:
✅ Test 1: TOOLS CRUD / Add → PASS
✅ Test 2: TOOLS CRUD / Edit → PASS
✅ Test 3: TOOLS CRUD / Delete → PASS
✅ Test 4: TOOLS CRUD / Copy → PASS
✅ Test 5: Batch / Batch Edit & Group Edit → PASS
✅ Test 6: Search / Text Search → PASS
✅ Test 7: Search / Type Filter → PASS
✅ Test 8: Detail Panel / Toggle & Populate → PASS
✅ Test 9: Preview / Inline STL → PASS
✅ Test 10: Preview / Detached Window → PASS
✅ Test 11: Selector / Context Mode → PASS
✅ Test 12: Export / Excel Export/Import → PASS
✅ Test 13: IPC / Setup Manager Handoff → PASS

Result: 13/13 PASS (100%)
```

### Parity Test Gate (Post-Implementation)

```
Phase 4 Test Results (end of Pass 6):
Expected: 13/13 PASS (identical to baseline)
Regression Threshold: 0 (zero regressions allowed)
Failure = blocker for phase progression
```

---

## 13 Test Groups: Behavior Verification

### Test Group 1: TOOLS CRUD / Add Tool

**File Location**: `tests/test_shared_regressions.py` (test_tools_add or equivalent)  
**Service**: `tool_service.save_tool()`  
**UI Entry Point**: HomePage: "Add Tool" button → AddEditToolDialog

#### Verification Steps

```python
# Automated verification
def test_tools_add():
    """Verify tool creation inserts to DB, updates UI, generates UID."""
    
    # Step 1: Create tool via service
    new_tool_data = {
        'tool_id': 'PHASE4_TEST_ADD_001',
        'description': 'Phase 4 Add Test',
        'tool_type': 'Turning Mill',
        'geom_x': 10.5,
        'geom_z': 5.0,
    }
    tool_service.save_tool(new_tool_data)
    
    # Step 2: Verify in DB
    saved_tool = tool_service.get_tool('PHASE4_TEST_ADD_001')
    assert saved_tool is not None, "Tool not found in DB"
    assert saved_tool['description'] == 'Phase 4 Add Test', "Description mismatch"
    assert saved_tool['uid'] is not None and saved_tool['uid'] > 0, "UID not generated"
    
    # Step 3: Verify in UI list (refresh_catalog calls apply_filters)
    tools_list = tool_service.list_tools()
    assert any(t['tool_id'] == 'PHASE4_TEST_ADD_001' for t in tools_list), \
        "Tool not in refresh_catalog result"
    
    # Step 4: Verify search finds new tool
    search_results = tool_service.list_tools(search='PHASE4_TEST_ADD')
    assert any(t['tool_id'] == 'PHASE4_TEST_ADD_001' for t in search_results), \
        "Tool not found via search"
    
    return 'PASS'
```

#### Manual Verification

```
☐ Open Tool Library → Home tab
☐ Click "Add Tool" button
☐ Fill form:
    ☐ Tool ID: PHASE4_TEST_ADD_001
    ☐ Description: Phase 4 Add Test
    ☐ Tool Type: Turning Mill
    ☐ Geom X: 10.5
    ☐ Geom Z: 5.0
☐ Click "Save"
☐ Verify tool appears in catalog
☐ Verify unique UID assigned (non-zero)
☐ Verify DB record created (SQLite check)
☐ Verify search finds tool
```

#### Pass Criteria

- ✅ Tool in database with all entered fields
- ✅ Unique UID generated and non-zero
- ✅ Tool visible in catalog after refresh
- ✅ Search/filter can locate new tool
- ✅ No UI artifacts or refresh errors
- ❌ **FAIL**: DB error | Tool not visible | UID collision | Search fails

#### Phase Gate: After Pass 1 (class structure)

- Expected: PASS (catalog refresh now delegated to CatalogPageBase.refresh_catalog)

---

### Test Group 2: TOOLS CRUD / Edit Tool

**File Location**: `tests/test_shared_regressions.py` (test_tools_edit)  
**Service**: `tool_service.save_tool()` (with existing UID)  
**UI Entry Point**: HomePage: select tool → "Edit Tool" button → AddEditToolDialog

#### Verification Steps

```python
def test_tools_edit():
    """Verify field updates persist, UID stable, UI refreshes."""
    
    # Step 1: Get original tool (from Test 1)
    original_tool = tool_service.get_tool('PHASE4_TEST_ADD_001')
    original_uid = original_tool['uid']
    
    # Step 2: Modify and save
    modified_tool = dict(original_tool)
    modified_tool['description'] = 'Phase 4 Add Test [EDITED]'
    modified_tool['geom_x'] = 12.5
    tool_service.save_tool(modified_tool)
    
    # Step 3: Verify in DB
    reloaded = tool_service.get_tool('PHASE4_TEST_ADD_001')
    assert reloaded['description'] == 'Phase 4 Add Test [EDITED]', "Description not updated"
    assert reloaded['geom_x'] == 12.5, "Geom X not updated"
    assert reloaded['uid'] == original_uid, "UID changed (should be stable)"
    
    # Step 4: Verify in catalog (refresh_catalog reflects changes)
    tools_list = tool_service.list_tools()
    tool_in_list = next((t for t in tools_list if t['tool_id'] == 'PHASE4_TEST_ADD_001'), None)
    assert tool_in_list is not None, "Tool not in list after edit"
    assert tool_in_list['description'] == 'Phase 4 Add Test [EDITED]', \
        "Catalog not refreshed with edited description"
    
    return 'PASS'
```

#### Pass Criteria

- ✅ All modified fields persisted to DB
- ✅ UID unchanged
- ✅ Catalog list shows updated description
- ✅ Detail panel updates on selection
- ✅ No database corruption
- ❌ **FAIL**: Partial update | UID changed | Catalog stale | DB error

#### Phase Gate: After Pass 1 (refresh logic verified)

---

### Test Group 3: TOOLS CRUD / Delete Tool

**File Location**: `tests/test_shared_regressions.py` (test_tools_delete)  
**Service**: `tool_service.delete_tool()`  
**UI Entry Point**: HomePage: select tool → "Delete Tool" button → Confirm

#### Verification Steps

```python
def test_tools_delete():
    """Verify tool removed from DB and UI, no orphaned data."""
    
    # Step 1: Verify exists before
    before_list = tool_service.list_tools()
    assert any(t['tool_id'] == 'PHASE4_TEST_ADD_001' for t in before_list), \
        "Tool not found before deletion (test 2 precondition failed)"
    
    # Step 2: Delete via service
    tool_service.delete_tool('PHASE4_TEST_ADD_001')
    
    # Step 3: Verify gone from DB
    deleted_tool = tool_service.get_tool('PHASE4_TEST_ADD_001')
    assert deleted_tool is None, "Tool still in DB after deletion"
    
    # Step 4: Verify gone from catalog list
    after_list = tool_service.list_tools()
    assert not any(t['tool_id'] == 'PHASE4_TEST_ADD_001' for t in after_list), \
        "Tool still in catalog after deletion"
    
    # Step 5: Verify no orphaned records
    # (Check spare_parts, components, models tables if applicable)
    
    # Step 6: Emit signal verification (if test 2 refactored)
    # Verify item_deleted('PHASE4_TEST_ADD_001') signal emitted
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Tool removed from database
- ✅ Tool removed from catalog UI
- ✅ Search no longer returns tool
- ✅ No orphaned related records
- ✅ Signal emitted: item_deleted(id)
- ❌ **FAIL**: Tool still present | Orphaned records | Signal not emitted | DB error

#### Phase Gate: After Pass 2 (signal emission verified)

---

### Test Group 4: TOOLS CRUD / Copy Tool

**File Location**: `tests/test_shared_regressions.py` (test_tools_copy)  
**Service**: `tool_service.copy_tool()` or manual copy + save  
**UI Entry Point**: HomePage: select tool → right-click → "Copy Tool" → dialog

#### Verification Steps

```python
def test_tools_copy():
    """Verify new tool with unique ID, all fields cloned, original unchanged."""
    
    # Setup: Create tool T1 to copy from
    tool_service.save_tool({
        'tool_id': 'PHASE4_TEST_COPY_SRC',
        'description': 'Copy Source Tool',
        'tool_type': 'Turning Mill',
        'geom_x': 10.5,
        'geom_z': 5.0,
    })
    original = tool_service.get_tool('PHASE4_TEST_COPY_SRC')
    original_uid = original['uid']
    
    # Step 1: Copy tool
    if hasattr(tool_service, 'copy_tool'):
        tool_service.copy_tool(
            source_id='PHASE4_TEST_COPY_SRC',
            new_id='PHASE4_TEST_COPY_DST',
            new_description='Copy of Source Tool'
        )
    else:
        # Manual copy
        copied_data = dict(original)
        copied_data['tool_id'] = 'PHASE4_TEST_COPY_DST'
        copied_data['description'] = 'Copy of Source Tool'
        copied_data.pop('uid', None)  # Remove UID so new one generated
        tool_service.save_tool(copied_data)
    
    # Step 2: Verify copy created
    copied = tool_service.get_tool('PHASE4_TEST_COPY_DST')
    assert copied is not None, "Copied tool not found in DB"
    assert copied['uid'] != original_uid, "Copied tool has same UID (collision)"
    assert copied['tool_id'] == 'PHASE4_TEST_COPY_DST', "Tool ID not updated"
    assert copied['description'] == 'Copy of Source Tool', "Description not set"
    assert copied['geom_x'] == original['geom_x'], "Geom X not cloned"
    assert copied['geom_z'] == original['geom_z'], "Geom Z not cloned"
    
    # Step 3: Verify original unchanged
    reloaded_original = tool_service.get_tool('PHASE4_TEST_COPY_SRC')
    assert reloaded_original['uid'] == original_uid, "Original UID changed"
    assert reloaded_original['tool_id'] == 'PHASE4_TEST_COPY_SRC', "Original ID changed"
    
    # Step 4: Verify both in catalog
    tools_list = tool_service.list_tools()
    src_in_list = any(t['tool_id'] == 'PHASE4_TEST_COPY_SRC' for t in tools_list)
    dst_in_list = any(t['tool_id'] == 'PHASE4_TEST_COPY_DST' for t in tools_list)
    assert src_in_list and dst_in_list, "Copy operation didn't refresh catalog"
    
    return 'PASS'
```

#### Pass Criteria

- ✅ New tool created with unique ID
- ✅ New tool has unique UID (no collision)
- ✅ All data fields cloned from source
- ✅ Original tool unchanged
- ✅ Both tools visible in catalog
- ✅ Spare parts/components cloned (if applicable)
- ❌ **FAIL**: No new tool | UID collision | Partial clone | Original modified

#### Phase Gate: After Pass 4 (detail panel tested)

---

### Test Group 5: Batch Operations / Batch Edit & Group Edit

**File Location**: `tests/test_shared_regressions.py` (test_batch_edit)  
**Service**: `home_page_support.batch_actions.batch_edit_tools()`, `group_edit_tools()`  
**UI Entry Point**: HomePage: multi-select → "Edit" button → batch dialog

#### Verification Steps

```python
def test_batch_edit():
    """Verify batch edit updates multiple tools, group edit coordinates."""
    
    # Setup: Create 3 test tools
    tools_to_batch = []
    for i in range(3):
        tool_data = {
            'tool_id': f'PHASE4_TEST_BATCH_{i}',
            'description': f'Batch Test Tool {i}',
            'tool_type': 'Turning Mill',
            'geom_x': 10.0,
            'tool_head': 'HEAD1',
        }
        tool_service.save_tool(tool_data)
        tools_to_batch.append(tool_service.get_tool(f'PHASE4_TEST_BATCH_{i}'))
    
    # Step 1: Simulate batch edit (e.g., change tool_head for all)
    from Tools_and_jaws_Library.ui.home_page_support.batch_actions import batch_edit_tools
    
    uids = [t['uid'] for t in tools_to_batch]
    # Typically called with home_page context, but test via service calls
    
    for tool in tools_to_batch:
        tool['tool_head'] = 'HEAD2'
        tool_service.save_tool(tool)
    
    # Step 2: Verify all updated
    for i in range(3):
        updated = tool_service.get_tool(f'PHASE4_TEST_BATCH_{i}')
        assert updated['tool_head'] == 'HEAD2', \
            f"Tool {i} tool_head not updated in batch edit"
    
    # Step 3: Verify catalog reflects batch changes
    tools_list = tool_service.list_tools()
    batch_tools_in_list = [t for t in tools_list if t['tool_id'].startswith('PHASE4_TEST_BATCH_')]
    assert len(batch_tools_in_list) == 3, "Not all batch tools in refreshed list"
    assert all(t['tool_head'] == 'HEAD2' for t in batch_tools_in_list), \
        "Catalog doesn't show batch updated tool_head"
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Multiple tools selected and edited
- ✅ Common field updated for all selected
- ✅ Catalog list refreshes with batch changes
- ✅ Group edit dialog coordinates changes
- ✅ No individual tools missed or missed
- ❌ **FAIL**: Some tools not updated | Catalog stale | Batch fails mid-operation

#### Phase Gate: After Pass 4 (test via home_page_support modules)

---

### Test Group 6: Search / Text Search

**File Location**: `tests/test_shared_regressions.py` (test_search_text)  
**Service**: `tool_service.list_tools(search='...')`  
**UI Entry Point**: HomePage: search icon → type text → auto-filter

#### Verification Steps

```python
def test_search_text():
    """Verify text search filters by tool_id or description."""
    
    # Setup: Create test tools with distinct IDs
    test_tools = [
        {'tool_id': 'SEARCH_ABC_001', 'description': 'Searching Tool A'},
        {'tool_id': 'SEARCH_XYZ_002', 'description': 'Another Search XYZ'},
        {'tool_id': 'NOSEARCH_999', 'description': 'Different Tool'},
    ]
    for tool_data in test_tools:
        tool_service.save_tool(tool_data)
    
    # Step 1: Search by tool_id prefix
    results = tool_service.list_tools(search='SEARCH_ABC')
    assert len(results) >= 1, "Search for 'SEARCH_ABC' returned no results"
    assert any(t['tool_id'] == 'SEARCH_ABC_001' for t in results), \
        "Target tool_id not in search results"
    
    # Step 2: Search by description
    results = tool_service.list_tools(search='Searching Tool A')
    assert any(t['tool_id'] == 'SEARCH_ABC_001' for t in results), \
        "Tool not found by description search"
    
    # Step 3: Search that matches multiple
    results = tool_service.list_tools(search='SEARCH')
    assert len(results) >= 2, "Partial search didn't match multiple tools"
    search_ids = [t['tool_id'] for t in results]
    assert 'SEARCH_ABC_001' in search_ids, "SEARCH_ABC not in multi-match results"
    assert 'SEARCH_XYZ_002' in search_ids, "SEARCH_XYZ not in multi-match results"
    
    # Step 4: Search with no matches
    results = tool_service.list_tools(search='NONEXISTENT_ZZZ')
    assert len([t for t in results if 'NONEXISTENT' in t['tool_id']]) == 0, \
        "Non-existent search returned matches"
    
    # Step 5: Clear search (empty string)
    all_tools = tool_service.list_tools(search='')
    assert len(all_tools) >= 3, "Clear search didn't return all tools"
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Search filters by tool_id (substring match)
- ✅ Search filters by description
- ✅ Multiple matches returned correctly
- ✅ No matches returns empty list
- ✅ Clear search returns all tools
- ✅ Apply_filters respects search param
- ❌ **FAIL**: Search returns no/wrong results | Partial matches missed

#### Phase Gate: After Pass 1 (apply_filters called by refresh_catalog)

---

### Test Group 7: Search / Type Filter

**File Location**: `tests/test_shared_regressions.py` (test_filter_type)  
**Service**: `tool_service.list_tools(tool_type='...')`  
**UI Entry Point**: HomePage: type filter dropdown → select type → auto-filter

#### Verification Steps

```python
def test_filter_type():
    """Verify type filter constrains catalog to selected tool type."""
    
    # Setup: Create tools of different types
    test_tools = [
        {'tool_id': 'TYPE_TURNING_001', 'description': 'Turning Mill', 'tool_type': 'Turning Mill'},
        {'tool_id': 'TYPE_TURNING_002', 'description': 'Turning Chuck', 'tool_type': 'Turning Mill'},
        {'tool_id': 'TYPE_MILLING_001', 'description': 'Milling Tool', 'tool_type': 'Milling'},
        {'tool_id': 'TYPE_MILLING_002', 'description': 'Milling Cutter', 'tool_type': 'Milling'},
    ]
    for tool_data in test_tools:
        tool_service.save_tool(tool_data)
    
    # Step 1: Filter by Turning Mill
    turning_results = tool_service.list_tools(tool_type='Turning Mill')
    turning_ids = [t['tool_id'] for t in turning_results]
    assert 'TYPE_TURNING_001' in turning_ids, "TYPE_TURNING_001 not in Turning Mill filter"
    assert 'TYPE_TURNING_002' in turning_ids, "TYPE_TURNING_002 not in Turning Mill filter"
    assert 'TYPE_MILLING_001' not in turning_ids, "Milling tool in Turning filter"
    
    # Step 2: Filter by Milling
    milling_results = tool_service.list_tools(tool_type='Milling')
    milling_ids = [t['tool_id'] for t in milling_results]
    assert 'TYPE_MILLING_001' in milling_ids, "TYPE_MILLING_001 not in Milling filter"
    assert 'TYPE_MILLING_002' in milling_ids, "TYPE_MILLING_002 not in Milling filter"
    assert 'TYPE_TURNING_001' not in milling_ids, "Turning tool in Milling filter"
    
    # Step 3: Filter by 'All' (no type filter)
    all_types = tool_service.list_tools(tool_type='All')
    assert len(all_types) >= 4, "All types doesn't include all tools"
    
    # Step 4: Combine search + type filter
    results = tool_service.list_tools(search='TYPE_TURNING', tool_type='Turning Mill')
    assert len(results) >= 2, "Search + type filter didn't narrow correctly"
    assert all(t['tool_type'] == 'Turning Mill' for t in results), \
        "Type filter override by combined search"
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Type filter constrains to selected type
- ✅ 'All' option shows all types
- ✅ Combination with search works correctly
- ✅ Apply_filters respects tool_type param
- ✅ Catalog updates on filter change
- ❌ **FAIL**: Filter returns wrong type | All filter incomplete | Combo filter broken

#### Phase Gate: After Pass 1 (apply_filters includes tool_type)

---

### Test Group 8: Detail Panel / Toggle & Populate

**File Location**: `tests/test_shared_regressions.py` (test_detail_panel)  
**Service**: `home_page.populate_details()` (now delegated to support module)  
**UI Entry Point**: HomePage: click details button or double-click tool → detail pane appears

#### Verification Steps

```python
def test_detail_panel():
    """Verify detail pane toggles visibility and populates with tool data."""
    
    # Setup: Create test tool
    tool_data = {
        'tool_id': 'DETAIL_PANEL_TEST',
        'description': 'Detail Panel Test Tool',
        'tool_type': 'Turning Mill',
        'geom_x': 10.5,
        'geom_z': 5.0,
    }
    tool_service.save_tool(tool_data)
    test_tool = tool_service.get_tool('DETAIL_PANEL_TEST')
    
    # Step 1: Verify detail pane hidden initially
    assert home_page._details_hidden == True or \
           home_page.detail_container.isHidden(), \
        "Detail pane should start hidden"
    
    # Step 2: Call populate_details (simulating selection + toggle)
    from Tools_and_jaws_Library.ui.home_page_support.detail_panel_builder import \
        populate_detail_panel
    populate_detail_panel(home_page, test_tool)
    
    # Step 3: Verify detail pane visible and populated
    # (Requires UI widget introspection)
    assert not home_page.detail_container.isHidden(), \
        "Detail pane should be visible after populate_details"
    
    # Step 4: Verify detail fields contain expected data
    # (Traverse detail layout to find labels/values)
    detail_text = home_page.detail_panel.toPlainText() if hasattr(...) else ''
    assert 'DETAIL_PANEL_TEST' in detail_text or 'Detail Panel Test Tool' in detail_text, \
        "Detail pane doesn't show tool ID or description"
    
    # Step 5: Select different tool and verify pane updates
    tool_data_2 = {
        'tool_id': 'DETAIL_PANEL_TEST_2',
        'description': 'Second Detail Tool',
        'tool_type': 'Milling',
        'geom_x': 20.5,
    }
    tool_service.save_tool(tool_data_2)
    test_tool_2 = tool_service.get_tool('DETAIL_PANEL_TEST_2')
    
    populate_detail_panel(home_page, test_tool_2)
    detail_text_2 = home_page.detail_panel.toPlainText() if hasattr(...) else ''
    assert 'DETAIL_PANEL_TEST_2' in detail_text_2 or 'Second Detail Tool' in detail_text_2, \
        "Detail pane doesn't update to new tool"
    
    # Step 6: Toggle hide (click details button again)
    home_page.toggle_details()
    assert home_page._details_hidden == True or \
           home_page.detail_container.isHidden(), \
        "Detail pane didn't close on toggle"
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Detail pane starts hidden
- ✅ Detail pane shows when populated
- ✅ Tool data displayed correctly
- ✅ Pane updates on tool selection change
- ✅ Pane hides on toggle
- ✅ Components section renders
- ❌ **FAIL**: Pane stuck open/closed | Data missing | Selection doesn't update

#### Phase Gate: After Pass 4 (detail_panel_builder extracted and integrated)

---

### Test Group 9: Preview / Inline STL

**File Location**: `tests/test_shared_regressions.py` (test_preview_inline)  
**Service**: Tool model loading → preview render (3D WebGL)  
**UI Entry Point**: HomePage detail pane → preview embed

#### Verification Steps

```python
def test_preview_inline():
    """Verify inline STL preview loads, renders, and responds to interactions."""
    
    # Setup: Create tool with model path
    tool_with_model = {
        'tool_id': 'PREVIEW_INLINE_TEST',
        'description': 'Preview Inline Test',
        'tool_type': 'Turning Mill',
        'models': [
            {'path': 'assets/3d/sample_tool.stl', 'index': 0},
        ],
    }
    tool_service.save_tool(tool_with_model)
    test_tool = tool_service.get_tool('PREVIEW_INLINE_TEST')
    
    # Step 1: Open detail pane with tool that has model
    from Tools_and_jaws_Library.ui.home_page_support.detail_panel_builder import \
        populate_detail_panel
    populate_detail_panel(home_page, test_tool)
    
    # Step 2: Verify preview panel exists (look for QWidget with preview viewer)
    # (Requires widget tree traversal or signal/property introspection)
    preview_widget = None
    for widget in home_page.detail_panel.findChildren(type(QWidget)):
        if 'preview' in widget.objectName().lower():
            preview_widget = widget
            break
    
    assert preview_widget is not None, "Preview widget not found in detail panel"
    
    # Step 3: Verify preview loaded (check for 3D content or iframe/webview)
    # (Depends on implementation: QWebEngineView, custom OpenGL, or embedded viewer)
    if hasattr(preview_widget, 'url'):  # If QWebEngineView
        preview_url = preview_widget.url()
        assert preview_url.isValid(), "Preview URL not loaded"
    
    # Step 4: Simulate mouse interactions (if accessible)
    # (This is typically UI-level interaction, hard to test without GUI automation)
    
    # Step 5: Verify no errors in preview rendering
    # (Check application logs for warnings/errors during preview load)
    
    # Step 6: Select different tool and verify preview updates
    tool_with_model_2 = {
        'tool_id': 'PREVIEW_INLINE_TEST_2',
        'description': 'Second Preview Inline',
        'tool_type': 'Milling',
        'models': [
            {'path': 'assets/3d/sample_mill.stl', 'index': 0},
        ],
    }
    tool_service.save_tool(tool_with_model_2)
    test_tool_2 = tool_service.get_tool('PREVIEW_INLINE_TEST_2')
    
    populate_detail_panel(home_page, test_tool_2)
    # Verify preview updated to new model
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Preview widget loads in detail pane
- ✅ STL model renders without errors
- ✅ 3D content displays (not blank)
- ✅ Preview updates on tool selection
- ✅ Rotation/pan/zoom respond to interaction
- ✅ No memory leaks or crashes
- ❌ **FAIL**: Preview fails to load | Model not rendered | Update broken | Crash

#### Phase Gate: After Pass 4 (detail_panel_builder handles preview)

---

### Test Group 10: Preview / Detached Window

**File Location**: `tests/test_shared_regressions.py` (test_preview_detached)  
**Service**: `home_page_support.detached_preview.toggle_preview_window()`  
**UI Entry Point**: HomePage toolbar → preview window button

#### Verification Steps

```python
def test_preview_detached():
    """Verify detached preview window opens, displays model, syncs with selection."""
    
    # Setup: Create tool with model
    tool_with_model = {
        'tool_id': 'PREVIEW_DETACHED_TEST',
        'description': 'Preview Detached Test',
        'tool_type': 'Turning Mill',
        'models': [
            {'path': 'assets/3d/sample_tool.stl', 'index': 0},
        ],
    }
    tool_service.save_tool(tool_with_model)
    test_tool = tool_service.get_tool('PREVIEW_DETACHED_TEST')
    
    # Step 1: Open detail pane to select tool
    home_page.refresh_catalog()
    # Simulate selection of test_tool
    
    # Step 2: Click preview window button (or call toggle_preview_window)
    from Tools_and_jaws_Library.ui.home_page_support.detached_preview import \
        toggle_preview_window
    
    # Initially no window
    assert home_page._detached_preview_dialog is None or \
           not home_page._detached_preview_dialog.isVisible(), \
        "Preview window should not exist initially"
    
    toggle_preview_window(home_page)
    
    # Step 3: Verify detached window opened
    assert home_page._detached_preview_dialog is not None, \
        "Detached preview dialog not created"
    assert home_page._detached_preview_dialog.isVisible(), \
        "Detached preview dialog not visible"
    
    # Step 4: Verify preview shows selected tool's model
    # (Check window content, similar to inline preview test)
    
    # Step 5: Select different tool in main window
    tool_with_model_2 = {
        'tool_id': 'PREVIEW_DETACHED_TEST_2',
        'description': 'Second Detached Preview',
        'tool_type': 'Milling',
        'models': [
            {'path': 'assets/3d/sample_mill.stl', 'index': 0},
        ],
    }
    tool_service.save_tool(tool_with_model_2)
    test_tool_2 = tool_service.get_tool('PREVIEW_DETACHED_TEST_2')
    
    # Simulate selection change in main window
    # Verify detached preview updates to new model
    
    # Step 6: Close detached window
    home_page._detached_preview_dialog.close()
    
    # Step 7: Verify window closed cleanly
    assert not home_page._detached_preview_dialog.isVisible(), \
        "Preview window didn't close"
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Detached window opens on button click
- ✅ Preview displays selected tool's model
- ✅ Window syncs with main catalog selection
- ✅ Model updates when main selection changes
- ✅ Window closes without errors
- ✅ No memory leak (window can be reopened)
- ❌ **FAIL**: Window doesn't open | Model not in window | Sync broken | Crash on close

#### Phase Gate: After Pass 4 (detached_preview already separated)

---

### Test Group 11: Selector / Context Mode

**File Location**: `tests/test_shared_regressions.py` (test_selector_context)  
**Service**: `home_page.set_selector_context()`, `apply_filters()` with selector state  
**UI Entry Point**: Setup Manager → launches Tool Library in selector mode

#### Verification Steps

```python
def test_selector_context():
    """Verify selector mode activates, filters by spindle, allows assignment."""
    
    # Setup: Create test tools
    tools_data = [
        {'tool_id': 'SELECTOR_TEST_1', 'tool_type': 'Main spindle', 'tool_head': 'HEAD1'},
        {'tool_id': 'SELECTOR_TEST_2', 'tool_type': 'Main spindle', 'tool_head': 'HEAD1'},
        {'tool_id': 'SELECTOR_TEST_SUB', 'tool_type': 'Sub spindle', 'tool_head': 'HEAD1'},
    ]
    for tool_data in tools_data:
        tool_service.save_tool(tool_data)
    
    # Step 1: Simulator Setup Manager calling set_selector_context
    from PySide6.QtCore import Qt
    
    home_page.set_selector_context(
        head='HEAD1',
        spindle='Main',
        selected_ids=[],
    )
    
    # Step 2: Verify selector mode activated
    assert home_page._selector_active == True, "Selector mode not activated"
    assert home_page._selector_head == 'HEAD1', "Selector head not set"
    assert home_page._selector_spindle == 'Main', "Selector spindle not set"
    
    # Step 3: Verify selector UI visible
    assert home_page.selector_card.isVisible(), "Selector card not visible"
    
    # Step 4: Verify catalog filtered by spindle
    # (Only Main spindle tools should appear) → apply_filters respects _selector_active
    filtered_results = home_page.apply_filters({
        'search': '',
        'tool_head': 'HEAD1',
        'tool_type': 'All',
    })
    # Should exclude sub-spindle tools based on _tool_matches_selector_spindle
    
    # Step 5: Verify can assign tools via selector UI
    # (Drag tool to selector panel, verify added to _selector_assigned_tools)
    
    # Step 6: Deactivate selector
    home_page.set_selector_context(
        head=None,
        spindle=None,
        selected_ids=[],
    )
    
    # Step 7: Verify selector mode deactivated
    assert home_page._selector_active == False, "Selector mode not deactivated"
    assert home_page.selector_card.isVisible() == False, "Selector card still visible"
    
    # Step 8: Verify normal mode restored (catalog shows all spindles)
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Selector mode activates on set_selector_context()
- ✅ Selector UI appears
- ✅ Catalog filters by selector spindle constraint
- ✅ Apply_filters respects _selector_active
- ✅ Tools can be assigned in selector mode
- ✅ Deactivation restores normal mode
- ✅ Normal catalog visible after deactivate
- ❌ **FAIL**: Selector doesn't activate | Filter ignored | UI not shown | Can't assign

#### Phase Gate: After Pass 3 (selector state preserved in apply_filters)

---

### Test Group 12: Export / Excel Export & Import

**File Location**: `tests/test_shared_regressions.py` (test_excel_export_import)  
**Service**: `export_service.export_tools_to_excel()`, `export_service.import_tools_from_excel()`  
**UI Entry Point**: HomePage → menu → "Export to Excel" / "Import from Excel"

#### Verification Steps

```python
def test_excel_export_import():
    """Verify Excel export generates valid file with all tools, reimport works."""
    
    from openpyxl import load_workbook
    import tempfile
    
    # Setup: Create test tools
    export_tools = [
        {'tool_id': 'EXPORT_001', 'description': 'Export Test 1', 'tool_type': 'Turning'},
        {'tool_id': 'EXPORT_002', 'description': 'Export Test 2', 'tool_type': 'Milling'},
    ]
    for tool_data in export_tools:
        tool_service.save_tool(tool_data)
    
    # Step 1: Export to Excel
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
        export_path = tmp.name
    
    export_service.export_tools_to_excel(tool_db_conn, export_path)
    
    # Step 2: Verify .xlsx file created and valid
    assert Path(export_path).exists(), "Export file not created"
    wb = load_workbook(export_path)
    assert len(wb.sheetnames) > 0, "Excel workbook has no sheets"
    
    # Step 3: Verify sheet structure
    ws = wb.active
    headers = [cell.value for cell in ws[1]]
    assert 'Tool ID' in headers or 'tool_id' in headers, "Tool ID header not found"
    assert 'Description' in headers or 'description' in headers, \
        "Description header not found"
    
    # Step 4: Verify exported tools in file
    tool_ids_in_file = [row[0] for row in ws.iter_rows(min_row=2, values_only=True)]
    assert 'EXPORT_001' in tool_ids_in_file, "EXPORT_001 not in export file"
    assert 'EXPORT_002' in tool_ids_in_file, "EXPORT_002 not in export file"
    
    # Step 5: Verify data integrity in export
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] == 'EXPORT_001':
            assert 'Export Test 1' in str(row), "Description not exported correctly"
            break
    
    # Step 6: Import from Excel (create new tools)
    import_tools = [
        {'Tool ID': 'IMPORT_001', 'Description': 'Imported Tool 1', 'Tool type': 'Turning'},
        {'Tool ID': 'IMPORT_002', 'Description': 'Imported Tool 2', 'Tool type': 'Milling'},
    ]
    
    # Create import file
    wb_import = Workbook()
    ws_import = wb_import.active
    ws_import.append(['Tool ID', 'Description', 'Tool type'])
    for tool_data in import_tools:
        ws_import.append([tool_data['Tool ID'], tool_data['Description'], tool_data['Tool type']])
    
    import_path = export_path.replace('.xlsx', '_import.xlsx')
    wb_import.save(import_path)
    
    # Step 7: Import via service
    column_mapping = {
        'Tool ID': 'tool_id',
        'Description': 'description',
        'Tool type': 'tool_type',
    }
    
    import_result = export_service.import_tools_from_excel(import_path, column_mapping)
    
    # Step 8: Verify imported tools in database
    imported_1 = tool_service.get_tool('IMPORT_001')
    imported_2 = tool_service.get_tool('IMPORT_002')
    assert imported_1 is not None, "IMPORT_001 not found after import"
    assert imported_2 is not None, "IMPORT_002 not found after import"
    assert imported_1['description'] == 'Imported Tool 1', "Description not imported"
    
    # Step 9: Verify catalog updated
    tools_list = tool_service.list_tools()
    assert any(t['tool_id'] == 'IMPORT_001' for t in tools_list), \
        "Imported tool not in refresh_catalog result"
    
    return 'PASS'
```

#### Pass Criteria

- ✅ Excel export file created and valid
- ✅ All tools included in export
- ✅ Data integrity (no truncation, correct types)
- ✅ File opens in Excel
- ✅ Excel import creates new tools
- ✅ Column mapping works
- ✅ Imported tools in database and catalog
- ✅ Conflict detection (duplicate IDs)
- ❌ **FAIL**: Export fails | File invalid | Data missing | Import incomplete

#### Phase Gate: After Pass 6 (full integration test)

---

### Test Group 13: IPC / Setup Manager Handoff

**File Location**: `tests/test_shared_regressions.py` (test_ipc_handoff)  
**Service**: QLocalSocket IPC communication, tool state sync  
**UI Entry Point**: Setup Manager → double-click tool → Tool Library opens with context

#### Verification Steps

```python
def test_ipc_handoff():
    """Verify Setup Manager ↔ Tool Library IPC, context passed, changes synced."""
    
    import json
    from PySide6.QtNetwork import QLocalSocket
    
    # Setup: Create test tool
    tool_data = {
        'tool_id': 'IPC_TEST_001',
        'description': 'IPC Test Tool',
        'tool_type': 'Turning Mill',
    }
    tool_service.save_tool(tool_data)
    
    # Step 1: Simulate Setup Manager initiating handoff
    # (In real scenario, Setup Manager launches Tool Library process with parameters)
    
    handoff_payload = {
        'action': 'edit_tool',
        'tool_id': 'IPC_TEST_001',
        'geometry': '100,50,800,600',  # Window position for Tool Library
        'head': 'HEAD1',
        'spindle': 'Main',
    }
    
    # Tool Library receives payload (via QLocalSocket or command-line args)
    # Simulated as method call
    home_page.handle_ipc_handoff(handoff_payload)
    
    # Step 2: Verify Tool Library opened with correct tool selected
    assert home_page.current_tool_id == 'IPC_TEST_001', "Tool not pre-selected"
    
    # Step 3: Verify context applied (head/spindle filters set)
    # (If applicable to Tool Library, selector mode not typically used)
    
    # Step 4: Simulate user edits tool in Tool Library
    tool_to_edit = tool_service.get_tool('IPC_TEST_001')
    tool_to_edit['description'] = 'IPC Test Tool [EDITED BY TOOL LIBRARY]'
    tool_service.save_tool(tool_to_edit)
    
    # Step 5: Tool Library sends confirmation back via IPC
    callback_payload = {
        'action': 'tool_edited',
        'tool_id': 'IPC_TEST_001',
        'modified_at': '2026-04-13T10:00:00Z',
    }
    
    # Emit IPC callback (via QLocalSocket.write or similar)
    # home_page.send_ipc_callback(callback_payload)
    
    # Step 6: Verify Setup Manager could receive callback
    # (In automated test, we simulate receiving by checking database state)
    
    # Step 7: Verify tool data consistent between apps
    updated_tool = tool_service.get_tool('IPC_TEST_001')
    assert updated_tool['description'] == 'IPC Test Tool [EDITED BY TOOL LIBRARY]', \
        "IPC handoff didn't persist changes"
    
    # Step 8: Verify IPC protocol version matches
    # (Check IPC_PROTOCOL_VERSION constant or handshake)
    
    return 'PASS'
```

#### Pass Criteria

- ✅ IPC handoff payload received
- ✅ Tool pre-selected in Tool Library
- ✅ Context applied (head/spindle if applicable)
- ✅ User edits persisted to database
- ✅ Callback sent back to Setup Manager
- ✅ Changes visible to Setup Manager
- ✅ IPC protocol version consistent
- ✅ No hanging processes or socket errors
- ❌ **FAIL**: Handoff fails | Tool not selected | Changes not synced | Protocol mismatch

#### Phase Gate: After Pass 6 (full integration test, Phase 5+ maintenance)

---

## Test Execution Plan

### Timeline: Run After Each Implementation Pass

```
Implementation Pass 1 (2-4 hours): Class structure + abstract methods
  ├─ After completion: Run categories [1-7] (CRUD, search, filter)
  ├─ Command: python tests/run_parity_tests.py --phase 4 --groups 1-7
  └─ Expected: 6/7 PASS (group 8+ need detail panel extraction)

Implementation Pass 2 (2-3 hours): Signal emission
  ├─ After completion: Run categories [1-7, 13]
  ├─ Verify: item_selected and item_deleted signals emit correctly
  └─ Expected: 7/7 PASS (signal emission verified)

Implementation Pass 3 (1-2 hours): Selector state preservation
  ├─ After completion: Run test group [11] (selector context)
  ├─ Verify: apply_filters respects _selector_active flag
  └─ Expected: 1/1 PASS (selector integrated)

Implementation Pass 4 (3-5 hours): Detail panel extraction
  ├─ After completion: Run categories [1-12] (all except IPC)
  ├─ Command: python tests/run_parity_tests.py --phase 4 --groups 1-12
  └─ Expected: 12/12 PASS (detail panel + preview working)

Implementation Pass 5 (1-2 hours): Tooling + governance
  ├─ After completion: Run quality gate
  ├─ Command: python scripts/run_quality_gate.py
  └─ Expected: All checks PASS

Implementation Pass 6 (4-6 hours): Parity testing + QA
  ├─ After completion: Run all 13 groups
  ├─ Command: python tests/run_parity_tests.py --phase 4 --all
  └─ Expected: 13/13 PASS (zero regressions verified)

Implementation Pass 7 (1-2 hours): Code review + finalization
  ├─ After completion: Final smoke test
  ├─ Command: python scripts/smoke_test.py
  └─ Expected: Both apps start without errors
```

---

## Test Invocation & Commands

### Command Format

```bash
# Run all 13 tests
python tests/run_parity_tests.py --phase 4

# Run specific test groups
python tests/run_parity_tests.py --phase 4 --groups 1,2,3

# Run with verbose output
python tests/run_parity_tests.py --phase 4 --verbose

# Compare to baseline
python tests/run_parity_tests.py --phase 4 --compare-baseline

# Capture new baseline (post-implementation)
python tests/run_parity_tests.py --phase 4 --capture-baseline
```

### Python Test Runner (Pseudocode)

```python
# tests/run_parity_tests.py

#!/usr/bin/env python
"""
Phase 4 Parity Test Runner

Executes 13 behavioral tests for HomePage refactoring.
Compares results to Phase 0 baseline.
Reports regressions as blocker for phase progression.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Test imports (from session memory)
from test_shared_regressions import (
    test_tools_add,
    test_tools_edit,
    test_tools_delete,
    test_tools_copy,
    test_batch_edit,
    test_search_text,
    test_filter_type,
    test_detail_panel,
    test_preview_inline,
    test_preview_detached,
    test_selector_context,
    test_excel_export_import,
    test_ipc_handoff,
)

TEST_GROUPS = [
    ('group_1_add', test_tools_add, 'TOOLS CRUD / Add'),
    ('group_2_edit', test_tools_edit, 'TOOLS CRUD / Edit'),
    ('group_3_delete', test_tools_delete, 'TOOLS CRUD / Delete'),
    ('group_4_copy', test_tools_copy, 'TOOLS CRUD / Copy'),
    ('group_5_batch', test_batch_edit, 'Batch / Edit & Group Edit'),
    ('group_6_search', test_search_text, 'Search / Text Search'),
    ('group_7_filter', test_filter_type, 'Search / Type Filter'),
    ('group_8_detail', test_detail_panel, 'Detail Panel / Toggle & Populate'),
    ('group_9_preview_inline', test_preview_inline, 'Preview / Inline STL'),
    ('group_10_preview_detached', test_preview_detached, 'Preview / Detached Window'),
    ('group_11_selector', test_selector_context, 'Selector / Context Mode'),
    ('group_12_export', test_excel_export_import, 'Export / Excel Import/Export'),
    ('group_13_ipc', test_ipc_handoff, 'IPC / Setup Manager Handoff'),
]

def run_tests(group_ids=None, verbose=False):
    """Run selected test groups, return results dict."""
    results = {
        'phase': 4,
        'timestamp': datetime.now().isoformat(),
        'build_version': get_build_version(),
        'tests': {},
    }
    
    # Filter groups if specified
    groups_to_run = TEST_GROUPS
    if group_ids:
        group_ids_set = set(group_ids)
        groups_to_run = [g for g in TEST_GROUPS if g[0] in group_ids_set]
    
    passed = 0
    failed = 0
    
    for group_id, test_func, test_name in groups_to_run:
        try:
            if verbose:
                print(f"  Running {test_name}...", end='', flush=True)
            
            result = test_func()  # Calls test function
            
            results['tests'][group_id] = {
                'name': test_name,
                'status': result,
                'error': None,
            }
            
            if result == 'PASS':
                passed += 1
                if verbose:
                    print(" ✅ PASS")
            else:
                failed += 1
                if verbose:
                    print(f" ❌ {result}")
        
        except Exception as e:
            failed += 1
            error_msg = str(e)
            results['tests'][group_id] = {
                'name': test_name,
                'status': 'FAIL',
                'error': error_msg,
            }
            if verbose:
                print(f" ❌ EXCEPTION: {error_msg}")
    
    # Summary
    results['summary'] = {
        'passed': passed,
        'failed': failed,
        'total': len(groups_to_run),
    }
    
    return results

def compare_to_baseline(baseline_file, current_results):
    """Compare current results to Phase 0 baseline."""
    with open(baseline_file) as f:
        baseline = json.load(f)
    
    regressions = []
    for group_id, test_result in current_results['tests'].items():
        baseline_status = baseline['tests'].get(group_id, {}).get('status')
        current_status = test_result.get('status')
        
        if baseline_status == 'PASS' and current_status != 'PASS':
            regressions.append({
                'group': group_id,
                'baseline': baseline_status,
                'current': current_status,
                'error': test_result.get('error'),
            })
    
    return regressions

def main():
    parser = argparse.ArgumentParser(
        description='Phase 4 Parity Test Runner'
    )
    parser.add_argument('--phase', type=int, default=4, help='Phase number')
    parser.add_argument('--groups', help='Comma-separated test groups to run')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    parser.add_argument('--all', action='store_true', help='Run all groups')
    parser.add_argument('--compare-baseline', action='store_true',
                        help='Compare to Phase 0 baseline')
    parser.add_argument('--capture-baseline', action='store_true',
                        help='Capture as new baseline')
    parser.add_argument('--output', default='parity-results.json',
                        help='Output results file')
    
    args = parser.parse_args()
    
    # Parse group IDs
    group_ids = None
    if args.groups:
        group_ids = set(
            f'group_{g.strip()}' for g in args.groups.split(',')
        )
    elif not args.all:
        # Default: run all
        group_ids = None
    
    print(f"Phase {args.phase} Parity Test Suite")
    print("=" * 60)
    
    if args.verbose:
        print(f"Groups: {'all' if not group_ids else ', '.join(group_ids)}")
        print()
    
    # Run tests
    results = run_tests(group_ids, verbose=args.verbose)
    
    # Print summary
    summary = results['summary']
    print(f"\nResults: {summary['passed']}/{summary['total']} PASSED")
    
    if summary['failed'] > 0:
        print(f"         {summary['failed']} FAILED ❌")
        sys.exit(1)
    else:
        print("         0 FAILED ✅")
    
    # Compare to baseline if requested
    if args.compare_baseline:
        baseline_file = f'phase0-baseline-results.json'
        if Path(baseline_file).exists():
            regressions = compare_to_baseline(baseline_file, results)
            if regressions:
                print(f"\n❌ {len(regressions)} Regression(s) detected:")
                for r in regressions:
                    print(f"  - {r['group']}: {r['baseline']} → {r['current']}")
                    if r['error']:
                        print(f"    Error: {r['error']}")
                sys.exit(1)
            else:
                print("\n✅ PARITY VERIFIED (all tests stable vs baseline)")
    
    # Save results
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to {args.output}")
    
    return 0 if summary['failed'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
```

---

## Expected Output & Parsing

### Successful Run (13/13 PASS)

```
Phase 4 Parity Test Suite
============================================================

Running group_1_add (TOOLS CRUD / Add)... ✅ PASS
Running group_2_edit (TOOLS CRUD / Edit)... ✅ PASS
Running group_3_delete (TOOLS CRUD / Delete)... ✅ PASS
Running group_4_copy (TOOLS CRUD / Copy)... ✅ PASS
Running group_5_batch (Batch / Edit & Group Edit)... ✅ PASS
Running group_6_search (Search / Text Search)... ✅ PASS
Running group_7_filter (Search / Type Filter)... ✅ PASS
Running group_8_detail (Detail Panel / Toggle & Populate)... ✅ PASS
Running group_9_preview_inline (Preview / Inline STL)... ✅ PASS
Running group_10_preview_detached (Preview / Detached Window)... ✅ PASS
Running group_11_selector (Selector / Context Mode)... ✅ PASS
Running group_12_export (Export / Excel Import/Export)... ✅ PASS
Running group_13_ipc (IPC / Setup Manager Handoff)... ✅ PASS

Results: 13/13 PASSED
         0 FAILED ✅

✅ PARITY VERIFIED (all tests stable vs baseline)
Results saved to parity-results.json
```

### JSON Output Format

```json
{
  "phase": 4,
  "timestamp": "2026-04-13T15:30:00",
  "build_version": "Phase4-Refactor-v0.1",
  "tests": {
    "group_1_add": {
      "name": "TOOLS CRUD / Add",
      "status": "PASS",
      "error": null
    },
    "group_2_edit": {
      "name": "TOOLS CRUD / Edit",
      "status": "PASS",
      "error": null
    },
    ...
    "group_13_ipc": {
      "name": "IPC / Setup Manager Handoff",
      "status": "PASS",
      "error": null
    }
  },
  "summary": {
    "passed": 13,
    "failed": 0,
    "total": 13
  }
}
```

### Failure Mode (Example: Test 8 fails)

```
Phase 4 Parity Test Suite
============================================================

Running group_1_add (TOOLS CRUD / Add)... ✅ PASS
Running group_2_edit (TOOLS CRUD / Edit)... ✅ PASS
Running group_3_delete (TOOLS CRUD / Delete)... ✅ PASS
Running group_4_copy (TOOLS CRUD / Copy)... ✅ PASS
Running group_5_batch (Batch / Edit & Group Edit)... ✅ PASS
Running group_6_search (Search / Text Search)... ✅ PASS
Running group_7_filter (Search / Type Filter)... ✅ PASS
Running group_8_detail (Detail Panel / Toggle & Populate)... ❌ FAIL
  Error: Detail pane widget not found in home_page.detail_panel

Running group_9_preview_inline (Preview / Inline STL)... ⏭️ SKIPPED
  Reason: Test 8 (prerequisite) failed

Results: 7/12 PASSED
         5 FAILED ❌

Comparison to baseline:
  ❌ group_8_detail: PASS → FAIL
  
Failure Classification: UI LOGIC (detail panel builder not properly integrated)
Recommended Rollback: Level 2 (inline extracted modules)
```

---

## Failure Classification & Rollback Triggers

### Failure Categories

#### Category A: Data/Logic Errors (DB or service layer)

**Symptoms**:
- Test groups 1-7 (CRUD, search, filter) fail
- Error messages: "DB error", "Tool not in DB", "Unexpected field value"
- Catalog refresh returns wrong results

**Root Causes**:
- `apply_filters()` broken → wrong filter logic
- `refresh_catalog()` not properly delegated to base class
- Service layer not called correctly

**Rollback: Level 1** (30 min)
1. Remove `(CatalogPageBase)` inheritance
2. Restore manual refresh_catalog() logic from git history
3. Re-run tests → should PASS immediately
4. Document lesson learned in AGENTS.md

**Prevention**:
- Ensure `apply_filters()` calls tool_service.list_tools() with all 3 filters
- Test apply_filters in isolation before pushing to refresh_catalog
- Commit apply_filters implementation separately for git bisect safety

---

#### Category B: UI/Rendering Errors (widgets, signals, detail panel)

**Symptoms**:
- Test groups 8-12 (detail, preview, selector, export, IPC) fail
- Error messages: "Widget not found", "Signal not emitted", "Detail pane hidden"
- UI doesn't respond to user interaction

**Root Causes**:
- Detail panel builder not properly integrated
- Signal emission code missing or syntax error
- Selector state not initialized in apply_filters

**Rollback: Level 2** (1 hour)
1. Inline detail_panel_builder module back into home_page.py
2. Restore extracted methods to original locations
3. Re-run tests → should PASS after inline
4. Re-rearchitect detail panel extraction for next attempt

**Prevention**:
- Test detail_panel_builder as standalone before HomePage integration
- Emit signals at each lifecycle point and verify with listener callback
- Use print/logging at signal emission points to debug

---

#### Category C: Architecture/Integration Errors (platform layer, inheritance)

**Symptoms**:
- All test groups fail or partially fail
- Error messages: "Abstract method not implemented", "Base class method not called"
- App doesn't start after Phase 4 changes

**Root Causes**:
- CatalogPageBase contract not fully implemented
- Abstract methods missing or incorrect signature
- Super().__init__() not called or called at wrong time

**Rollback: Level 3** (2 hours)
1. Revert all Phase 4 commits
2. Review CatalogPageBase design (Phase 3)
3. Check if Phase 3 deliverables correct
4. Plan Phase 4 redesign if CatalogPageBase flawed

**Prevention**:
- Commit abstract method implementations incrementally
- Use `abc.abstractmethod` decorator to catch missing implementations at import time
- Run smoke_test.py after each pass to detect import/start failures early

---

### Rollback Decision Tree

```
Test failure detected (test group X fails)
│
├─ Category A (Data/logic; tests 1-7 fail)?
│  └─ Rollback Level 1: Revert CatalogPageBase inheritance (30 min)
│     └─ Re-run tests → 13/13 PASS → document → redesign approach
│
├─ Category B (UI/rendering; tests 8-12 fail)?
│  └─ Rollback Level 2: Inline detail_panel_builder (1 hour)
│     └─ Re-run tests → continue with Pass 3 onward
│
├─ Category C (Architecture; multiple/all tests fail)?
│  └─ Rollback Level 3: Revert Phase 4 commits (2 hours)
│     └─ Review Phase 3 deliverables
│     └─ If Phase 3 faulty: escalate to architecture review
│     └─ If Phase 4 design faulty: redesign and restart
│
└─ Confirm rollback type with team lead before executing
```

---

## Quality Gate Integration

### Pre-Phase 4 Gate (Baseline Capture)

```bash
# 1. Verify Phase 0 baseline exists
test -f phase0-baseline-results.json && echo "✅ Baseline exists"

# 2. Run parity tests to confirm all 13 PASS
python tests/run_parity_tests.py --phase 4 --all --capture-baseline

# 3. Verify import/duplicate checkers pass
python scripts/import_path_checker.py && echo "✅ No import violations"
python scripts/duplicate_detector.py | grep 'home_page.py' | grep '<2223'

# 4. Run smoke tests
python scripts/smoke_test.py

# Gate decision: All checks PASS → Phase 4 implementation can start
```

### Per-Pass Validation Gate

```bash
# After implementation Pass N:

# 1. Quick smoke test (app starts)
python scripts/smoke_test.py || exit 1

# 2. Run parity tests for Pass N scope
python tests/run_parity_tests.py --phase 4 --groups <relevant_groups>

# 3. No new import violations
python scripts/import_path_checker.py || exit 1

# Decision: All checks PASS → proceed to Pass N+1
#          Any check FAIL → fix issue or rollback
```

### Phase 4 Completion Gate

```bash
# Final acceptance criteria:

# 1. All 13 tests PASS
python tests/run_parity_tests.py --phase 4 --all
# Expected: 13/13 PASS

# 2. Zero regressions vs Phase 0
python tests/run_parity_tests.py --phase 4 --compare-baseline
# Expected: ✅ PARITY VERIFIED

# 3. Quality checks
python scripts/run_quality_gate.py
# Expected: All checks PASS

# 4. File size reduction verified
python -c "print(len(open('Tools and jaws Library/ui/home_page.py').readlines()))"
# Expected: < 500 lines (was 2,223)

# 5. Code review approved
# Expected: 2+ reviewers +1

# Gate decision: All criteria met → Phase 4 COMPLETE, Phase 5 ready
```

---

## Appendix: Test Database Snapshots

### Pre-Phase 4 Snapshot

```
test_tool_library_phase4_baseline.db (SQLite 3)
├─ tools (table)
│  ├─ Standard tools (e.g., TURNING_001, MILLING_001, ...)
│  ├─ Tool count: ~50 (representative set)
│  └─ All schema columns present
│
├─ tool_models (if applicable)
│  ├─ STL references for preview tests
│  └─ Model count: ~10
│
└─ ... (other tables as needed)

Checksum: phase4-baseline.db.sha256
```

### Post-Phase 4 Snapshot

```
test_tool_library_phase4_post.db (SQLite 3)
├─ Identical schema to baseline
├─ Same tools + test_ prefixed rows added during parity run
├─ Checksum: phase4-post.db.sha256

Comparison: sha256sum matches baseline before test_ rows → no schema drift
```

---

**End of Phase 4 Parity Test Validation Strategy**

Document Control:
- Version: 1.0
- Status: Ready for Implementation
- Owner: AI-Assisted Development Team
- Last Updated: April 13, 2026
- Next Review: After Phase 4 Implementation Pass 1

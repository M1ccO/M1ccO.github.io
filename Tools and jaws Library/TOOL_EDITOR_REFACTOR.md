# Tool Editor Dialog — Refactoring Log

## Overview

`ui/tool_editor_dialog.py` was refactored across April 2026 to reduce it from a monolithic ~1,400-line file into a thin coordinator that delegates to purpose-built support modules. All extractions were behavior-preserving — no logic was changed, no API surfaces broken.

Support modules live in `ui/tool_editor_support/` (already the established home for this dialog's helpers).

---

## What Changed

### Lines removed from `tool_editor_dialog.py`

| Extraction | Lines removed | Destination |
|---|---|---|
| `ComponentPickerDialog` class + all methods | ~290 | `component_picker_dialog.py` |
| `_get_spare_component_key`, `_set_spare_component_key`, `_schedule_spare_component_refresh`, `_refresh_spare_component_dropdowns`, `_add_spare_part_row` | ~60 | `spare_parts_table_coordinator.py` |
| Inline dialog block in `_link_spares_to_selected_component` | ~78 | `component_linking_dialog.py` |
| **Total** | **~428** | |

Net result: the dialog went from ~1,400 lines to ~970 lines.

---

## New Modules

### `ui/tool_editor_support/component_picker_dialog.py`

**Class:** `ComponentPickerDialog(QDialog)`

A self-contained, searchable dialog for browsing and selecting tool components from existing tool records.

**Responsibilities:**
- Receives a list of component entry dicts (kind, name, code, link) from the caller.
- Renders them in a `QTreeWidget` with search filtering.
- Manages column widths via ratio-based sizing relative to dialog width.
- Returns `selected_entry() -> dict | None` on `QDialog.Accepted`.

**Constructor signature:**
```python
ComponentPickerDialog(
    title: str,
    entries: list[dict],
    parent=None,
    translate: Callable[[str, str | None], str] | None = None,
)
```

**Call site (in `tool_editor_dialog.py`):**
```python
dlg = ComponentPickerDialog(title, entries, self, translate=self._t)
if dlg.exec() != QDialog.Accepted:
    return None
return dlg.selected_entry()
```

---

### `ui/tool_editor_support/spare_parts_table_coordinator.py`

**Class:** `SparePartsTableCoordinator`

Owns spare parts table row management and debounced component dropdown refresh. Extracted from five methods that were previously inlined in the dialog.

**Responsibilities:**
- Adding spare part rows to the table with correct widget setup.
- Managing the component key cell widget (a `QComboBox`) per row.
- Debouncing rapid structural changes via a 75 ms `QTimer` before re-populating dropdowns.
- `shutdown()` — stops the timer cleanly when the dialog closes.

**Constructor signature:**
```python
SparePartsTableCoordinator(
    table: PartsTable,
    component_dropdown_values: Callable[[], list[tuple[str, str]]],
    component_display_for_key: Callable[[str], str],
    refresh_on_structure_change: Callable[[], None],
)
```

**Public API:**
```python
add_spare_part_row(part: dict)
get_component_key(row: int) -> str
set_component_key(row: int, key: str)
set_component_keys_for_rows(rows: list[int], ref: str)
schedule_refresh()
shutdown()
```

**Integration in `__init__`:**
```python
self._spare_parts_coordinator = None  # Initialized after _build_ui()
# ...
self._init_spare_parts_coordinator()
```

---

### `ui/tool_editor_support/component_linking_dialog.py`

**Class:** `ComponentLinkingDialog(QDialog)`

A small modal dialog for selecting which component to link selected spare part rows to. Replaced ~78 lines of inline `QDialog` construction in `_link_spares_to_selected_component`.

**Responsibilities:**
- Renders a labeled `QComboBox` pre-populated with component options (label, key pairs).
- Pre-selects the currently highlighted component if one is provided.
- Returns `selected_component_key() -> str | None` on `QDialog.Accepted`.

**Constructor signature:**
```python
ComponentLinkingDialog(
    options: list[tuple[str, str]],
    preselected_key: str = '',
    parent=None,
    translate: Callable[[str, str | None], str] | None = None,
)
```

**Call site (in `tool_editor_dialog.py`):**
```python
dlg = ComponentLinkingDialog(
    options,
    preselected_key=self._selected_component_ref(),
    parent=self,
    translate=self._t,
)
if dlg.exec() != QDialog.Accepted:
    return
component_ref = dlg.selected_component_key()
```

---

## `__init__.py` Exports

All three new classes are exported from `ui/tool_editor_support/__init__.py`:

```python
from .component_linking_dialog import ComponentLinkingDialog
from .component_picker_dialog import ComponentPickerDialog
from .spare_parts_table_coordinator import SparePartsTableCoordinator
```

---

## Validation

After each extraction:

| Check | Result |
|---|---|
| `python -m py_compile` on new module | PASSED |
| `python -m py_compile` on `tool_editor_dialog.py` | PASSED |
| Pylance syntax errors | None |
| `scripts/import_path_checker.py` | PASSED |
| `scripts/duplicate_detector.py` | 9 collisions — stable, all intentional |
| `scripts/run_quality_gate.py` (7/7 regression tests) | PASSED (after extraction 2) |

Note: `smoke_test.py` reports a failure for the Setup Manager app due to a pre-existing encoding corruption in `Setup Manager/ui/work_editor_dialog.py` (literal `\r\n` characters embedded in source). This is unrelated to the tool editor refactoring.

---

## Architecture Compliance

- All new modules are **app-local** to `Tools and jaws Library` — no shared/ pollution.
- No cross-app imports introduced.
- Baseline of 9 intentional duplicate-detector collisions held stable throughout.
- The `_t` translation function pattern is consistent with all other support modules.

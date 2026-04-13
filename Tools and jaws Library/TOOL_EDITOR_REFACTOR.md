# ⚠️ DEPRECATED: This file has been superseded

**Date**: April 13, 2026  
**Replacement**: See three new documents that govern the Tools and Jaws Library refactoring program:

1. **[TOOLS_JAWS_MODULAR_OVERHAUL_GOALS.md](TOOLS_JAWS_MODULAR_OVERHAUL_GOALS.md)** — Vision and high-level goals for the entire platform overhaul. Read this first to understand WHY the architecture is changing.

2. **[TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md](TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md)** — Rules and constraints for AI agents and contributors. Read this to understand WHAT you can and cannot do during refactoring.

3. **[TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md)** — Current phase status and tracking. Read this to understand WHERE we are now and WHAT phase comes next.

---

## Why This File Was Replaced

The old TOOL_EDITOR_REFACTOR.md documented a **single isolated extraction** (tool editor modularization in April 2026). That work is now complete and frozen.

The three new files above document the **entire program**: a 9-phase overhaul to transform Tools and Jaws Library from duplicated, monolithic domains into a reusable **module platform**.

**Scope Change:**
- OLD: Document one dialog's extraction history
- NEW: Govern 9 phases of work, 3-4 months timeline, AI-agent-friendly handoff

---

## What Happened in April 2026 (Tool Editor Extraction)

For historical reference only: `ui/tool_editor_dialog.py` was reduced from ~1,400L to ~970L by extracting:
- `ComponentPickerDialog` (~290L) → `component_picker_dialog.py`
- Spare parts coordination (~60L) → `spare_parts_table_coordinator.py`
- Component linking dialog (~78L) → `component_linking_dialog.py`

This extraction is **complete and stable**. It serves as a proof-of-concept for the larger modular platform refactoring described in the three new documents.

---

## How to Proceed

1. **Read the new documents** in order: GOALS → RULES → STATUS
2. **Check current phase** in TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md
3. **Understand constraints** in TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md
4. **Contribute according to rules** for your assigned phase

Do not reference this deprecated file; it is kept only for historical context.**
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

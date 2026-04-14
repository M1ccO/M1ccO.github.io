# Measurement Editor Refactor Plan

Last updated: 2026-04-14

---

## Overview

`Tools and jaws Library/ui/measurement_editor_dialog.py` is currently **~2,647 lines** — a single monolithic `MeasurementEditorDialog` class that owns UI build, all four measurement type editors (distance, diameter, radius, angle), point-pick dispatch, axis overlays, list management, preview sync, and the output API.

A support subpackage `ui/measurement_editor/` already exists and holds pure-logic modules (models, controllers, forms, bridge, utils). Those modules are fine and must not be changed. The problem is that the dialog class was never slimmed down after those extractions.

**Target:** Reduce `measurement_editor_dialog.py` to a thin orchestrator of ~450–550 lines by extracting stateful coordinator logic into new modules inside the existing `ui/measurement_editor/` subpackage.

---

## Goals

1. `measurement_editor_dialog.py` becomes a thin orchestrator: it builds the UI, creates coordinator objects, wires callbacks, and exposes `get_measurements()` / `accept()`. No measurement-type-specific logic inside.
2. Each new support module has one clear responsibility. No module exceeds ~300 lines.
3. Zero behavior change. The public API (`__init__`, `get_measurements()`, `accept()`) must be identical before and after.
4. No new inter-app imports. No imports from `Setup Manager/` inside any `Tools and jaws Library/` module.
5. All imports follow the canonical paths in `AGENTS.md`. No legacy shared paths.
6. The existing `ui/measurement_editor/` submodules (models, controllers, forms, bridge, utils) are read-only during this refactor — do not modify them.
7. After each step: run `python -m py_compile "Tools and jaws Library/ui/measurement_editor_dialog.py"` and all new files. Run `python scripts/run_quality_gate.py` before marking the step DONE.

---

## Rules

- **Behavior-preserving only.** No feature adds, no UI changes, no payload schema changes.
- **No compatibility shims.** Do not add forwarding wrapper methods in the dialog unless unavoidable and marked `# SHIM: remove after <step>`.
- **Coordinator classes use callback injection, not a `host` reference.** Do not pass `self` (the dialog) into a coordinator. Instead inject specific callables. This keeps coordinators independently readable.
- **Widget refs are injected at construction time** via the `*FormRefs` dataclasses already returned by the existing `forms/` builders. Do not re-query widgets with `findChild` or by name.
- **Edit models live in the coordinator** that owns the measurement type. The dialog no longer holds `_distance_edit_model` or `_diameter_edit_model` directly — it calls through to the coordinator.
- **`_pick_target`, `_dist_pick_stage`, `_diam_pick_stage`** are cross-cutting state used by the pick dispatcher. These may remain on the dialog or be moved to a `PickState` dataclass held by the dialog. Either is acceptable.
- Keep refactor passes small and single-responsibility. One step = one new file.

---

## Current State (before refactor)

```
Tools and jaws Library/ui/
  measurement_editor_dialog.py          ← 2,647 lines — ALL logic here
  measurement_editor/                   ← existing subpackage (DO NOT MODIFY)
    __init__.py
    models/
      distance.py                       ← compose_distance_commit_payload, normalize_distance_measurement
      diameter.py                       ← compose_diameter_commit_payload, normalize_diameter_measurement
      radius.py                         ← normalize_radius_measurement
      angle.py                          ← normalize_angle_measurement
    controllers/
      distance_controller.py            ← pure helper fns: adjust_target_key, axis_sign, etc.
      diameter_controller.py            ← pure helper fns: adjust_mode, geometry_target, etc.
      measurement_registry.py           ← measurement_kind_order, find_item_by_uid
    forms/
      distance_form.py                  ← build_distance_form → (container, DistanceFormRefs)
      diameter_form.py                  ← build_diameter_form → (container, DiameterFormRefs)
      radius_form.py                    ← build_radius_form   → (container, RadiusFormRefs)
      angle_form.py                     ← build_angle_form    → (container, AngleFormRefs)
      shared_sections.py                ← apply_section_groupbox_style, build_*_header_row
      type_picker.py                    ← build_measurement_type_picker
    bridge/
      preview_sync.py                   ← apply_*_overlay_update, compose_preview_overlays
    utils/
      coordinates.py                    ← xyz_to_tuple, fmt_coord, float_or_default
      axis_math.py                      ← axis_xyz_text, normalize_*, rotation helpers
```

---

## Target State (after refactor)

```
Tools and jaws Library/ui/
  measurement_editor_dialog.py          ← ~450–550 lines, thin orchestrator
  measurement_editor/
    (all existing modules — unchanged)
    NEW:
    coordinators/
      __init__.py
      list_manager.py                   ← MeasurementListManager — list add/remove/rebuild/populate
      distance_editor.py                ← DistanceEditorCoordinator — distance state, setters, commit
      diameter_editor.py                ← DiameterEditorCoordinator — diameter state, setters, commit
      pick_coordinator.py               ← PickCoordinator — _on_point_picked dispatch + cancel
      axis_overlay.py                   ← AxisOverlayController — overlay widget positioning + sync
      preview_coordinator.py            ← refresh_preview_measurements, sync_before_save, on_measurement_updated
    utils/
      edit_helpers.py                   ← set_xyz_edits, xyz_text_from_edits, focused_axis  (static helpers extracted from dialog)
```

---

## Step-by-Step Implementation Plan

Each step is self-contained and safe to implement independently. Complete them in order.

---

### STEP 1 — Extract XYZ edit helpers into `utils/edit_helpers.py`

**Status:** TODO

**What to do:**
Create `Tools and jaws Library/ui/measurement_editor/utils/edit_helpers.py` with the three static helpers currently in the dialog:

```python
"""Static helpers for reading and writing QLineEdit XYZ triplets."""
from __future__ import annotations
from PySide6.QtWidgets import QLineEdit
from .coordinates import xyz_to_tuple, fmt_coord


def set_xyz_edits(
    edits: tuple[QLineEdit, QLineEdit, QLineEdit],
    value,
) -> None:
    x, y, z = xyz_to_tuple(value)
    edits[0].setText(fmt_coord(x))
    edits[1].setText(fmt_coord(y))
    edits[2].setText(fmt_coord(z))


def xyz_text_from_edits(edits: tuple[QLineEdit, QLineEdit, QLineEdit]) -> str:
    values = []
    defaults = [0.0, 0.0, 0.0]
    for i, edit in enumerate(edits):
        text = edit.text().strip().replace(',', '.')
        try:
            values.append(float(text))
        except Exception:
            values.append(defaults[i])
    return f"{fmt_coord(values[0])}, {fmt_coord(values[1])}, {fmt_coord(values[2])}"


def focused_axis(edits: tuple[QLineEdit, QLineEdit, QLineEdit]) -> str:
    if edits[0].hasFocus():
        return 'x'
    if edits[1].hasFocus():
        return 'y'
    if edits[2].hasFocus():
        return 'z'
    return 'all'
```

In the dialog, replace the three private methods (`_set_xyz_edits`, `_xyz_text_from_edits`, `_focused_axis`) with delegation to the new module:

```python
from ui.measurement_editor.utils.edit_helpers import (
    set_xyz_edits as _set_xyz_edits_fn,
    xyz_text_from_edits as _xyz_text_from_edits_fn,
    focused_axis as _focused_axis_fn,
)
# Then in each method:
def _set_xyz_edits(self, edits, value): _set_xyz_edits_fn(edits, value)
def _xyz_text_from_edits(self, edits): return _xyz_text_from_edits_fn(edits)
@staticmethod
def _focused_axis(edits): return _focused_axis_fn(edits)
```

**Verification:**
- `python -m py_compile "Tools and jaws Library/ui/measurement_editor_dialog.py"`
- `python -m py_compile "Tools and jaws Library/ui/measurement_editor/utils/edit_helpers.py"`
- `python scripts/run_quality_gate.py`

---

### STEP 2 — Create `coordinators/__init__.py`

**Status:** TODO

**What to do:**
Create `Tools and jaws Library/ui/measurement_editor/coordinators/__init__.py` as an empty file (or with a single `# Coordinator modules for MeasurementEditorDialog` comment). This initializes the package.

---

### STEP 3 — Extract `DistanceEditorCoordinator` into `coordinators/distance_editor.py`

**Status:** TODO

**Responsibility:** All distance-type-specific state, setters, commit, and nudge logic. Does NOT handle point-pick dispatch (that stays in the dialog or later moves to `pick_coordinator.py`).

**Methods to extract from `MeasurementEditorDialog`:**

| Dialog method | Coordinator method |
|---|---|
| `_distance_precise_mode_enabled` | `precise_mode_enabled` |
| `_distance_value_mode` | `value_mode` |
| `_set_distance_value_mode(mode, commit)` | `set_value_mode(mode, commit)` |
| `_on_distance_value_mode_toggled` | `on_value_mode_toggled` |
| `_distance_adjust_mode` | `adjust_mode` |
| `_distance_nudge_point` | `nudge_point` |
| `_distance_adjust_edits` | `adjust_edits` (property) |
| `_distance_adjust_target_key(mode, point)` | `adjust_target_key(mode, point)` |
| `_distance_adjust_active_axis_value` | `adjust_active_axis_value` |
| `_update_distance_adjust_tooltips` | `update_adjust_tooltips` |
| `_distance_axis_sign(model, axis)` | `axis_sign(model, axis)` |
| `_distance_effective_point_xyz_text(point)` | `effective_point_xyz_text(point)` |
| `_load_distance_adjust_edits_from_model` | `load_adjust_edits_from_model` |
| `_store_distance_adjust_edits_to_model(target_key)` | `store_adjust_edits_to_model(target_key)` |
| `_update_distance_adjust_controls(refresh_values)` | `update_adjust_controls(refresh_values)` |
| `_set_distance_adjust_mode(mode, commit)` | `set_adjust_mode(mode, commit)` |
| `_on_distance_adjust_mode_toggled` | `on_adjust_mode_toggled` |
| `_set_distance_nudge_point(point, commit)` | `set_nudge_point(point, commit)` |
| `_on_nudge_point_toggled` | `on_nudge_point_toggled` |
| `_distance_axis_value` | `axis_value` (property) |
| `_set_distance_axis(axis, commit)` | `set_axis(axis, commit)` |
| `_distance_measured_value_text` | `measured_value_text` |
| `_update_distance_measured_value_box` | `update_measured_value_box` |
| `_update_distance_pick_status` | `update_pick_status` |
| `_commit_distance_edit(sync_adjust_edits)` | `commit_edit(sync_adjust_edits)` |
| `_start_distance_two_point_pick(reset_points)` | `start_two_point_pick(reset_points)` |
| `_on_distance_point_nudge(direction)` | `on_point_nudge(direction)` |
| `_populate_distance_form(meas)` | `populate_form(meas)` |

**Constructor signature:**
```python
class DistanceEditorCoordinator:
    def __init__(
        self,
        refs,                              # DistanceFormRefs from build_distance_form
        translate: Callable,               # dialog._t
        icon: Callable,                    # dialog._icon
        precise_mode_enabled: Callable,    # () -> bool — reads _distance_detail_mode_btn
        on_commit_done: Callable,          # () -> None — calls dialog._refresh_preview_measurements
        on_pick_start: Callable,           # (pick_target: str) -> None — sets dialog._pick_target and enables picking
        on_pick_cancel: Callable,          # () -> None — dialog._cancel_pick
        on_name_changed: Callable,         # (uid: str, name: str) -> None — update all-list label
        on_axis_overlay_needed: Callable,  # () -> None — sync axis pick overlay visibility
        preview_widget,                    # StlPreviewWidget ref
    ): ...
    
    # Mutable state owned by this coordinator:
    edit_model: dict | None = None
    _dist_axis_value: str = 'z'
    _dist_adjust_active_axis: str = 'x'
```

**In the dialog**, after building the distance form with `_build_distance_form_fn(...)`:
```python
self._distance_editor = DistanceEditorCoordinator(
    refs=distance_refs,
    translate=self._t,
    icon=self._icon,
    precise_mode_enabled=lambda: self._distance_detail_mode_btn.isChecked(),
    on_commit_done=self._refresh_preview_measurements,
    on_pick_start=self._set_pick_target,
    on_pick_cancel=self._cancel_pick,
    on_name_changed=lambda uid, name: self._update_selected_measurement_name_in_all_list('length', uid, name),
    on_axis_overlay_needed=self._sync_axis_pick_overlay_visibility,
    preview_widget=self._preview_widget,
)
```

Each dialog method that used to contain distance logic becomes a one-line delegation:
```python
def _commit_distance_edit(self, sync_adjust_edits=True):
    self._distance_editor.commit_edit(sync_adjust_edits)

def _set_distance_axis(self, axis, commit=True):
    self._distance_editor.set_axis(axis, commit)
```

The thin wrapper methods in the dialog may be left for one refactor cycle, then removed in a follow-up cleanup step.

**Verification:**
- `python -m py_compile` on dialog and new file
- `python scripts/run_quality_gate.py`

---

### STEP 4 — Extract `DiameterEditorCoordinator` into `coordinators/diameter_editor.py`

**Status:** TODO

**Responsibility:** All diameter-type-specific state, setters, commit, pick-start, and nudge logic.

**Methods to extract from `MeasurementEditorDialog`:**

| Dialog method | Coordinator method |
|---|---|
| `_diameter_value_mode` | `value_mode` |
| `_set_diameter_value_mode(mode, commit)` | `set_value_mode(mode, commit)` |
| `_on_diameter_value_mode_toggled` | `on_value_mode_toggled` |
| `_diameter_axis_value` | `axis_value` (property) |
| `_set_diameter_axis(axis, commit, store_adjust_edits)` | `set_axis(axis, commit, store_adjust_edits)` |
| `_diameter_overlay_index` | `overlay_index` (property) — needs distance_list.count() passed in |
| `_diameter_adjust_edits` | `adjust_edits` (property) |
| `_diameter_adjust_mode` | `adjust_mode` |
| `_diameter_geometry_target` | `geometry_target` |
| `_diameter_adjust_target_key(mode, geometry_target)` | `adjust_target_key(mode, geometry_target)` |
| `_diameter_adjust_active_axis_value` | `adjust_active_axis_value` |
| `_ensure_diameter_rotation_target_value` | `ensure_rotation_target_value` |
| `_diameter_visual_offset_mm(model)` | `visual_offset_mm(model)` |
| `_load_diameter_visual_offset_edit_from_model` | `load_visual_offset_from_model` |
| `_store_diameter_visual_offset_edit_to_model` | `store_visual_offset_to_model` |
| `_update_diameter_adjust_tooltips` | `update_adjust_tooltips` |
| `_load_diameter_adjust_edits_from_model` | `load_adjust_edits_from_model` |
| `_store_diameter_adjust_edits_to_model(target_key)` | `store_adjust_edits_to_model(target_key)` |
| `_update_diameter_adjust_controls(refresh_values)` | `update_adjust_controls(refresh_values)` |
| `_set_diameter_adjust_mode(mode, commit)` | `set_adjust_mode(mode, commit)` |
| `_on_diameter_adjust_mode_toggled` | `on_adjust_mode_toggled` |
| `_set_diameter_geometry_target(target, commit)` | `set_geometry_target(target, commit)` |
| `_on_diameter_geometry_target_toggled` | `on_geometry_target_toggled` |
| `_diameter_measured_numeric` | `measured_numeric` |
| `_update_diameter_measured_value_box` | `update_measured_value_box` |
| `_update_diameter_pick_status` | `update_pick_status` |
| `_diameter_has_manual_value(model)` | `has_manual_value(model)` |
| `_diameter_is_complete(model)` | `is_complete(model)` |
| `_prompt_diameter_value_near_cursor` | `prompt_value_near_cursor` |
| `_start_diameter_edge_pick` | `start_edge_pick` |
| `_start_diameter_pick(reset_points)` | `start_pick(reset_points)` |
| `_auto_start_diameter_pick_if_needed` | `auto_start_pick_if_needed` |
| `_on_pick_diameter_points` | `on_pick_points` |
| `_on_diameter_offset_nudge(direction)` | `on_offset_nudge(direction)` |
| `_populate_diameter_form(meas)` | `populate_form(meas)` |
| `_commit_diameter_edit(sync_adjust_edits)` | `commit_edit(sync_adjust_edits)` |

**Constructor signature:**
```python
class DiameterEditorCoordinator:
    def __init__(
        self,
        refs,                              # DiameterFormRefs from build_diameter_form
        translate: Callable,
        icon: Callable,
        on_commit_done: Callable,          # () -> None — calls _refresh_preview_measurements
        on_pick_start: Callable,           # (pick_target: str, stage: str) -> None
        on_pick_cancel: Callable,          # () -> None
        on_name_changed: Callable,         # (uid: str, name: str) -> None
        on_axis_overlay_needed: Callable,  # () -> None
        on_axis_overlay_buttons_update: Callable,  # () -> None
        ensure_uid: Callable,              # (payload: dict) -> str
        preview_widget,
        distance_list_count: Callable,     # () -> int  (for overlay_index calculation)
    ): ...

    # Mutable state owned by this coordinator:
    edit_model: dict | None = None
    _diam_axis_value: str = 'z'
    _diam_adjust_active_axis: str = 'x'
    _pick_target: str | None = None       # NOTE: This may stay on the dialog — see pick_coordinator
```

**Note on `_pick_target` ownership:**
`_pick_target` and `_diam_pick_stage` are read by the point-pick dispatcher and the axis overlay. Keep them on the dialog for now (as properties) and inject via `on_pick_start` / `on_pick_cancel` callbacks. The coordinator does NOT store `_pick_target` itself.

**Verification:** Same as Step 3.

---

### STEP 5 — Extract `AxisOverlayController` into `coordinators/axis_overlay.py`

**Status:** TODO

**Responsibility:** Positioning, visibility, and button-state of the `_axis_pick_overlay` and `_axis_hint_overlay` frames that float over the preview container.

**Methods to extract:**

| Dialog method | Controller method |
|---|---|
| `_update_axis_overlay_buttons` | `update_buttons` |
| `_position_axis_overlay` | `position_axis_overlay` |
| `_position_axis_hint_overlay` | `position_axis_hint_overlay` |
| `_update_axis_hint_overlay_visibility` | `update_hint_visibility` |
| `_show_axis_pick_overlay` | `show` (calls `sync_visibility`) |
| `_sync_axis_pick_overlay_visibility` | `sync_visibility` |
| `_on_axis_overlay_selected(axis_val)` | `on_axis_selected(axis_val)` |

**Constructor signature:**
```python
class AxisOverlayController:
    def __init__(
        self,
        axis_pick_overlay,       # QFrame widget
        axis_hint_overlay,       # QFrame widget
        axis_overlay_btns: dict, # {axis_val: QPushButton}
        preview_container,       # QWidget
        preview_widget,          # StlPreviewWidget
        active_kind: Callable,   # () -> str | None — returns current active measurement kind
        dist_axis_value: Callable,    # () -> str
        diam_axis_value: Callable,    # () -> str
        diam_is_complete: Callable,   # () -> bool
        current_diam_item: Callable,  # () -> QListWidgetItem | None
        pick_target: Callable,        # () -> str | None
        on_axis_selected: Callable,   # (axis_val: str, kind: str) -> None  — calls set_distance_axis or set_diameter_axis
        precise_mode_enabled: Callable,  # () -> bool
    ): ...
```

In the dialog, after building all widgets:
```python
self._axis_overlay_ctrl = AxisOverlayController(
    axis_pick_overlay=self._axis_pick_overlay,
    axis_hint_overlay=self._axis_hint_overlay,
    axis_overlay_btns=self._axis_overlay_btns,
    preview_container=self._preview_container,
    preview_widget=self._preview_widget,
    active_kind=self._active_measurement_kind,
    dist_axis_value=lambda: self._distance_editor.axis_value,
    diam_axis_value=lambda: self._diameter_editor.axis_value,
    diam_is_complete=lambda: self._diameter_editor.is_complete(),
    current_diam_item=lambda: self._current_diameter_item,
    pick_target=lambda: self._pick_target,
    on_axis_selected=self._on_axis_overlay_selected,
    precise_mode_enabled=lambda: self._distance_detail_mode_btn.isChecked(),
)
```

**Verification:** Same as before.

---

### STEP 6 — Extract `MeasurementListManager` into `coordinators/list_manager.py`

**Status:** TODO

**Responsibility:** Managing the unified `_measurement_all_list` and the four hidden type lists. Add/remove/rebuild/populate operations.

**Methods to extract:**

| Dialog method | Manager method |
|---|---|
| `_ensure_measurement_uid(payload)` | `ensure_uid(payload)` |
| `_hidden_list_for_kind(kind)` | `list_for_kind(kind)` |
| `_active_measurement_kind` | — keep on dialog (reads `_current_*_item`) |
| `_selected_measurement_meta` | `selected_meta` |
| `_find_item_by_uid(src_list, uid)` | delegates to existing `measurement_registry.find_item_by_uid` |
| `_clear_current_measurement_refs` | `clear_current_refs` (also clears dialog's `_current_*_item`) |
| `_rebuild_measurement_all_list(preferred_kind, preferred_uid)` | `rebuild_all_list(preferred_kind, preferred_uid)` |
| `_update_selected_measurement_name_in_all_list(kind, uid, name)` | `update_name_in_all_list(kind, uid, name)` |
| `_on_all_measurement_selected` | `on_all_measurement_selected` |
| `_add_measurement_of_kind(kind)` | `add_of_kind(kind)` |
| `_cancel_add_measurement_type_picker` | `cancel_add_type_picker` |
| `_show_add_measurement_type_picker` | `show_add_type_picker` |
| `_normalize_*_measurement` × 4 | `normalize_measurement(kind, meas)` dispatcher |
| `_populate_measurements` | `populate_from_tool_data(tool_data)` |
| `_add_*_measurement` × 4 | dispatched from `add_of_kind` |
| `_remove_*_measurement` × 4 | dispatched from `remove_current` |
| `_remove_current_measurement` | `remove_current` |

**Constructor signature:**
```python
class MeasurementListManager:
    def __init__(
        self,
        all_list,                  # QListWidget — the unified list
        distance_list,             # QListWidget
        diameter_list,             # QListWidget
        radius_list,               # QListWidget
        angle_list,                # QListWidget
        edit_stack,                # QStackedWidget
        add_type_picker_page_index: int,
        add_type_cancel_btn,       # QPushButton
        translate: Callable,
        ensure_uid: Callable,      # (payload: dict) -> str  — uses internal counter
        on_edit_stack_kind_changed: Callable,  # (kind: str | None) -> None  — calls update_distance_mode_controls_visibility
        on_refresh_preview: Callable,
        on_cancel_pick: Callable,
        on_start_distance_pick: Callable,      # (reset_points: bool) -> None
        on_auto_start_diameter_pick: Callable, # () -> None
        on_populate_distance_form: Callable,   # (meas: dict) -> None
        on_populate_diameter_form: Callable,   # (meas: dict) -> None
        on_populate_radius_form: Callable,     # (meas: dict) -> None
        on_populate_angle_form: Callable,      # (meas: dict) -> None
        set_current_distance_item: Callable,   # (item | None) -> None
        set_current_diameter_item: Callable,
        set_current_radius_item: Callable,
        set_current_angle_item: Callable,
        get_current_distance_item: Callable,
        get_current_diameter_item: Callable,
        get_current_radius_item: Callable,
        get_current_angle_item: Callable,
    ): ...
```

**Note on `_current_*_item`:** These are referenced from many places (pick coordinator, commit, preview refresh). To avoid deep coupling, keep them as attributes on the dialog and inject getter/setter callables into the list manager and other coordinators.

**Verification:** Same as before.

---

### STEP 7 — Extract `PickCoordinator` into `coordinators/pick_coordinator.py`

**Status:** TODO

**Responsibility:** Owns the `_pick_target` state and dispatches point-picked events to the appropriate coordinator. Also owns `_cancel_pick`.

**Methods to extract:**

| Dialog method | Coordinator method |
|---|---|
| `_cancel_pick` | `cancel` |
| `_on_pick_target` | `on_pick_target` |
| `_on_pick_radius_center` | `on_pick_radius_center` |
| `_on_pick_angle_center` | `on_pick_angle_center` |
| `_on_pick_angle_start` | `on_pick_angle_start` |
| `_on_pick_angle_end` | `on_pick_angle_end` |
| `_start_angle_pick(target_prefix, btn, edits)` | `start_angle_pick(...)` |
| `_on_point_picked(data)` | `on_point_picked(data)` |

**Constructor signature:**
```python
class PickCoordinator:
    def __init__(
        self,
        preview_widget,
        translate: Callable,
        icon: Callable,
        # Widget refs for resetting pick button icons on cancel:
        dist_pick_btn,
        diam_pick_btn,
        radius_center_pick_btn,
        angle_center_pick_btn,
        angle_start_pick_btn,
        angle_end_pick_btn,
        # XYZ edit tuples for radius/angle:
        radius_center_edits: tuple,
        radius_part_edit,
        angle_center_edits: tuple,
        angle_start_edits: tuple,
        angle_end_edits: tuple,
        angle_part_edit,
        # Coordinator callbacks:
        distance_editor,           # DistanceEditorCoordinator — for target_xyz dispatch
        diameter_editor,           # DiameterEditorCoordinator — for diameter_* dispatch
        get_current_distance_item: Callable,
        get_current_diameter_item: Callable,
        on_commit_radius: Callable,
        on_commit_angle: Callable,
        on_update_distance_pick_status: Callable,
        on_update_diameter_pick_status: Callable,
        on_sync_axis_overlay: Callable,
    ): ...

    # Mutable pick state owned here:
    pick_target: str | None = None
    dist_pick_stage: str | None = None
    diam_pick_stage: str | None = None
```

**Important:** After this step, the dialog's `_pick_target`, `_dist_pick_stage`, `_diam_pick_stage` attributes become properties that read from `self._pick_coordinator.pick_target` etc., so all existing code that was not yet refactored continues to work.

**Verification:** Same as before.

---

### STEP 8 — Extract `PreviewCoordinator` into `coordinators/preview_coordinator.py`

**Status:** TODO

**Responsibility:** `_refresh_preview_measurements`, `_sync_preview_measurements_before_save`, `_on_measurement_updated`.

**Extract as module-level functions** (no class needed — stateless):
```python
def refresh_preview_measurements(
    preview_widget,
    distance_list, diameter_list, radius_list, angle_list,
    current_distance_item,
    normalize_distance: Callable,
    normalize_diameter: Callable,
    normalize_radius: Callable,
    normalize_angle: Callable,
    distance_precise_mode_enabled: bool,
    distance_adjust_mode: str,
    distance_nudge_point: str,
) -> None: ...

def sync_preview_before_save(preview_widget, on_measurement_updated: Callable) -> None: ...

def on_measurement_updated(
    payload: dict,
    distance_list,
    diameter_list,
    current_distance_item,
    current_diameter_item,
    on_distance_model_updated: Callable,   # (item, data) -> None
    on_diameter_model_updated: Callable,   # (item, data) -> None
    on_refresh_preview: Callable,
) -> None: ...
```

**Verification:** Same as before.

---

### STEP 9 — Clean up thin wrapper methods in the dialog

**Status:** TODO

After Steps 1–8, the dialog will contain many one-line delegations like:
```python
def _commit_distance_edit(self, sync=True): self._distance_editor.commit_edit(sync)
```

Audit each one. If the wrapper is called **only from inside the dialog** and is always a direct delegation, inline the coordinator call at the call site and remove the wrapper. If the wrapper is part of the dialog's internal API called from more than one place, keep it.

Target: reduce dialog to ≤ 550 lines after cleanup.

**Verification:**
- Full quality gate: `python scripts/run_quality_gate.py`
- Manual smoke test: launch `python "Tools and jaws Library/main.py"` and open the Measurement Editor from any tool, verify all four measurement types, point picking, and Save/Cancel work correctly.

---

### STEP 10 — Update AGENTS.md and docs

**Status:** TODO

Add `measurement_editor_dialog.py` + its coordinator subpackage to the **Navigation Map** in `AGENTS.md`:

```markdown
### Measurement Editor (add/edit measurements on tools)
Tools and jaws Library/ui/
  measurement_editor_dialog.py              ← thin orchestrator
  measurement_editor/
    coordinators/
      list_manager.py                       ← MeasurementListManager
      distance_editor.py                    ← DistanceEditorCoordinator
      diameter_editor.py                    ← DiameterEditorCoordinator
      pick_coordinator.py                   ← PickCoordinator + pick state
      axis_overlay.py                       ← AxisOverlayController
      preview_coordinator.py                ← preview refresh/sync functions
    (all existing submodules remain unchanged)
```

Update the `module-registry.json` under `Tools and jaws Library/docs/` to register the new files with `status: "active"`.

---

## File Size Targets

| File | Current | Target after refactor |
|---|---|---|
| `measurement_editor_dialog.py` | ~2,647 L | ≤ 550 L |
| `coordinators/list_manager.py` | — | ~200 L |
| `coordinators/distance_editor.py` | — | ~280 L |
| `coordinators/diameter_editor.py` | — | ~350 L |
| `coordinators/pick_coordinator.py` | — | ~200 L |
| `coordinators/axis_overlay.py` | — | ~100 L |
| `coordinators/preview_coordinator.py` | — | ~90 L |
| `utils/edit_helpers.py` | — | ~40 L |

---

## Non-Negotiables

- No payload shape changes (`get_measurements()` return dict keys must be identical).
- No user-visible workflow changes (pick sequences, overlay behavior, save/cancel behavior).
- No new cross-app imports.
- All imports use the canonical paths in `AGENTS.md`.
- No existing `ui/measurement_editor/` module is modified (read-only during this refactor).
- `python scripts/run_quality_gate.py` must pass after every step.
- If a step fails validation, fix it before proceeding to the next step.

---

## Notes

- Steps 3 and 4 (distance + diameter coordinators) are the largest steps. If needed, each can be split into two sub-steps: first extract without callback injection (just move methods, pass `dialog` temporarily), then add proper callback injection in a second pass.
- The radius and angle editors are lightweight enough (~50–80 lines each) that they do not need their own coordinator classes. Their populate/commit logic can remain in the dialog or be folded into `list_manager.py` as simple functions.
- `_update_distance_mode_controls_visibility` is a shared UI sync method (enables/disables the remove button, shows/hides the precise-mode toggle). It depends on `_active_measurement_kind()` which cross-cuts all four types. Keep this method on the dialog or in a small `ui_sync.py` helper — do not put it inside any single-type coordinator.

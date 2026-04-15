# Named Machine Configuration System

Technical documentation for the multi-machine configuration feature added across two sessions.

---

## Table of Contents

1. [Overview](#overview)
2. [Data Model](#data-model)
3. [File: `shared/services/machine_config_service.py`](#shared-services-machine_config_servicepy)
4. [File: `Setup Manager/config.py`](#setup-manager-configpy)
5. [File: `Setup Manager/main.py`](#setup-manager-mainpy)
6. [File: `Setup Manager/ui/main_window.py`](#setup-manager-ui-main_windowpy)
7. [File: `Setup Manager/ui/machine_config_dialog.py`](#setup-manager-ui-machine_config_dialogpy)
8. [File: `Setup Manager/ui/preferences_dialog.py`](#setup-manager-ui-preferences_dialogpy)
9. [File: `Setup Manager/ui/main_window_support/preferences_actions.py`](#setup-manager-ui-main_window_support-preferences_actionspy)
10. [File: `shared/services/ui_preferences_service.py`](#shared-services-ui_preferences_servicepy)
11. [JSON Storage Format](#json-storage-format)
12. [Live Switching — Control Flow](#live-switching--control-flow)
13. [Shared Database Logic](#shared-database-logic)
14. [Shared DB Notice System](#shared-db-notice-system)
15. [First-Run Migration](#first-run-migration)
16. [Further Implementation Paths](#further-implementation-paths)
17. [Known Limitations and Improvement Areas](#known-limitations-and-improvement-areas)

---

## Overview

The system replaces the old single-machine, single-database startup with a named configuration
manager. Each **machine configuration** is an independent bundle of:

- A human-readable name (e.g. `"NTX2500 Line B"`)
- A machine profile key (e.g. `"ntx_2sp_2h"`, controls which UI tabs and measurement columns appear)
- An absolute path to a Setup Manager SQLite database
- An optional absolute path to a Tools Library SQLite database (empty = app default)
- An optional absolute path to a Jaws Library SQLite database (empty = app default)
- A UTC ISO-8601 timestamp of when the config was last switched away from (`last_used_at`)

Multiple configs can point to the **same** database file path (shared DB), meaning edits made
under one config are immediately visible to any other config that shares the same path.

The active config can be switched **live** — no restart, no unsaved-changes prompt — by
re-creating all services and a new `MainWindow` in place.

---

## Data Model

```python
@dataclass
class MachineConfig:
    id: str                  # "config_ntx2500_a3b4c5"  (stable, never changes)
    name: str                # "NTX2500"  (user-editable display name)
    machine_profile_key: str # "ntx_2sp_2h"  (profile that drives UI tab set)
    setup_db_path: str       # absolute path to setup_manager.db
    tools_db_path: str       # absolute path to tools .db, or "" for app default
    jaws_db_path: str        # absolute path to jaws .db, or "" for app default
    last_used_at: str        # ISO-8601 UTC — stamped when LEAVING this config
```

`id` format: `config_{sanitized_name}_{6-char-hex}` where the sanitized name is
`re.sub(r"[^\w]", "_", name).strip("_").lower()`. Example: `"NTX 2500 / Line-B"` →
`config_ntx_2500_line_b_3fcffa`.

---

## File: `shared/services/machine_config_service.py`

New file. Full CRUD service. Reads/writes `.runtime/machine_configurations.json`.

### Key methods

| Method | Description |
|---|---|
| `is_empty()` | True when no configs exist yet (first ever run) |
| `list_configs()` | Returns a copy of the internal list |
| `get_config(id)` | Returns `MachineConfig` or `None` |
| `get_active_config()` | Returns active config, falls back to `_configs[0]` |
| `create_config(name, machine_profile_key, ...)` | Generates stable `id`, auto-generates `setup_db_path` if empty, appends, saves |
| `update_config(id, **changes)` | Replaces the matching entry with updated fields, saves |
| `delete_config(id)` | Raises `ValueError` if last config or active config |
| `set_active_config_id(id)` | Sets `_active_id`, saves |
| `update_last_used(id)` | Stamps `last_used_at` = `datetime.now(timezone.utc).isoformat()`, saves |
| `configs_sharing_path(path, exclude_id)` | Scans all configs for any DB field equal to `path`, returns matches |
| `migrate_from_legacy(...)` | Wraps `create_config`; used only on first run when `is_empty()` |

### Auto-generated setup_db_path

When `create_config` receives an empty `setup_db_path`:

```python
short_id = uuid.uuid4().hex[:6]
config_id = f"config_{_sanitize_folder_name(name)}_{short_id}"
resolved_setup_db = str(
    runtime_dir / "configs" / config_id / "setup_manager.db"
)
```

This produces a human-readable folder like `.runtime/configs/config_ntx2500_a3b4c5/setup_manager.db`.
The `config_id` is reused as both the stable identifier and the folder name.

### `_save()` implementation

Serialises the full list with `dataclasses.asdict` and writes atomically via
`Path.write_text`. No temp-file rename — acceptable for this use case since
the file is small and writes are infrequent.

---

## File: `Setup Manager/config.py`

Added one constant:

```python
MACHINE_CONFIGS_PATH = RUNTIME_DIR / "machine_configurations.json"
```

This is imported by `main.py` and passed to `MachineConfigService.__init__`.

---

## File: `Setup Manager/main.py`

### Startup sequence change

Before this feature, `main.py` opened `DB_PATH` unconditionally. Now:

```python
machine_config_svc = MachineConfigService(MACHINE_CONFIGS_PATH, RUNTIME_DIR)

if machine_config_svc.is_empty():
    # First ever run: no JSON file exists yet.
    # Use legacy DB_PATH; will create the migration config after profile key is known.
    active_setup_db_path = str(DB_PATH)
    active_tools_db_path = str(TOOL_LIBRARY_DB_PATH)
    active_jaws_db_path  = str(JAW_LIBRARY_DB_PATH)
else:
    _active_cfg = machine_config_svc.get_active_config()
    active_setup_db_path = _active_cfg.setup_db_path or str(DB_PATH)
    active_tools_db_path = _active_cfg.tools_db_path or str(TOOL_LIBRARY_DB_PATH)
    active_jaws_db_path  = _active_cfg.jaws_db_path  or str(JAW_LIBRARY_DB_PATH)
```

After the profile key is determined (either from the DB or from the setup wizard):

```python
if machine_config_svc.is_empty():
    machine_config_svc.migrate_from_legacy(
        name="NTX2500",
        machine_profile_key=db_profile_key,
        setup_db_path=active_setup_db_path,
    )
```

### `_do_live_switch(new_config_id: str)` closure

Lives inside `main()`. Uses `nonlocal` to update `win`, `work_service`,
`logbook_service`, `draw_service` so the IPC `show_setup_manager` closure always
references the current window.

```
1. Stamp last_used_at on the config being LEFT
2. machine_config_svc.set_active_config_id(new_config_id)
3. win._suppress_quit = True  →  win.close()  →  win.deleteLater()
4. QApplication.setOverrideCursor(WaitCursor)
5. Recreate Database, WorkService, LogbookService, DrawService, update PrintService ref
6. _prefs_svc.set_machine_profile_key(active.machine_profile_key)
7. QApplication.restoreOverrideCursor()
8. Create new MainWindow, connect config_switch_requested → _do_live_switch
9. Restore window geometry from new DB directory's .window_geometry file
10. new_win.show() / raise_() / activateWindow()
11. Update nonlocals: win, work_service, logbook_service, draw_service
12. QTimer.singleShot(500, _maybe_show_shared_db_notice)
```

Step 1 is critical: stamping `last_used_at` **on the config being left** (not the one being
entered) means the timestamp records when the user's last session on that config ended.
Any shared DB modification that occurs after that timestamp was made by another config.

### `_maybe_show_shared_db_notice(target_win, active_cfg)` closure

Called 500 ms after the new window is shown (800 ms on initial startup).

```
1. Load prefs — if show_shared_db_notice is False, return immediately
2. For each of setup_db_path / tools_db_path / jaws_db_path:
     call configs_sharing_path(path, exclude_id=active_cfg.id)
     build shared: dict[label → [other_config_names]]
3. If no shared DBs at all, return
4. If last_used_at is empty:
     → first-use notice listing which DBs are shared and with whom
5. Else parse last_used_at as datetime, compare against file mtime of each shared DB:
     if mtime_dt > last_dt → add to changed dict
   If changed is empty, return
   → change notice listing which DBs were modified since last use
6. Show a QDialog with the notice text + "Don't show these notices" checkbox
7. If checkbox checked on OK: _prefs_svc.save({..., show_shared_db_notice: False})
```

---

## File: `Setup Manager/ui/main_window.py`

### Changes

```python
from PySide6.QtCore import Signal  # added to existing import

class MainWindow(QMainWindow):
    config_switch_requested = Signal(str)   # emits target config_id

    def __init__(
        self,
        work_service,
        logbook_service,
        draw_service,
        print_service,
        machine_config_svc=None,            # new optional parameter
    ):
        ...
        self.machine_config_svc = machine_config_svc
        self._suppress_quit = False          # set True before close() during live switch

    def closeEvent(self, event):
        if not self._suppress_quit:
            # save window geometry to .window_geometry file
        super().closeEvent(event)
        if not self._suppress_quit:
            app = QApplication.instance()
            if app is not None:
                app.quit()
```

`_suppress_quit = True` prevents the `closeEvent` from calling `app.quit()` when
`_do_live_switch` closes the window programmatically. The `QLocalServer` is attached
to `QApplication`, not `MainWindow`, so it survives the window close.

---

## File: `Setup Manager/ui/machine_config_dialog.py`

New file. Handles both **Edit** (existing config) and **New** (create) modes.

### `_DbRow(QFrame)` helper widget

A composite widget for a single database path field. Toggles between two modes:

**Custom mode** (default):
```
[Label]  [QLineEdit: path]  [BROWSE]  [Clear]
```

**Shared mode** (when "Use shared database" checkbox is checked):
```
[Label]  Shared with: [QComboBox listing other configs]
```

Key methods:

```python
def set_value(self, path: str) -> None:
    # Detects if path matches another config's same db_attr.
    # If match found: checks the shared checkbox, selects that config in combo.
    # Otherwise: sets the path in the QLineEdit.

def get_value(self) -> str:
    # If shared mode: returns getattr(selected_config, self._db_attr)
    #   (the path stored in the other config — may itself be "" for app default)
    # If custom mode: returns self._path_edit.text().strip()

def is_shared(self) -> bool: ...
def shared_with_name(self) -> str: ...  # display name for warning labels
```

The combo in shared mode is populated by iterating `machine_config_svc.list_configs()`
and skipping `own_config_id`.

### `MachineConfigDialog`

Uses three `_DbRow` instances for `setup_db_path`, `tools_db_path`, `jaws_db_path`.

**Edit mode** (`config_id` is not None):
- Loads existing config via `machine_config_svc.get_config(config_id)`
- Warning label shown at top: "Editing this configuration will change all databases for this machine."
- On save: calls `machine_config_svc.update_config(config_id, **changes)`
- `requires_reload()` returns True if `machine_profile_key` or any DB path changed

**New mode** (`config_id` is None):
- All fields start empty/default
- On save:
  1. Calls `machine_config_svc.create_config(...)`
  2. If the setup DB path resolves to a new file (does not exist), calls
     `_bootstrap_new_database(path)` which initialises the SQLite schema
- `result_config()` returns the newly created `MachineConfig`

---

## File: `Setup Manager/ui/preferences_dialog.py`

### Tab structure

| Tab | Contents |
|---|---|
| General | Language, Color Theme, Enable assembly transform, Enable drawings tab, Detached preview mode |
| **Machines** | Active Machine dropdown + Edit/New/Delete; Notifications card with `show_shared_db_notice` checkbox |
| 3D Models | Tools 3D root folder, Jaws 3D root folder |
| Database | Setup DB path picker, Active runtime DB (read-only), Check Compatibility button |

The machine config section was previously crammed into General (causing the "Active Machine
not visible" bug when the dialog was only 520×340). Moving it to its own tab at 560×400
gives all widgets room.

### Live-switch pattern

The dialog does **not** emit the switch signal directly. Instead it stores a pending ID
and closes via `reject()`:

```python
self._pending_switch_config_id: str | None = None

def _on_config_combo_changed(self, _index):
    ...
    self._pending_switch_config_id = selected_id
    self.reject()   # caller reads _pending_switch_config_id after exec() returns
```

The caller (`preferences_actions.py`) reads this attribute and emits the signal on
`MainWindow` — which is connected to `_do_live_switch` in `main.py`.

This pattern avoids the dialog needing a reference to `MainWindow` and keeps the
signal emission at the right layer.

### Signal connection guard

`_machine_config_combo.currentIndexChanged` is connected **after** `_refresh_config_combo()`
runs during `_load_current_values()`, so the initial population does not trigger a live switch.

---

## File: `Setup Manager/ui/main_window_support/preferences_actions.py`

```python
def open_preferences_action(window) -> None:
    dialog = PreferencesDialog(
        ...,
        machine_config_svc=getattr(window, "machine_config_svc", None),
    )
    result = dialog.exec()

    # Check for pending live switch BEFORE processing normal save.
    pending_id = getattr(dialog, "_pending_switch_config_id", None)
    if pending_id:
        window.config_switch_requested.emit(pending_id)
        return   # do NOT apply normal preferences save — the window is being destroyed

    if result != PreferencesDialog.Accepted:
        return

    # Normal save flow: apply language, theme, model paths, etc.
    payload = dialog.preferences_payload()
    ...
```

The early return on `pending_id` is critical — if a switch is in progress, the old
`window` is about to be deleted, so writing preferences back through it would be a
use-after-free.

---

## File: `shared/services/ui_preferences_service.py`

Added `show_shared_db_notice: bool = False` to `_base_defaults()` and to the
normalisation pass in `_normalize_preferences()`:

```python
data["show_shared_db_notice"] = bool(data.get("show_shared_db_notice", False))
```

Default is `False` (off). Users opt in via Preferences → Machines → checkbox.
The `_maybe_show_shared_db_notice` dialog also provides a "Don't show these notices"
checkbox that writes `False` back directly via `_prefs_svc.save(...)`.

---

## JSON Storage Format

`.runtime/machine_configurations.json`:

```json
{
  "active_config_id": "config_ntx2500_a3b4c5",
  "configurations": [
    {
      "id": "config_ntx2500_a3b4c5",
      "name": "NTX2500",
      "machine_profile_key": "ntx_2sp_2h",
      "setup_db_path": "C:/.../.runtime/configs/config_ntx2500_a3b4c5/setup_manager.db",
      "tools_db_path": "",
      "jaws_db_path": "",
      "last_used_at": "2026-04-15T07:00:00+00:00"
    },
    {
      "id": "config_lathe_line_b_d1e2f3",
      "name": "Lathe Line B",
      "machine_profile_key": "lathe_2sp_3h",
      "setup_db_path": "C:/.../.runtime/configs/config_lathe_line_b_d1e2f3/setup_manager.db",
      "tools_db_path": "C:/.../.runtime/configs/config_ntx2500_a3b4c5/tools.db",
      "jaws_db_path": "",
      "last_used_at": "2026-04-14T15:30:00+00:00"
    }
  ]
}
```

In the example above, `Lathe Line B` shares the Tools DB from `NTX2500`. If both
configs had `tools_db_path` pointing to the same file, `configs_sharing_path` would
return the other config when queried from either side.

---

## Live Switching — Control Flow

```
User selects config in dropdown
         │
         ▼
PreferencesDialog._on_config_combo_changed()
  → confirm QMessageBox
  → _pending_switch_config_id = selected_id
  → self.reject()
         │
         ▼
preferences_actions.open_preferences_action()
  reads _pending_switch_config_id
  → window.config_switch_requested.emit(new_id)
         │
         ▼
main.py: _do_live_switch(new_id)
  → update_last_used(old_id)              ← stamps the config being LEFT
  → set_active_config_id(new_id)
  → win._suppress_quit = True
  → win.close() / win.deleteLater()
  → recreate Database, WorkService, LogbookService, DrawService
  → set_machine_profile_key(new profile)
  → create new MainWindow
  → connect config_switch_requested → _do_live_switch (recursive, same closure)
  → new_win.show()
  → update nonlocals: win, work_service, ...
  → QTimer(500ms) → _maybe_show_shared_db_notice
```

---

## Shared Database Logic

Two configs "share" a database when their `setup_db_path` (or `tools_db_path` or
`jaws_db_path`) point to the **same absolute path string**.

Detection happens in `MachineConfigService.configs_sharing_path(path, exclude_id)`:

```python
def configs_sharing_path(self, path: str, exclude_id: str = "") -> list[MachineConfig]:
    if not path:
        return []
    return [
        c for c in self._configs
        if c.id != exclude_id
        and path in (c.setup_db_path, c.tools_db_path, c.jaws_db_path)
    ]
```

Note: this checks **any** DB field, not just the same field. If config A's
`tools_db_path` happens to equal config B's `setup_db_path`, it would be flagged.
This is a deliberate conservative check — an unusual cross-field share is still a share.

In `_DbRow.set_value()`, the same-field check is used (not cross-field) when
auto-detecting sharing for the UI toggle:

```python
# Only check the same db_attr field on other configs for auto-detection
for cfg in other_configs:
    if getattr(cfg, self._db_attr, "") == path:
        self._shared_cb.setChecked(True)
        self._shared_combo.setCurrentIndex(...)
        return
```

---

## Shared DB Notice System

The notice fires under two conditions (only if `show_shared_db_notice` pref is `True`):

### Condition 1 — First use
`active_cfg.last_used_at` is empty. This means the config has never been switched
away from (it was either just created or migrated from legacy state). If it already
has shared DB paths configured, the user is informed.

### Condition 2 — Modified since last use
`active_cfg.last_used_at` is set AND at least one shared DB file has `st_mtime`
greater than the parsed `last_used_at` datetime. The notice names the databases
that changed and which configs share them (as possible sources of the change).

This is a best-effort system. It can produce false positives (file touched by
backup tools, OS indexing, etc.) and false negatives (change within the same second
as the timestamp). It does not track which specific rows changed.

---

## First-Run Migration

On the very first run there is no `machine_configurations.json`. The flow is:

```
machine_config_svc.is_empty() → True
  → use legacy DB_PATH as active_setup_db_path
  → open DB, load/set profile key
  → machine_config_svc.migrate_from_legacy(
        name="NTX2500",
        machine_profile_key=db_profile_key,
        setup_db_path=active_setup_db_path,
        tools_db_path="",   ← "" means app default
        jaws_db_path="",
    )
```

`migrate_from_legacy` calls `create_config` internally and sets `_active_id` to
the new config's id. After this point `is_empty()` is `False` for all future runs.

---

## Further Implementation Paths

### 1. Config import/export

Allow exporting a config (and optionally its databases) to a ZIP archive and
importing it on another machine. The `MachineConfig` dataclass serialises cleanly
via `dataclasses.asdict`, so the JSON side is trivial. The DB copy would use
`sqlite3.connect().backup()` for a hot copy.

```python
def export_config(self, config_id: str, dest_dir: Path) -> Path: ...
def import_config(self, archive_path: Path) -> MachineConfig: ...
```

### 2. Config duplication ("Clone")

A "Duplicate" button in `MachineConfigDialog` or the Machines tab. Should
deep-copy the setup DB file (not just re-use the path) and create a new config
pointing to the copy, unless the user explicitly opts for a shared DB.

### 3. Per-config colour accent

Each config could carry an optional `accent_color: str` (hex). The `MainWindow`
title bar or a status badge could reflect the active config's accent — useful when
operators work across multiple configs and need a visual cue that they're on the
right machine.

### 4. Config-scoped preferences

Currently `show_shared_db_notice` is a global preference. A richer model would
allow per-config overrides: e.g. one config suppresses notices, another keeps them.
This would require moving some pref keys into `MachineConfig` or a parallel
`machine_config_preferences.json`.

### 5. Shared DB conflict detection at save time

When a user edits a record that exists in a shared DB, and another config has
modified the same row since `last_used_at`, show a merge/overwrite dialog instead
of silently overwriting. Requires a row-level change log (e.g. a `changes` table
with `(table_name, row_id, changed_at, changed_by_config_id)`) written by
`WorkService`/`DrawService` on every mutation.

### 6. Remote/network database support

`tools_db_path` and `jaws_db_path` currently require local paths. Extending to
`sqlite+tcp://` or a REST-backed adapter would allow a shared central Tools Library
server. This would require abstracting `Database` behind a protocol interface.

### 7. Config auto-switching via IPC

The IPC server already accepts JSON commands (`{"command": "show"}`). A new command
`{"command": "switch", "config_id": "config_ntx2500_a3b4c5"}` would allow an external
script or a PLC integration to trigger a live switch programmatically.

```python
if request["command"] == "switch":
    config_id = str(request.get("config_id", "")).strip()
    if config_id:
        _do_live_switch(config_id)
```

### 8. Config list persistence across sessions (recently used)

`last_used_at` already tracks usage. A "Recent" section at the top of the Active
Machine dropdown (sorted by `last_used_at` descending, top 3) would speed up
switching for operators who rotate between a small set of configs.

---

## Known Limitations and Improvement Areas

### Atomicity of `_save()`

`MachineConfigService._save()` does a single `Path.write_text()`. If the process
is killed mid-write, the JSON file is corrupted and all configs are lost on next
startup. Fix: write to a `.tmp` sibling and `os.replace()` into place.

```python
tmp = self._path.with_suffix(".tmp")
tmp.write_text(json.dumps(payload, ...), encoding="utf-8")
os.replace(tmp, self._path)
```

### Path comparison is string-based

`configs_sharing_path` compares raw strings. On Windows, `C:\foo\bar.db` and
`c:/foo/bar.db` would not match. All paths should be normalised through
`Path(...).resolve()` before storage and before comparison.

### `_suppress_quit` is not re-entrant

If `config_switch_requested` fires twice in rapid succession (e.g. user double-clicks
in the dropdown), `_do_live_switch` could run on a `win` that has already been
`deleteLater()`-ed. A guard flag on `main.py` scope would prevent the second call
from executing while a switch is already in progress.

```python
_switch_in_progress = False

def _do_live_switch(new_config_id):
    nonlocal _switch_in_progress
    if _switch_in_progress:
        return
    _switch_in_progress = True
    try:
        ...
    finally:
        _switch_in_progress = False
```

### `last_used_at` accuracy

The timestamp is stamped by `datetime.now(timezone.utc)` at the moment the switch
begins in Python, not at the OS process level. If the clock changes (NTP step,
DST, timezone change) the comparison against file `st_mtime` can produce incorrect
results. Using monotonic filesystem mtimes consistently would help, but
`datetime.fromtimestamp(mtime, tz=timezone.utc)` already converts correctly as long
as the local clock is accurate.

### Shared DB combo in `_DbRow` shows config names, not paths

When two configs share a Tools DB, the combo shows the other config's name. If
that config is later renamed, the `_DbRow` still shows the new name correctly on
next open (it re-queries `list_configs()` at dialog init time), but the shared path
in the JSON does not update — it is the path that is the link, not the name. This
is correct and intentional but could confuse users who expect renaming to "break" sharing.

### No undo for delete

`delete_config` removes the config from the JSON immediately. There is no soft-delete
or trash. The database files are not deleted (they remain on disk), so data recovery
is possible manually, but there is no UI for it. A soft-delete with a "Recently deleted"
section in the Machines tab would reduce accidental loss.

### `MachineConfigDialog` bootstraps a new DB synchronously on the UI thread

When creating a new config with a fresh database, `_bootstrap_new_database(path)`
runs SQLite schema migrations on the UI thread. For large schemas this causes a
visible freeze. Moving it to `QRunnable` / `QThreadPool` with a progress indicator
would fix this.

### `show_shared_db_notice` is off by default — discoverability

Users who would benefit from the notice may never enable it because the default is
off. Consider showing it once on the first config switch after a shared DB is
configured, with a "Got it — don't show again" option, regardless of the pref value.
This one-time first-use path is already half-implemented via the `last_used_at` empty
check; it just needs to fire unconditionally on the very first shared-DB switch.

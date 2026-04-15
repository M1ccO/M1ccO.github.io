# Machine Profile Architecture

## Overview

The machine profile system describes the physical configuration of the CNC machine being managed — how many spindles, how many heads, what each head can do, and what terminology the UI should use. Every behavioural variation in Setup Manager and the Tools/Jaws Library that depends on machine hardware is driven by the active `MachineProfile` object.

---

## Where the Profile Lives

### Authoritative source — `app_config` table in `setup_manager.db`

| Table | Key | Value |
|---|---|---|
| `app_config` | `machine_profile_key` | e.g. `ntx_2sp_2h` |

The profile key is **database-bound**, not a casual user preference. One database = one machine configuration. The value is written once during the setup wizard and only changed deliberately via "Configure Machine..." in Preferences.

### Mirror — `shared_ui_preferences.json`

On every startup, `main.py` mirrors the DB-bound key to the shared JSON preferences file that both apps read:

```
.runtime/shared_ui_preferences.json → "machine_profile_key": "ntx_2sp_2h"
```

This mirror is **one-way and read-only for the Tools Library**. It lets the Tools Library reflect the active profile (e.g. which heads exist, b-axis visibility) without any direct cross-app import.

---

## Profile Bootstrap Flow

```
Startup
  └─ Database.open() + create_or_migrate_schema()
       ├─ app_config table created (if new)
       ├─ machine_profile_key backfilled to 'ntx_2sp_2h' if existing works present
       └─ machine_profile_key set to '' if fresh empty database
  └─ work_service.get_machine_profile_key()
       ├─ '' → show MachineSetupWizard
       │    └─ wizard.exec() → profile_key chosen
       │    └─ work_service.set_machine_profile_key(key)
       └─ non-empty → use as-is
  └─ ui_preferences_service.set_machine_profile_key(key)   ← mirror to shared prefs
  └─ MainWindow opens (reads profile from shared prefs via UiPreferencesService)
```

**Existing databases** receive `ntx_2sp_2h` automatically during migration — no disruption.  
**Fresh databases** show the wizard before the main window opens.

---

## Changing the Profile (Post-Setup)

Via **Preferences → General → Configure Machine...**:
1. `MachineSetupWizard` opens as a standalone dialog.
2. On Accepted: `work_service.set_machine_profile_key(key)` + `ui_preferences_service.set_machine_profile_key(key)`.
3. A restart-required notice is shown.
4. On next launch the bootstrap mirrors the new key to shared prefs and all UIs use it.

The machine profile combo in Preferences is now **read-only display** — it shows the currently bound profile name but cannot be directly edited.

---

## The Five Profiles

| Key | Name | Spindles | Heads | Head types | OP terminology |
|---|---|---|---|---|---|
| `ntx_2sp_2h` | NTX 2 Spindles / 2 Turret Heads | 2 | 2 | turret, turret | No (Main/Sub) |
| `lathe_2sp_1mill` | Lathe 2 Spindles / 1 Milling Head | 2 | 1 | milling | No (Main/Sub) |
| `lathe_2sp_3h` | Lathe 2 Spindles / 3 Turret Heads | 2 | 3 | turret×3 | No (Main/Sub) |
| `lathe_1sp_1h` | Lathe 1 Spindle / 1 Turret Head | 1 | 1 | turret | Yes (OP10/OP20) |
| `lathe_1sp_1mill` | Lathe 1 Spindle / 1 Milling Head | 1 | 1 | milling | Yes (OP10/OP20) |

All profiles are fixed presets in `Setup Manager/machine_profiles.py` in `PROFILE_REGISTRY`.  
New variants can be added by defining another `MachineProfile` and registering it — no schema changes required for most additions.

---

## Profile Data Model (`machine_profiles.py`)

```python
@dataclass(frozen=True)
class MachineHeadProfile:
    key: str                         # "HEAD1" | "HEAD2" | "HEAD3"
    label_key: str                   # i18n key for UI label
    label_default: str               # fallback display text
    default_coord: str               # default G-code coordinate (G54…)
    head_type: str                   # "turret" | "milling"
    allows_rotating_tools: bool      # drills/endmills allowed (turret only)
    allows_b_axis: bool              # b_axis_angle field is meaningful
    allows_dual_spindle_orientation: bool  # tool orientation matters for both spindles

@dataclass(frozen=True)
class MachineSpindleProfile:
    key: str                         # "main" | "sub"  (storage contract, never changes)
    label_default: str               # "Main spindle" | "OP10" etc.
    jaw_title_default: str           # title shown above jaw selector panel
    jaw_filter: str | None           # DB filter value for spindle_side column

@dataclass(frozen=True)
class MachineProfile:
    key: str
    spindles: tuple[MachineSpindleProfile, ...]
    heads: tuple[MachineHeadProfile, ...]
    machine_type: str                # "lathe" | "machining_center"
    use_op_terminology: bool         # True → OP10/OP20 labels for single-spindle
    supports_sub_pickup: bool
    supports_print_pots: bool
    supports_zero_xy_toggle: bool
    ...
```

---

## Screens That Are Now Profile-Driven

| Screen / Area | What changes with profile |
|---|---|
| **Work Editor — Spindles tab** | Sub jaw selector hidden for 1-spindle profiles; jaw selector titles use profile spindle labels (OP10/OP20 vs Pääkara/Vastakara) |
| **Work Editor — Zeros tab** | Spindle zero groups: only "main" group for 1-spindle; spindle labels from profile |
| **Work Editor — Tools tab** | Head switch button hidden if only 1 head; sub-program inputs created per active head |
| **Work Editor — general** | Sub pickup section hidden if `supports_sub_pickup=False` |
| **Tool Library — head filter** | Only heads present in profile are valid filter targets (HEAD3 visible only for 3-head profiles) |
| **Tool Library — Tool Editor** | `b_axis_angle` field shown/hidden per `head.allows_b_axis`; spindle orientation button hidden for single-spindle |
| **Jaws Library — jaw selector** | Spindle-side labels/filters use profile-derived terms |
| **Preferences dialog** | Machine profile is read-only display; "Configure Machine..." opens wizard |

---

## How Old Databases Are Handled

1. Migration runs `_ensure_app_config_table(conn)`.
2. It checks whether `machine_profile_key` already exists in `app_config`.
3. If not, it counts works rows:
   - `> 0` → existing DB → backfills `ntx_2sp_2h` (full backward compat, no wizard shown).
   - `= 0` → fresh DB → inserts `''` → wizard shown at startup.
4. HEAD3 columns (`head3_zero`, `head3_tool_ids`, etc.) are added to `works` table additively — existing rows default to empty/`[]`.

**No existing work record is modified. No data is lost. The schema is strictly additive.**

---

## What Remains — Future Work

### Machining Center (`machine_type = "machining_center"`)

- The `MachineProfile.machine_type` field already exists and the wizard has a disabled radio button for it.
- When implemented, Machining Center will need:
  - Its own **Fixtures Library** (separate DB domain, separate app page).
  - Different coordinate/program model (no spindles in the traditional sense).
  - Different Work Editor layout.
- The profile model is ready to extend; do not backfill machining center logic into lathe paths.

### Per-Head Rotating Tool Enforcement (Tools Library)

- `MachineHeadProfile.allows_rotating_tools` and `head_allows_rotating_tools(head_key)` are defined.
- The Tool Editor and import validation do not yet enforce them.
- Next step: in `ToolEditorDialog`, when `tool_head` is a turret head with `allows_rotating_tools=False`, filter or warn on milling tool types.

### B-Axis Field Visibility in Tool Editor (Tools Library)

- `MachineHeadProfile.allows_b_axis` is defined.
- `b_axis_field` in the Tool Editor is already conditionally created but currently shown/hidden by tool-type rules only.
- Next step: additionally gate on `profile.head_allows_b_axis(selected_head)` — hide the field entirely when the active head does not support B-axis regardless of tool type.

### OP20 Checkbox in Work Editor (1-Spindle)

- For `use_op_terminology=True` profiles, the second operation context (OP20) is conceptually represented by a second jaw setup on the same spindle (rather than a true sub-spindle).
- A future Work Editor change should add an "Enable OP20" checkbox when the profile is single-spindle, replacing the always-present sub jaw section with an opt-in.

### HEAD3 in Work Editor Tools Tab

- The `head3_*` columns exist in the schema.
- The Work Editor already iterates `dialog.machine_profile.heads` to create sub-program rows.
- HEAD3 tool assignment lists and selector support still need to be wired into the tools-tab builder and payload adapter for the `lathe_2sp_3h` profile.

### Tool Library Profile Context via IPC

- The IPC selector payload already carries `head` and `spindle` fields.
- Extend the payload to include the active `machine_profile_key` so the Tools Library can apply head-capability rules during a selector session without reading shared prefs.

---

## Storage Contract (Never Changes)

Even as profiles evolve, these storage values are frozen:

| Domain | Storage value | Meaning |
|---|---|---|
| `tools.tool_head` | `"HEAD1"`, `"HEAD2"`, `"HEAD3"` | Physical head assignment |
| `tools.spindle_orientation` | `"main"`, `"sub"` | Spindle targeting |
| `jaws.spindle_side` | `"Main spindle"`, `"Sub spindle"`, `"Both"` | Jaw spindle assignment |
| `works.head1_*` / `head2_*` / `head3_*` | per-head coordinate fields | Head-specific work data |
| `works.main_jaw_id` / `sub_jaw_id` | jaw assignment | Storage uses main/sub keys |

Display labels can change with the profile; stored keys never change.

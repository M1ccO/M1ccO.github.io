# Machine Profile Architecture — Refactor & Hardening Plan

> **Implementation status** (updated 2026-04-15)
>
> | Phase | Status |
> |---|---|
> | 1 — Consolidate machine-type detection | ✅ Done |
> | 2 — `dataclasses.replace` | ✅ Done |
> | 3 — Stop swallowing exceptions | ✅ Done |
> | 4 — Single `resolve_profile_key` | ✅ Done |
> | 5 — Profile-key mirror on config switch | ✅ Already correct in `main.py`; no change needed |
> | 6 — Unify cross-app profile view | ⏳ Deferred — larger architectural change, tracked separately |
> | 7 — Document migration load-bearing status | ✅ Done |
> | 8 — Scrub stale "future" wording | ✅ Done (one comment in `machine_profiles.py:75-76`) |
> | 9 — MC payload schema | ⏳ Optional; deferred |

---

Target: tighten the newly implemented Machine Profile + Machine Configuration architecture
without changing observable behaviour or visuals.

**Ground rule for every step below:** no UI or functional change. Refactor-only. Visual
snapshots (Work Editor lathe view, Work Editor MC view, Setup page, Fixture page, Tool
Selector, Jaw Selector, Fixture Selector, Setup card PDF output) must be identical
before and after each phase. Run both apps in lathe **and** machining-center
configurations between phases.

---

## 0. Guiding Principles

1. **One source of truth per concern.** Profile key lives in Setup Manager DB.
   Everything else mirrors or resolves from it. No one invents their own fallback.
2. **No silent failures on state-changing paths.** Swallowed exceptions are allowed
   only for genuinely best-effort cleanup, and even then must be logged.
3. **Pure refactor commits.** Each commit either moves code, renames, or collapses
   duplication — never all three. Functional changes get their own commit.
4. **Persisted identifiers never change.** Everything in the *Storage Contract* table
   of [MACHINE_PROFILE_ARCHITECTURE.md](MACHINE_PROFILE_ARCHITECTURE.md) is frozen.

---

## Phase 1 — Consolidate Machine-Type Detection ✅

**STATUS: Done.** Added `is_machining_center_key(key)` to `machine_profiles.py` and a private `_is_machining_center_key` mirror to `machine_config_service.py` (no cross-app import). Replaced 8 open-coded `startswith("machining_center")` / `machine_type == "machining_center"` patterns in `model.py`, `tab_builders.py`, `tools_tab_builder.py`, `work_editor_dialog.py`, and `machine_config_service.py`.

The `startswith("machining_center")` / `machine_type == "machining_center"` check is
open-coded in at least seven places across both apps. This is the highest-leverage
cleanup and unlocks the rest of the plan.

**Scope**

Add one helper (and only one) to the shared profile module:

```python
# Setup Manager/machine_profiles.py
def is_machining_center_key(key: str | None) -> bool: ...
def is_machining_center(profile) -> bool: ...   # accepts MachineProfile OR dict
```

**Call sites to migrate**

| File | Current pattern |
|---|---|
| [shared/services/machine_config_service.py:221](shared/services/machine_config_service.py#L221) | `key.startswith("machining_center")` in `create_config` |
| [shared/services/machine_config_service.py:377](shared/services/machine_config_service.py#L377) | same in `migrate_empty_db_paths` |
| [Setup Manager/ui/work_editor_support/model.py:50](Setup%20Manager/ui/work_editor_support/model.py#L50) | `machine_type == "machining_center"` (populate) |
| [Setup Manager/ui/work_editor_support/model.py:125](Setup%20Manager/ui/work_editor_support/model.py#L125) | same (extract) |
| [Setup Manager/ui/work_editor_support/tab_builders.py:270](Setup%20Manager/ui/work_editor_support/tab_builders.py#L270) | Zeros tab routing |
| [Setup Manager/ui/work_editor_support/tools_tab_builder.py:207](Setup%20Manager/ui/work_editor_support/tools_tab_builder.py#L207) | Tool IDs tab routing |
| [Setup Manager/ui/work_editor_dialog.py:452](Setup%20Manager/ui/work_editor_dialog.py#L452) | dialog branching |
| [Tools and jaws Library/ui/main_window.py:231](Tools%20and%20jaws%20Library/ui/main_window.py#L231) | defensive dict-based check |

**Verify:** lathe config → Work Editor still opens lathe layout, Tool Selector shows
head/spindle toggle, Jaws module routing intact. MC config → operation cards render,
Fixtures module routing intact, head/spindle toggle hidden.

---

## Phase 2 — Collapse Dataclass Rewrite Duplication ✅

**STATUS: Done.** Added `replace` to `machine_config_service.py` imports. Collapsed manual `MachineConfig(...)` rewrite in `update_last_used`, `update_config`, `migrate_empty_db_paths`, and `migrate_to_config_folders` — each now a `replace(c, ...)` one-liner or short call.

`MachineConfig` is rebuilt by hand in four places. Use `dataclasses.replace` (already
imported elsewhere in the codebase).

**Locations**

- [shared/services/machine_config_service.py:186-199](shared/services/machine_config_service.py#L186-L199) — `update_last_used`
- [shared/services/machine_config_service.py:253-274](shared/services/machine_config_service.py#L253-L274) — `update_config`
- [shared/services/machine_config_service.py:408-423](shared/services/machine_config_service.py#L408-L423) — `migrate_empty_db_paths`
- [shared/services/machine_config_service.py:492-508](shared/services/machine_config_service.py#L492-L508) — `migrate_to_config_folders`

**Change**

```python
from dataclasses import replace
self._configs[i] = replace(c, last_used_at=ts)
```

Each site shrinks to a one-liner. Field coverage is enforced by the dataclass itself,
so no more risk of forgetting to copy a new field (e.g. `fixtures_db_path` — already
had to be plumbed through four separate constructors).

**Verify:** config rename, active switch, and first-run bootstrap all still persist
correctly; `machine_configurations.json` byte-identical vs. baseline (ignoring
`last_used_at`).

---

## Phase 3 — Stop Swallowing Exceptions Silently ✅

**STATUS: Done.** Added `_log = logging.getLogger(__name__)` to `machine_config_service.py`. Replaced bare `except Exception: pass` in `_load()` (parse error now logged at warning), `delete_config` unlink/rmdir (warning + debug), SQLite pre-create in `migrate_empty_db_paths` (warning), and file copy in `migrate_to_config_folders` (warning).

Every `except Exception: pass` in [shared/services/machine_config_service.py](shared/services/machine_config_service.py)
is either a corruption risk or a debugging nightmare. Audit them:

| Line | Current | Action |
|---|---|---|
| 92 | `_load()` swallows JSON decode errors | Log at warning; rename file to `.corrupt-<ts>` on fatal parse so next run recovers |
| 341 | `delete_config` unlink failure | Already captured in `failed_paths`, add logger.warning |
| 348 | `rmdir` failure | log at debug — genuinely best-effort |
| 441 | SQLite pre-create failure | Log at warning — affects Tool Library startup |
| 469, 479 | Copy failures in `migrate_to_config_folders` | Log at warning — user loses data silently otherwise |

Logger is already available (`shared` uses `logging.getLogger(__name__)` elsewhere).
Add a module-level logger to `machine_config_service.py`.

**Verify:** no behavioural change on happy path. Force-create a corrupt JSON file,
confirm app recovers instead of starting with empty config list silently.

---

## Phase 4 — Single Profile-Key Resolution Entry Point ✅

**STATUS: Done.** Added `resolve_profile_key(raw)` to `machine_profiles.py`. It normalises, validates against `PROFILE_REGISTRY`, and returns `DEFAULT_PROFILE_KEY` on unknown input. `load_profile` now delegates entirely to it — one line instead of three, one fallback rule instead of two.

Today three places normalize an unknown profile key:

1. [Setup Manager/machine_profiles.py:566-571](Setup%20Manager/machine_profiles.py#L566-L571) — `load_profile()` defaults to `ntx_2sp_2h`
2. [shared/services/ui_preferences_service.py:72-77](shared/services/ui_preferences_service.py#L72-L77) — persists whatever it gets, no validation
3. [Setup Manager/ui/machine_setup_wizard.py:103-116](Setup%20Manager/ui/machine_setup_wizard.py#L103-L116) — its own fallback logic

**Change**

Move canonical resolution into `machine_profiles.py`:

```python
def resolve_profile_key(raw: str | None) -> str:
    """Return a registered key, falling back to ntx_2sp_2h."""
```

UiPreferencesService normalizes on read (not on write, to keep its agnostic contract).
Wizard uses the same helper instead of its closure. `load_profile` delegates to it.

**Verify:** an invalid key in shared prefs or DB produces the same default as today,
but from one code path only.

---

## Phase 5 — Guarantee Profile-Key Mirror on Config Switch ✅

**STATUS: Already implemented correctly.** `main.py _do_live_switch` already calls `new_work_service.set_machine_profile_key(active.machine_profile_key)` then `_prefs_svc.set_machine_profile_key(active.machine_profile_key)` in the correct order before creating the new window. The defensive key-carry-forward in `preferences_actions.py` is correct for the normal-Save path (prevents UiPreferencesService default from overwriting DB-bound key). No change needed.

The current mirror is implicit: [preferences_actions.py:38-41](Setup%20Manager/ui/main_window_support/preferences_actions.py#L38-L41)
has to explicitly re-read the profile key from DB before saving UI prefs, to stop
UiPreferencesService from overwriting it. That is a symptom.

**Change**

1. When `config_switch_requested` fires, the switch handler must, in order:
   1. Rebind WorkService to the new setup DB.
   2. Read canonical `machine_profile_key` from the new DB.
   3. Call `ui_prefs.set_machine_profile_key(...)` with that value.
   4. Only then emit whatever the UI listens to for re-render.
2. Remove the defensive read-before-save dance in preferences_actions.py — it is no
   longer needed once step 1.3 is authoritative.

**Verify:** switch lathe → MC → lathe; confirm Tools and Jaws Library reflects each
switch without needing a separate manual pref edit, and shared_ui_preferences.json
always matches the active DB's key.

---

## Phase 6 — Unify the Cross-App Profile View ⏳ Deferred

**STATUS: Deferred.** The Tools Library's `_resolve_machine_profile` method is well-contained and its dict-based profile contract is stable. Promoting `machine_profiles.py` to `shared/` or wrapping it in a typed proxy view requires a larger cross-app restructure and is not a safety fix — it is a quality-of-life improvement. Tracked for a future session.

The architecture doc accepts a lightweight resolved mapping for the Tools and Jaws
Library. That is fine — but today the mapping is assembled defensively with
`(self.machine_profile or {}).get(...)` calls. Drift risk is real because Setup
Manager adds flags faster than Tools Library picks them up.

**Change**

Promote `machine_profiles.py` to `shared/` (or add a thin shared read-only view) so
Tools Library can call `load_profile(key)` directly and receive a real `MachineProfile`
object. Keep the "lightweight" promise by exposing only the flags Tools Library
actually needs through a typed `TolLibProfileView` proxy.

Locations that will simplify:

- [Tools and jaws Library/ui/main_window.py:231](Tools%20and%20jaws%20Library/ui/main_window.py#L231)
- Tool Selector state resolving head/spindle toggle visibility
- Fixture Selector's (currently absent) MC-only assertion — add one

**Verify:** Tool Selector, Jaw Selector, Fixture Selector all match current visuals
byte-for-byte across lathe and MC configs.

---

## Phase 7 — Document Migration Load-Bearing Status ✅

**STATUS: Done.** Added extended docstrings to all three migration methods in `machine_config_service.py`: `migrate_empty_db_paths`, `migrate_to_config_folders`, `migrate_from_legacy`. Each now states whether it is load-bearing or one-shot, which release introduced it, and under what condition it becomes safe to delete.

The three migration methods in `MachineConfigService` look like dead code to a
new reader, but at least two are called at startup from `main.py`:

- `migrate_empty_db_paths` — main.py:276 — still needed for users with per-config
  library isolation added after their first run.
- `migrate_to_config_folders` — main.py:284 — still needed to relocate pre-folder
  DBs into per-config folders.
- `migrate_from_legacy` — main.py:405 — one-shot on first run from pre-multi-config
  state.

**Change**

1. Extract all three into `shared/services/machine_config_migrations.py`.
2. Add module docstring listing the release each migration handles and the condition
   that makes it a no-op (so we know when it is safe to delete).
3. Add a short note in [MACHINE_PROFILE_ARCHITECTURE.md](MACHINE_PROFILE_ARCHITECTURE.md)
   referencing the new module.

No behavioural change. Pure move + docs.

---

## Phase 8 — Scrub Stale "Future" Wording ✅

**STATUS: Done.** Fixed one stale comment in `machine_profiles.py:75-76` that said `"machining_center" is reserved for future work (Fixtures library, etc.)`. Updated to reflect that both families are fully implemented. No other stale future-wording found in production source files (TODOs in vendor `three.module.js` and separate plan `.md` files were left alone).

Architecture doc gap #3 notes remaining "future tense" comments about
machining-center flows that are in fact now active. Grep for the offenders and
correct or remove them.

Start points:
- docstrings in [Setup Manager/ui/work_editor_support/machining_center.py](Setup%20Manager/ui/work_editor_support/machining_center.py)
- docstrings in [Tools and jaws Library/ui/selectors/tool_selector_state.py](Tools%20and%20jaws%20Library/ui/selectors/tool_selector_state.py)
- any `TODO` / `FUTURE` / `when MC is implemented` strings across both apps

Pure comment change, no code impact.

---

## Phase 9 — MC Payload Contract (Low Priority, Nice-to-Have)

`mc_operation_count` and `mc_operations` (JSON) are written by WorkService, read by
MC editor support. Fine today, but:

- Add a small typed schema (TypedDict or dataclass) in `Setup Manager/services/` for
  the operation entry.
- Make `_serialize_json_object_list` / its reader validate against it on load and
  log-and-default on mismatch.

Only do this phase if a regression actually appears. It is insurance, not required.

---

## Phase 10 — Verification Matrix

Before declaring the refactor done, run this matrix:

| Config | App | Check |
|---|---|---|
| lathe (2sp/2h) | Setup Manager | Work Editor lathe layout, Setup card PDF unchanged |
| lathe (1sp/1h, OP terminology) | Setup Manager | OP labels render correctly |
| lathe (any) | Tools and Jaws Library | Tool Selector shows head/spindle toggle, Jaws module routes to Jaws |
| MC 3ax | Setup Manager | Operation cards, per-OP tool IDs, fixtures selection work |
| MC 3ax | Tools and Jaws Library | Fixtures module routes, head/spindle toggle hidden |
| Switch lathe→MC live | both | Both apps re-render without restart where expected; restart notice where documented |
| First run, empty DB | Setup Manager | Wizard appears, key is written to DB and mirrored to shared prefs |
| Legacy DB (pre-multi-config) | Setup Manager | `migrate_from_legacy` bootstraps a single config, active id set |

---

## Out of Scope

- Adding new machine profiles or families.
- Changing the `.runtime/` directory layout.
- Any UI redesign. If a visual delta appears, revert and re-examine the phase.
- Performance work — this plan is about correctness and maintainability only.

---

## Suggested Commit Order

1. Phase 1 (helper + call-site migration) — one commit per app.
2. Phase 2 (`dataclasses.replace`) — single commit.
3. Phase 3 (logging) — single commit.
4. Phase 4 (resolve_profile_key) — single commit.
5. Phase 5 (switch handler ordering) — single commit; verify cross-app prefs.
6. Phase 7 (extract migrations) — single commit, pure move.
7. Phase 8 (stale comments) — single commit.
8. Phase 6 (cross-app profile view) — only after 1–5 have baked; touches both apps.
9. Phase 9 (MC payload schema) — optional.

Each commit must leave both apps in a runnable state and pass the Phase 10 matrix
for the scope it touched.

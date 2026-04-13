# Setup Manager

Operational app for CNC setup execution data.

## Current Status (April 2026)
- Cross-app shared runtime preferences are active via `shared_ui_preferences.json`.
- Setup Manager continues to treat Tool Library master data as read-only.
- Ongoing Tool Library support-layer modularization planning is documented in:
  - `Tools and jaws Library/PHASE11_SHARED_SUPPORT_GOALS.md`
  - `Tools and jaws Library/PHASE11_SHARED_SUPPORT_RULES.md`
  - `Tools and jaws Library/PHASE11_SHARED_SUPPORT_STATUS.md`

## Scope
- Owns: setup works + production logbook.
- Reads (read-only): tool/jaw master data from sibling `Tools and jaws Library`.
- Does not edit tool/jaw master records.

## Stack
- Python 3.10+
- PySide6
- SQLite (`sqlite3`)
- `openpyxl` (Excel export)
- `reportlab` (setup card PDF)

## Main Modules
- `main.py`: app bootstrap.
- `config.py`: path and runtime config.
- `ui/main_window.py`: shell, page routing, cross-app handoff.
- `ui/setup_page.py`: work list + setup actions.
- `ui/work_editor_dialog.py`: setup editor.
- `ui/work_editor_support/`: app-local support modules used to keep `work_editor_dialog.py` orchestration-focused.
- `ui/logbook_page.py`: run history + export.
- `services/work_service.py`: work CRUD.
- `services/logbook_service.py`: log CRUD + serial generation.
- `services/draw_service.py`: drawing lookup + read-only master refs.
- `services/print_service.py`: setup card PDF.

## Data Ownership
- Setup DB schema lives in `data/migrations.py`.
- Keep migrations additive-only.
- Keep cross-app model reference-based (store IDs, not duplicated master rows).

## Cross-App Behavior
- Setup Manager can launch/switch to Tool Library via local IPC.
- IPC uses single-instance server names from config.
- Setup app remains owner of setup/logbook; Tool Library remains owner of tool/jaw master data.

## Run
From repository root:

```powershell
.\run.bat
```

Or from `Setup Manager`:

```powershell
.\run.cmd
```

## Quick Verification
1. Start Setup Manager.
2. Open Tool Library and return.
3. Create/edit a work with tool/jaw IDs.
4. Add logbook entry and verify serial.
5. Export logbook and print setup card.

## Work Editor Refactor Status
- Current behavior-preserving refactor status and remaining safe extractions:
  - `WORK_EDITOR_REFACTOR_STATUS.md`
- Use this status file when continuing `ui/work_editor_dialog.py` responsibility-reduction work.

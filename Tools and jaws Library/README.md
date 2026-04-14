# Tools and jaws Library

Desktop master-data application for CNC tools and jaws. It owns the tool and jaw catalogs, editor dialogs, selector workflows, Excel import/export, and the shared 3D preview experience used by the library app.

## Current Status (April 2026)

- Platform overhaul phases 0-9 are complete.
- The TOOLS and JAWS catalog pages are both thin orchestrators built on `CatalogPageBase`.
- Phase 11 shared support modularization is complete.
- Current orchestrator sizes are approximately:
  - `ui/home_page.py`: 567 lines
  - `ui/jaw_page.py`: 565 lines
- Current support-folder inventories are:
  - `ui/home_page_support/`: 19 Python modules plus `__init__.py`
  - `ui/jaw_page_support/`: 18 Python modules plus `__init__.py`
- The measurement editor refactor is active:
  - `ui/measurement_editor_dialog.py`: 1381 lines
  - coordinator package exists under `ui/measurement_editor/coordinators/`
- Inline detail-panel 3D preview is currently disabled as a runtime fallback.
- Detached 3D preview remains the primary supported preview workflow.
- The repository quality gate passed on 2026-04-14.

## What The App Owns

Tools and jaws Library owns:

- tool master data
- jaw master data
- tool and jaw CRUD dialogs
- selector dialogs used by Setup Manager
- library-side Excel import/export
- 3D preview and measurement-overlay workflows on the library side

It does not own:

- setup/work records
- logbook/history records
- setup-side PDF workflows

Those stay in `Setup Manager/`.

## Runtime Architecture

Top-level structure:

- `main.py` boots the app, services, IPC server, and main window.
- `ui/main_window.py` is the shell, page host, and selector-session owner.
- `ui/home_page.py` is the TOOLS catalog orchestrator.
- `ui/jaw_page.py` is the JAWS catalog orchestrator.
- `ui/home_page_support/` and `ui/jaw_page_support/` contain the domain-specific support modules used by those orchestrators.
- `ui/tool_editor_dialog.py` and `ui/jaw_editor_dialog.py` own CRUD dialog orchestration.
- `ui/tool_editor_support/` and `ui/jaw_editor_support/` contain dialog support logic.
- `ui/selectors/` contains the standalone Tool and Jaw selector dialogs opened by Setup Manager sessions.
- `services/tool_service.py` and `services/jaw_service.py` own domain behavior.
- `services/export_service.py` and export pages own Excel workflows.
- `shared/` provides canonical models, services, UI helpers, and platform abstractions.

## Major Refactor Outcomes

### Platform Migration

The largest catalog pages were reduced from monoliths into orchestrators plus support packages.

- `ui/home_page.py`: 2223 -> 567 lines
- `ui/jaw_page.py`: 1423 -> 565 lines

This changed the structure from page-centered monoliths to:

- thin page orchestrators
- domain support folders with responsibility-scoped modules
- shared platform bases under `shared/ui/platforms/`

### Shared Support Modularization

Phase 11 extracted overlap between TOOLS and JAWS into shared helpers for:

- detached preview shell behavior
- topbar scaffolding
- page scaffolding
- selection plumbing

This lowered duplication without merging domain logic that still needs to stay separate.

### Measurement Editor Track

The measurement editor is no longer a fully isolated monolith, but it is still one of the largest remaining refactor targets.

Current state:

- dialog orchestrator in `ui/measurement_editor_dialog.py`
- extracted coordinators in `ui/measurement_editor/coordinators/`
- refactor plan tracked in `MEASUREMENT_EDITOR_REFACTOR_PLAN.md`

## Functional Areas

### TOOLS

The TOOLS side provides:

- searchable and filterable tool catalog
- delegate-rendered catalog cards
- detail panel with metadata and component breakdown
- add/edit/copy/delete flows
- tool selector integration for Setup Manager
- measurement-editor support for tool-related 3D annotations
- detached 3D preview workflow

### JAWS

The JAWS side provides:

- searchable and filterable jaw catalog
- jaw-specific detail panel and preview rules
- add/edit/delete flows
- jaw selector integration for Setup Manager
- detached 3D preview workflow with jaw transform persistence

### Selectors

Selector dialogs are standalone and session-based.

- Tool selector: catalog plus assignment panel
- Jaw selector: catalog plus spindle-slot assignment panel
- result payloads are returned to Setup Manager by IPC

### Excel I/O

The app supports export/import for library data and keeps import/export behavior app-local even though the shared platform layer now exists.

## 3D Preview Status

Current behavior:

- detached preview is supported and actively used
- inline detail-panel preview is intentionally disabled for now by config fallback
- the detail panel shows a placeholder message directing users to the detached preview window
- jaw preview transforms and measurement-overlay support still exist behind the same preview stack

If inline preview is restored later, it should be done as a focused UX/performance task rather than folded into unrelated refactors.

## Integration With Setup Manager

- Setup Manager opens Tool Library through local IPC.
- Tool Library can be opened in normal mode or with master filters derived from a selected work.
- Tool Library owns selector session lifecycle and sends selection payloads back to Setup Manager.
- Ownership stays clean: master data here, operational setup data there.

## Running From Source

From this folder:

```powershell
..\.venv\Scripts\python.exe main.py
```

From the repository root:

```powershell
.\run.bat
```

## Build

Primary packaged build path uses the included spec file.

```powershell
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean library.spec
```

## Validation

Recommended validation after library-side changes:

1. open TOOLS catalog
2. open JAWS catalog
3. open detached 3D preview from both domains
4. verify selector dialogs still return payloads
5. test Excel export/import path if touched
6. run `python scripts/run_quality_gate.py` from the repository root

## Near-Term Engineering Targets

- finish slimming the measurement editor orchestrator
- keep support folders responsibility-focused rather than accumulating wrapper-only modules
- reduce the remaining duplicate-baseline refactor targets
- decide whether inline detail preview should be restored or documented as permanently detached-only

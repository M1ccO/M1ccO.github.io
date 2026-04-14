# Tools and jaws Library — AI Quick Spec

## Role

This app is the master-data side of the workspace. It owns tool records, jaw records, library-side editor dialogs, selector dialogs, Excel workflows, and library-side preview behavior.

## Current Status (April 2026)

- phases 0-9 platform overhaul: complete
- phase 11 shared support modularization: complete
- `ui/home_page.py`: 567 lines
- `ui/jaw_page.py`: 565 lines
- `ui/measurement_editor_dialog.py`: 1381 lines
- detached preview is the supported primary preview path
- inline detail preview is currently disabled via runtime fallback
- quality gate passed on 2026-04-14

## Critical Paths

- `main.py` — app bootstrap, IPC server, service graph
- `config.py` — canonical paths, DB locations, icon mappings, preview flags
- `data/migrations/` — tool and jaw schema migration modules
- `services/tool_service.py` — tool CRUD, normalization, legacy compatibility
- `services/jaw_service.py` — jaw CRUD and normalization
- `services/export_service.py` — Excel workflows
- `ui/main_window.py` — shell, navigation, selector session lifecycle, IPC
- `ui/home_page.py` + `ui/home_page_support/` — TOOLS page orchestrator and support modules
- `ui/jaw_page.py` + `ui/jaw_page_support/` — JAWS page orchestrator and support modules
- `ui/tool_editor_dialog.py` + `ui/tool_editor_support/` — tool CRUD dialog
- `ui/jaw_editor_dialog.py` + `ui/jaw_editor_support/` — jaw CRUD dialog
- `ui/selectors/` — Tool/Jaw selector dialogs
- `ui/measurement_editor_dialog.py` + `ui/measurement_editor/coordinators/` — measurement editing stack

## Boundaries

Non-negotiables:

- do not move tool/jaw ownership into Setup Manager
- do not import Setup Manager modules directly into this app
- use canonical `shared.*` paths for shared logic
- keep tools and jaws as separate database domains
- keep migrations additive-only

## Refactor Assessment

What is already strong:

- page orchestration moved to `CatalogPageBase`
- duplicated page scaffolding reduced through shared helpers
- support folders now carry most domain-specific UI responsibilities
- selector workflows are isolated into standalone dialog modules

What is still active:

- measurement editor consolidation and final orchestrator slimming
- duplicate baseline reduction for the remaining classified collisions
- decision on future inline-preview support

## Preview And Measurement Notes

- detached preview remains functional and should be treated as the stable user path
- measurement editor coordinator extraction has already started; the dialog is no longer the only location of measurement logic

## Done Criteria For Changes

1. touched modules compile cleanly
2. catalog pages still load and filter correctly
3. selector dialogs still submit payloads correctly
4. detached preview still opens and syncs
5. import/export behavior remains unchanged if touched
6. `python scripts/run_quality_gate.py` passes from repo root

# NTX Setup Manager — Developer Guide

## Overview

This workspace contains two separate PySide6 desktop apps that run side-by-side and communicate via `QLocalSocket` IPC:

| App | Root | Entry point |
|---|---|---|
| Tools and jaws Library | `Tools and jaws Library/` | `Tools and jaws Library/main.py` |
| Setup Manager | `Setup Manager/` | `Setup Manager/main.py` |

Shared code (models, services, UI base classes) lives in `shared/`.  
Tests live in `tests/`.

---

## Prerequisites

- **Python 3.12 or 3.13** (3.10+ will work; the venv was built on 3.13)
- No other system dependencies — all runtime deps are Python packages

---

## Environment Setup

A single venv at the workspace root covers both apps.

```bat
# From the workspace root (c:\Users\pz9079\NTX Setup Manager):
python -m venv .venv
.venv\Scripts\pip install -r "Tools and jaws Library\requirements.txt"
```

The `run.bat` at the workspace root handles venv creation automatically on first launch.

---

## Running the Apps

**Recommended** — use the launcher scripts so window geometry and IPC are wired up correctly:

```bat
# Launch both apps (Setup Manager in foreground, Library in background):
run.bat

# Launch Library standalone (for testing catalog features):
.venv\Scripts\python.exe "Tools and jaws Library\main.py"

# Launch Setup Manager standalone:
.venv\Scripts\python.exe "Setup Manager\main.py"
```

Both apps read their own `config.py` for paths. When running from source, databases land in the app subdirectory (e.g., `Tools and jaws Library/databases/`). In a frozen build they land under `%LOCALAPPDATA%`.

---

## DEV_MODE and IS_FROZEN

Both `config.py` files define two flags:

```python
IS_FROZEN = getattr(sys, 'frozen', False)   # True inside a PyInstaller build
DEV_MODE   = not IS_FROZEN                  # True when running from source
```

`DEV_MODE` controls logging level:
- **DEV_MODE = True** → `logging.DEBUG` — every service call, IPC event, and filter evaluation is logged to stdout and to `app.log` in the app directory
- **DEV_MODE = False** → `logging.WARNING` — only warnings and errors go to the log

`app.log` location:
- Source run: `Tools and jaws Library/app.log` / `Setup Manager/app.log`
- Frozen run: `%LOCALAPPDATA%\Tools and jaws Library\app.log` / `%LOCALAPPDATA%\Setup Manager\app.log`

---

## Running Tests

```bat
# Run all tests from the workspace root:
.venv\Scripts\python.exe -m unittest discover -s tests -v

# Run a specific file:
.venv\Scripts\python.exe tests\test_priority1_targeted.py -v
.venv\Scripts\python.exe tests\test_shared_regressions.py -v
```

Tests use an offscreen Qt platform (`QT_QPA_PLATFORM=offscreen`) — no display required.  
All tests use in-memory SQLite — no test databases are written to disk.

### Test files

| File | What it covers |
|---|---|
| `tests/test_priority1_targeted.py` | ToolService filters, JawService filters, migration idempotence, localization fallbacks, selector_mime round-trips, filter_coordinator master filter |
| `tests/test_shared_regressions.py` | Shared UI component regressions, localization merge behavior |

---

## Quality Gate Scripts

Located in `scripts/`. Run these before merging to catch structural regressions:

```bat
.venv\Scripts\python.exe scripts\import_path_checker.py
.venv\Scripts\python.exe scripts\module_boundary_checker.py
.venv\Scripts\python.exe scripts\duplicate_detector.py
.venv\Scripts\python.exe scripts\run_parity_tests.py
```

---

## IPC Flow (Selector Workflow)

When Setup Manager needs a tool or jaw selection:

1. Setup Manager sends `open_selector` JSON payload over `QLocalSocket` to the Library's named server.
2. Library `MainWindow._open_selector_dialog_for_session()` opens `ToolSelectorDialog` or `JawSelectorDialog`.
3. User makes selection and clicks DONE.
4. Dialog calls `on_submit` callback → `_on_selector_dialog_submit()` → `_send_selector_result_payload()`.
5. Library connects back to Setup Manager's callback socket and sends the result JSON.

See `architecture-map.json` → `ipc.selectorFlow` for the full step-by-step.

---

## Architecture Map

`architecture-map.json` at the workspace root is the machine-readable reference for AI agents and tooling. It describes app ownership, module structure, IPC flow, dependency rules, and key entry points.

`AGENTS.md` contains the human-readable navigation guide — including a user-language → technical translation table (e.g., "Tool Selector" → `ui/selectors/tool_selector_dialog.py`).

---

## Database Files

| File | Owner | Default dev path |
|---|---|---|
| `tool_library.db` | Library | `Tools and jaws Library/databases/` |
| `jaws_library.db` | Library | `Tools and jaws Library/databases/` |
| `setup_manager.db` | Setup Manager | `Setup Manager/databases/` |

All three databases are SQLite. Schema is created/migrated automatically at startup via `data/migrations/`. Migrations are idempotent — running them twice on the same database is safe.

---

## Key Files Quick Reference

| What | Where |
|---|---|
| Platform base class (inherit this for new catalog pages) | `shared/ui/platforms/catalog_page_base.py` |
| Tool catalog page orchestrator | `Tools and jaws Library/ui/home_page.py` |
| Jaw catalog page orchestrator | `Tools and jaws Library/ui/jaw_page.py` |
| Tool selector dialog | `Tools and jaws Library/ui/selectors/tool_selector_dialog.py` |
| Jaw selector dialog | `Tools and jaws Library/ui/selectors/jaw_selector_dialog.py` |
| Selector IPC lifecycle | `Tools and jaws Library/ui/main_window.py` (`_open_selector_dialog_for_session` and surrounding methods) |
| Localization | `shared/services/localization_service.py` |
| Library config (paths, constants) | `Tools and jaws Library/config.py` |
| Setup Manager config | `Setup Manager/config.py` |

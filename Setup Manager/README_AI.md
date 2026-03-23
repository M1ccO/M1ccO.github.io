# NTX Setup Manager — Developer and AI Reference

This document is the authoritative technical reference for AI agents and developers working on the Setup Manager codebase. Read it before modifying files.

## System Overview

NTX Setup Manager is the operational desktop application in the NTX software family. It manages work records and production logbook history while reading master data from the sibling Tool Library databases.

Tech stack:
- PySide6
- SQLite via sqlite3
- openpyxl for Excel export
- reportlab for PDF setup cards
- Python 3.10+
- Windows

Setup Manager owns only its own data:
- works table
- logbook table

It does not create, migrate, or write to the Tool Library or Jaws Library databases. Those remain the source of truth for tools and jaws.

## High-Level Architecture

main.py
- creates QApplication and startup progress dialog
- opens the setup database
- instantiates setup-specific services
- wires read-only access to tool and jaw master databases through DrawService
- opens MainWindow

MainWindow hosts these pages:
- SetupPage
- DrawingPage
- LogbookPage

MainWindow also owns the bidirectional handoff to the sibling Tool Library process.

Shared responsibilities:
- WorkService manages works CRUD and JSON serialization of tool ID lists
- LogbookService manages run history and batch serial generation
- DrawService locates drawing PDFs and reads tool/jaw references from external databases in read-only mode
- PrintService generates setup-card PDFs

## Configuration

config.py is the canonical path source.

Important paths:
- DB_PATH: Setup Manager database
- DRAWINGS_DIR: directory scanned for drawing PDFs
- TOOL_LIBRARY_DB_PATH: preferred tool master database path
- JAW_LIBRARY_DB_PATH: preferred jaw master database path

Path resolution order for external master databases is:
1. sibling NTX Tool Library/databases under the shared parent folder
2. NTX Tool Library user-data directory when running frozen
3. local fallback files under Setup Manager/databases

This allows Setup Manager to work directly against the sibling Tool Library repository in development while still tolerating standalone copies.

## Database Layer

data/database.py
- thin sqlite3 wrapper for the setup database
- sets row_factory to sqlite3.Row
- calls create_or_migrate_schema() on init

data/migrations.py owns the setup schema.

works table columns:
- work_id TEXT PK
- drawing_id TEXT
- description TEXT
- drawing_path TEXT
- main_jaw_id TEXT
- sub_jaw_id TEXT
- head1_zero TEXT
- head2_zero TEXT
- head1_program TEXT
- head2_program TEXT
- head1_tool_ids TEXT JSON list
- head2_tool_ids TEXT JSON list
- robot_info TEXT
- notes TEXT
- created_at TEXT
- updated_at TEXT

logbook table columns:
- id INTEGER PK AUTOINCREMENT
- work_id TEXT
- order_number TEXT
- quantity INTEGER
- batch_serial TEXT
- date TEXT
- notes TEXT

Migration strategy is additive only.

## Services

services/work_service.py
- list_works(search)
- get_work(work_id)
- save_work(work_dict)
- delete_work(work_id)
- duplicate_work(source_id, new_id, new_description)

Tool ID lists are stored as JSON strings and returned as Python lists.

services/logbook_service.py
- list_entries(search, filters)
- get_entry(entry_id)
- add_entry(work_id, order_number, quantity, notes, custom_serial, entry_date)
- generate_next_serial(work_id, year, quantity)
- delete_entry(entry_id)
- export_entries_to_excel(entries, output_path)

Serial format is letter-prefix plus year and quantity, for example A26/50.

services/draw_service.py
- list_drawings(search)
- open_drawing(path)
- list_tool_refs(force_reload=False)
- list_jaw_refs(force_reload=False)
- get_tool_ref(tool_id)
- get_jaw_ref(jaw_id)
- get_reference_source_status()

External database access must stay read-only. Use SQLite URI mode with mode=ro and immutable=1.

services/print_service.py
- generate_setup_card(work, entry, output_path)

Current print output is a single-page PDF summary. Expand here for richer card layouts rather than embedding print logic in UI files.

## UI Layer

ui/main_window.py
- builds left navigation rail
- hosts SetupPage, DrawingPage, and LogbookPage
- shows active setup/master database state in the status bar
- launches or re-activates Tool Library through `QLocalSocket` IPC
- applies a short fade-out animation before cross-app handoff

ui/setup_page.py
- lists work records
- opens WorkEditorDialog for new/edit actions
- deletes and duplicates works
- prints setup cards
- shows referenced jaw/tool metadata by reading the external master databases

Current behavior notes (March 2026):
- setup list cards have two modes:
	- normal mode: Work ID, Drawing, Description, Last run
	- compact mode (detail panel open): Work ID and Description only
- compact mode is responsive and keeps row height close to normal rows
- "Open in Tool Library" stays visible; enable state depends on selected work links

ui/work_editor_dialog.py
- general, spindle, tool, and notes tabs
- jaw fields use completers fed from read-only jaw references
- tool selections are populated from read-only tool references
- unresolved master-data references warn but do not block save

ui/drawing_page.py
- lists PDF drawings from DRAWINGS_DIR
- opens the selected file using the OS handler

ui/logbook_page.py
- filters and lists logbook entries
- shows entry details
- creates logbook entries
- supports sortable columns
- exports the current view to Excel

Current behavior notes (March 2026):
- search is a single inline field shown next to the search icon
- date format in table/details is `DD/MM/YYYY`
- search supports broad mode and column-targeted mode
- clicking a header while search is open sets active search column
- active search column has border highlight
- column-search mode keeps rows deselected by default to reduce distraction
- clicking empty table space clears current selection

## Cross-App Switching

Setup Manager and Tool Library are designed to feel like one paired workflow on Windows.

- Setup Manager pre-warms Tool Library in hidden mode during startup when available.
- `SETUP_MANAGER_SERVER_NAME` and `TOOL_LIBRARY_SERVER_NAME` are used for single-instance IPC handoff.
- Foreground transfer relies on `AllowSetForegroundWindow(...)` before sending the IPC show message.
- Receiver-side activation uses both Qt window activation and Win32 `SetForegroundWindow(...)` as a fallback.
- Sender-side UI fades out before hide; receiver-side UI fades in after show.

Keep this IPC flow intact when modifying launch behavior. Avoid reintroducing title-based window hunts as a primary path.

## Important Rules

- Do not add tool or jaw schema to Setup Manager migrations.
- Do not write to the sibling Tool Library databases.
- Keep work records reference-based: store tool IDs and jaw IDs, not duplicated master rows.
- Preserve additive-only schema migrations for the setup database.
- Keep UI logic pragmatic and local to the page or dialog that owns it.

## Recommended Verification

- Start the app and confirm the status bar points to the expected setup, tool, and jaw databases.
- Switch to Tool Library and back to confirm the IPC handoff and fade transitions still work.
- Open the Work editor and confirm jaw completion and tool lists load from the sibling Tool Library databases.
- Create and edit a work with tool and jaw references.
- Add a logbook entry and verify serial generation.
- Export logbook entries to Excel.
- Print a setup card PDF.
- Confirm missing tool or jaw databases do not crash the app and unresolved references are shown clearly.

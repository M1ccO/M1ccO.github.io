# Setup Manager

Setup Manager is the operational desktop application in this software family. It stores setup records for actual work runs, links those records to tool and jaw master data, tracks production history in a logbook, and generates printable setup cards.

The application is designed to sit beside Tools and jaws Library in the same parent folder and read its tool and jaw databases in read-only mode.

## What the Software Does

Setup Manager answers the question: how is this work actually run?

It manages:
- work records with drawing IDs, jaw assignments, zero points, programs, and tool ID selections
- a logbook of completed batches with serial generation
- drawing PDF browsing
- printable setup cards
- direct, bidirectional switching with the sibling Tool Library app from the main UI

It does not own tool or jaw master data. Those records stay in Tools and jaws Library.

## Main Areas

### Setups

The Setups page is the main operational view.

Each work record stores:
- Work ID
- Drawing ID
- Description
- Drawing path
- Main jaw ID
- Sub jaw ID
- Head 1 zero point and program
- Head 2 zero point and program
- Tool IDs for Head 1 and Head 2
- Robot information
- Notes

The detail panel shows:
- a summary header with drawing and update information
- last-run information from the logbook
- jaw assignments resolved against the Tool Library jaw database
- tool selections resolved against the Tool Library tool database
- data-source state for the linked master databases

Current Setups list UX behavior:
- when the detail panel is open, the left list cards switch to compact mode
- compact mode shows only Work ID and Description
- compact cards stay responsive to available width and keep near-normal row height

From this page you can:
- add a work
- edit a work
- duplicate a work
- delete a work
- print a setup card

### Drawings

The Drawings page scans the configured drawing folder for PDF files and lets you open them with the system PDF handler.

### Logbook

The Logbook page stores run history for completed work batches.

Each entry includes:
- date
- work ID
- order number
- quantity
- batch serial
- notes

Filtering supports:
- a single inline search field toggled from the search icon
- broad search across Date, Serial, Work ID, Order, Qty, and Notes
- column-targeted search by clicking a table header while search is open

Current Logbook UX behavior:
- date is displayed as `DD/MM/YYYY`
- date search works with displayed date format
- active search column is highlighted in the header
- clicking empty table area clears row selection
- row selection uses border-style highlighting instead of full-row fill

The page also supports:
- click-to-sort table columns
- manual log entry creation from the Logbook page
- Excel export of the filtered results

## Integration with Tools and jaws Library

Setup Manager reads the tool and jaw master databases from Tools and jaws Library without modifying them.

Default path resolution order for the linked databases is:
1. sibling Tools and jaws Library/databases under the shared parent folder
2. packaged Tools and jaws Library user-data directory
3. local fallback database files under Setup Manager/databases

The Main UI includes a direct switch into Tool Library.

Window switching behavior:
- Setup Manager starts Tool Library in the background during startup when available
- switching between the two apps uses local IPC instead of a full cold restart when possible
- both directions use a short fade-out and fade-in transition so the handoff feels like one continuous workflow
- Setup Manager stays the owner of setup and logbook data while Tool Library remains the owner of tool and jaw master data

Use Tool Library to maintain tools and jaws. Use Setup Manager to build work setups from those references.

## Scope and Cleanup Notes (March 2026)

Setup Manager intentionally focuses on operational setup workflow only.

The following legacy copy-paste modules were removed from Setup Manager during cleanup:
- old Tool Library-style home catalog pages
- jaw catalog/editor/export pages
- tool editor/export pages
- unused tool/jaw/export/settings service stubs

If you need to edit tool or jaw master data, do it in Tools and jaws Library. Setup Manager reads those databases in read-only mode by design.

## Project Layout

```text
Setup Manager/
  main.py
  config.py
  data/
  services/
  ui/
  assets/
  preview/
  styles/
  databases/
  drawings/
```

Important modules:
- `data/database.py` and `data/migrations.py` manage the setup database
- `services/work_service.py` manages work CRUD
- `services/logbook_service.py` manages run history and serial generation
- `services/draw_service.py` handles drawing lookup and read-only master-data access
- `services/print_service.py` generates setup-card PDFs
- `ui/main_window.py` hosts the navigation shell and Tool Library launcher
- `ui/setup_page.py` is the main work-management page
- `ui/logbook_page.py` provides filtering and export for run history

## Batch Serial Format

Logbook serials are generated per work and per year.

Format:
- `A26/20`
- `B26/20`
- `C26/20`

Meaning:
- prefix letter increments for each batch of the same work in the same year
- `26` is the last two digits of the year
- `20` is the batch quantity used when the entry was created

Custom serial override is also supported when needed.

## How to Run

Use one of these two modes.

### Mode A: Developer run (source code)

Requirements:
- Windows
- Python 3.10+
- dependencies installed into the local virtual environment

Run from the workspace root:

```powershell
.\run.bat
```

Or from inside the project folder:

```powershell
.\run.cmd
```

### Mode B: Portable distribution (recommended for sharing)

This is the preferred way to share with other users, especially when local admin rights are limited.

Build once on your machine:

```powershell
.\Setup Manager\build_portable.cmd
```

Then share this folder from your machine:

```text
Setup Manager\dist\Setup Manager
```

On the target machine, run:

```text
Setup Manager.exe
```

Notes:
- target machine does not need Python installed
- no pip install is required on the target machine
- no admin rights are typically required when running from a user-writable location like Desktop

## Runtime Dependencies

Runtime dependencies are listed in `requirements.txt` and include:
- PySide6
- numpy
- openpyxl
- reportlab

## Data Ownership Rules

- Setup Manager owns only its own setup and logbook database.
- Tool and jaw master data remain in Tools and jaws Library.
- External tool and jaw databases are read-only from Setup Manager.
- Missing master-data references do not block saving a work, but they are shown clearly in the UI.

## Recommended Verification

- start Setup Manager
- confirm the status bar shows the expected setup, tool, and jaw databases
- switch to Tool Library from the main UI and back again
- create a work that references tools and jaws from the sibling Tool Library database
- add a logbook entry and verify serial generation
- filter the logbook by work, order, year, and date range
- print a setup card PDF

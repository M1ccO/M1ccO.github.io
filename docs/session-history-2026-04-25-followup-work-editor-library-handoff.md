# Session History - 2026-04-25 (Follow-up: Work Editor / Library Handoff)

Branch: `codex/before-shared-styles`  
Date: `2026-04-25`

---

## Context

This follow-up session focused on handoff stability between Setup Manager and Tools/Jaws Library, after multiple reports of:

1. Python instance flash around Work Editor / selector launch
2. Setup Manager freezing when opening Library from selector flow
3. Setup Manager freezing after editing Tool/Jaw in Library, returning to Setup Manager, then reopening Library

The goal was root-cause debugging (step-by-step), not broad refactor changes.

---

## Issue 1: Setup Manager Freeze During Library Open/Handoff

### Symptom

Setup Manager could appear frozen when opening Library from Setup Manager or after selector-related transitions.

### Investigation Notes

- `setup_manager_modal_trace.log` and `tool_library_launch_trace.log` were used.
- We found handoff transitions could stay pending if completion callback was delayed/missed in some paths.
- Earlier synchronous IPC behavior could also make the UI feel blocked under stale socket conditions.

### Fixes Applied

#### 1) Handoff fallback recovery timer (Setup Manager)

File:
- `Setup Manager/ui/main_window_support/library_handoff_controller.py`

Changes:
- Added fallback timer for sender transition recovery.
- If completion callback does not return in time, Setup Manager cancels pending sender transition and restores surface.
- Timer is cleared on normal completion and timeout/failure paths.

New env knob:
- `NTX_LIBRARY_HANDOFF_FALLBACK_TIMEOUT_MS` (default `4500`, `0` disables fallback)

#### 2) Faster non-blocking first IPC attempt (Setup Manager)

Files:
- `Setup Manager/ui/main_window.py`
- `Setup Manager/ui/main_window_support/library_handoff_controller.py`

Changes:
- `_send_to_tool_library(...)` now supports `retries` and `timeout_ms` parameters.
- First open attempt now uses fast IPC (`retries=1`, short timeout), then async retry path if needed.
- Launch is only used when ready checks indicate it is actually needed.

New env knob:
- `NTX_LIBRARY_OPEN_FAST_IPC_TIMEOUT_MS` (default `220`)

### Status

Partially mitigated first freeze vector and removed UI-blocking behavior from first IPC path.

---

## Issue 2: Freeze After Edit -> Return -> Reopen Library

### Symptom

Repro path:
1. Open Library from Setup Manager
2. Edit Tool or Jaw
3. Return to Setup Manager
4. Open Library again

Setup Manager could freeze and Library would not open correctly.

### Root Cause (Observed)

Tool Library logs showed this pattern on bad cycles:

- Logged: `ipc: request received ... show=True`
- Missing next expected log: `ipc: selector_active_request=...`

This indicated `win.apply_external_request(...)` could throw during IPC processing in `Tools and jaws Library/main.py`, which interrupted handoff flow and prevented reliable completion callback behavior.

### Fixes Applied

File:
- `Tools and jaws Library/main.py`

Changes:
- Wrapped `win.apply_external_request(payload, caller_was_visible=was_visible)` in `try/except` with `logger.exception(...)`.
- Continued handoff/show pipeline even if `apply_external_request` fails.
- Wrapped `_show_main_window()` logic in `try/except` and added emergency callback send:
  - If `_show_main_window()` fails and `handoff_hide_callback_server` exists, still send transition completion callback to avoid Setup Manager getting stuck.

### Status

User-confirmed result:
- "OKay, now it doesn't freeze!"

Marked as **fixed in current test cycle**.

---

## Notes on Test Execution / Environment

### Important observation

In one traced startup, `tool_library_launch_trace.log` showed:
- `enable_hidden_auto_launch: false`

even though env had been set to `1` in user shell. This can happen depending on launcher/env inheritance path (`run.bat`, restarted processes, prior instances). It did not block the final freeze fix but is important for future diagnostics.

### run.bat behavior

`run.bat` starts app with `.venv\Scripts\pythonw.exe` and kills prior python/pythonw instances tied to Setup Manager/Library scripts before relaunch.

---

## Files Changed In This Follow-up Session

1. `Setup Manager/ui/main_window_support/library_handoff_controller.py`
- Added handoff fallback timer and clear/start helpers
- Added fast IPC/open dispatch path
- Added env-based timeout controls

2. `Setup Manager/ui/main_window.py`
- Extended `_send_to_tool_library(...)` to accept `retries` and `timeout_ms`

3. `Tools and jaws Library/main.py`
- Added exception-safe `apply_external_request` wrapper with structured logging
- Added exception-safe `_show_main_window` with emergency transition completion callback
- Improved IPC exception logging in socket consume path

---

## PowerShell Test Snippet Used

```powershell
$env:NTX_ENABLE_TOOL_LIBRARY_PRELOAD='1'
$env:NTX_ENABLE_HIDDEN_TOOL_LIBRARY_AUTO_LAUNCH='1'
$env:NTX_TOOL_LIBRARY_LAUNCH_TRACE='1'
$env:NTX_TOOL_LIBRARY_LAUNCH_TRACE_RESET_ON_START='1'
$env:NTX_LIBRARY_HANDOFF_FALLBACK_TIMEOUT_MS='4500'
$env:NTX_LIBRARY_OPEN_FAST_IPC_TIMEOUT_MS='220'

cd "C:\Users\Omistaja\Desktop\NTX Setup Manager"
.\run.bat
```

---

## Suggested Next Verification Pass

1. Repeat the edit->return->reopen loop 10+ times for Tool and Jaw editors.
2. Run same cycle with both direct Library opens and selector-initiated opens.
3. Keep traces enabled during verification:
   - `Setup Manager/temp/tool_library_launch_trace.log`
   - `Tools and jaws Library/app.log`

If instability reappears, new exception guards should now reveal precise failing call sites instead of silent freezes.

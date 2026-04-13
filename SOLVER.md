# Setup Manager Startup Freeze - Diagnostic & Solution Guide

## Symptoms
- Setup Manager freezes on startup (splash screen appears but doesn't progress)
- No error messages visible
- May take 30+ seconds before responding or closing

## Root Cause Analysis

The freeze is likely caused by **blocking initialization work** that happens before the Setup Manager window is shown. Common culprits:

1. **Service initialization** (database connections, settings loading)
2. **Shared module imports** (localization, UI styles)
3. **Deferred page creation callbacks** firing during Setup Manager init
4. **IPC server setup** waiting for responses

## Diagnostic Steps

### Step 1: Identify Where the Freeze Occurs
Add timing diagnostics to Setup Manager's main.py:

**File:** `Setup Manager/main.py`

**Action:** Add these lines at key startup checkpoints:

```python
import time
import sys

# At the very start of main()
print(f"[{time.time():.1f}] main() starting", flush=True)

# After each major step:
print(f"[{time.time():.1f}] Step: Importing services", flush=True)
# ... service imports ...

print(f"[{time.time():.1f}] Step: Creating MainWindow", flush=True)
# ... MainWindow creation ...

print(f"[{time.time():.1f}] Step: Showing window", flush=True)
win.show()

print(f"[{time.time():.1f}] Step: Entering event loop", flush=True)
```

**How to run:**
```powershell
python "Setup Manager\main.py" 2>&1 | Tee-Object -FilePath setup_timing.log
```

This will show exactly where the freeze happens. Look for long delays between consecutive timestamps.

### Step 2: Check Shared Module Imports
Run this to verify shared modules load quickly:

```powershell
python -c "import time; s = time.time(); from shared.services.localization_service import LocalizationService; print(f'Localization load: {(time.time()-s)*1000:.0f}ms')"
```

If any shared module takes >500ms, that's a suspect.

### Step 3: Verify Tool Library IPC Server
The Setup Manager might be trying to communicate with Tool Library. Check if it's blocking:

```powershell
# In one terminal, start Tool Library
python "Tools and jaws Library\main.py"

# In another terminal, check if it responds
python -c "from PySide6.QtNetwork import QLocalSocket; from config import TOOL_LIBRARY_SERVER_NAME; s = QLocalSocket(); s.connectToServer(TOOL_LIBRARY_SERVER_NAME); print('Connected:', s.state() == 3)"
```

## Solutions (In Priority Order)

### Solution A: Defer Non-Critical Initialization
Move non-UI setup to after `win.show()`:

**File:** `Setup Manager/main.py` (in main function, after `win = MainWindow(...)`)

```python
# Before (blocking):
# services initialization happens before win.show()

# After (deferred):
win.show()

# Now defer expensive operations
from PySide6.QtCore import QTimer
QTimer.singleShot(100, lambda: _complete_startup_async())

def _complete_startup_async():
    # Load any remaining cache/preferences
    pass
```

### Solution B: Optimize Shared Module Imports
Check for circular imports or expensive operations in:
- `shared/services/localization_service.py`
- `shared/services/ui_preferences_service.py`
- `shared/ui/bootstrap_visual.py`

**Action:** Move heavy initialization (file I/O, database queries) to lazy-load functions instead of module-level code.

### Solution C: Skip Tool Library Server Check at Startup
If Setup Manager is waiting for Tool Library IPC server:

**File:** `Setup Manager/main.py`

Find the code that connects to TOOL_LIBRARY_SERVER and add a short timeout:

```python
# Before:
socket.connectToServer(server_name)
socket.waitForConnected()  # No timeout = blocks indefinitely

# After:
socket.connectToServer(server_name)
socket.waitForConnected(500)  # 500ms timeout max
```

### Solution D: Profile Startup with Python Profiler
Get detailed breakdown of what's slow:

```powershell
python -m cProfile -s cumtime "Setup Manager\main.py" 2>&1 | head -50
```

Look for functions with high cumulative time (cumtime column).

## Quick Test After Each Fix

```powershell
# Measure startup time
$start = Get-Date; python "Setup Manager\main.py"; $((Get-Date) - $start).TotalSeconds
```

Target: <2 seconds from `python main.py` to window appearing.

## If Still Frozen After All Steps

1. **Check for infinite loops:** Search Setup Manager code for `while True:` without event processing
2. **Check for deadlocks:** If multiple threads exist, they may be waiting for each other
3. **Verify database:** Try running smoke tests - if they fail, database might be locked/corrupted
   ```powershell
   python scripts/smoke_test.py
   ```

## Revert Last Changes (Nuclear Option)

If Setup Manager was working before recent changes:

```powershell
# Check git status for recent file changes
git log --oneline -10

# Revert to last known good commit
git checkout <commit-hash>
```

---

## How to Collect Info for Further Debugging

Run this command and share the output:

```powershell
# Collect timing data
python "Setup Manager\main.py" 2>&1 | Tee-Object -FilePath "$env:TEMP\setup_debug.log"

# Check file size (if >1MB, something is wrong)
(Get-Item "$env:TEMP\setup_debug.log").Length

# Show last 100 lines
Get-Content "$env:TEMP\setup_debug.log" -Tail 100
```

# Editor Focus Glitch Fix - Blueprint

## STATUS: COMPLETED ✅

All 4 CRUD functions have been updated with the focus fix pattern (dlg.show() + raise_() + activateWindow()) between dialog positioning and exec().

## GOALS

1. **Eliminate the visual glitch** where PYTHONW3.EXE appears in taskbar during Tool/Jaw editor open sequence
2. **Ensure proper focus handling** between dialog creation and `exec()` modal loop
3. **Preserve existing behavior** - blur effect, dialog positioning, save/cancel semantics
4. **No regression** - no white-screen issues, no data changes

## RULES

1. Do NOT change the blur effect timing or implementation
2. Do NOT modify dialog parenting or modal settings
3. Do NOT alter save/cancel flow or data persistence
4. Focus fix must be minimal and only affect editor launch
5. All changes isolated to CRUD action functions (`add_tool`, `edit_tool`, `add_jaw`, `edit_jaw`)

## DIAGNOSIS

Based on screenshot analysis:

- **First image**: Window shows blur effect, but PYTHONW3.EXE visible in taskbar = **focus lost**
- **Second image**: Editor "Edit Tool - T1" appears normally = **focus recovered**
- **Root cause**: Gap between dialog creation and `exec()` where focus drifts to taskbar

### Timeline (Current - Problematic)

```
Line 74-78:  dlg = AddEditToolDialog(...)     ← Heavy dialog init (includes WebEngine)
Lines 86-98: Blur applied, position set
Line 100:  dlg.exec()                      ← Only now dialog gets focus (TOO LATE!)
```

### Expected Fix Timeline

```
Line 74-78:  dlg = AddEditToolDialog(...)
Lines 86-98: Blur applied, position set
[FOCUS FIX]: dlg.raise_() + dlg.activateWindow()
Line 100:  dlg.exec()
```

## STATUS: PROPOSED CHANGES

### File: `Tools and jaws Library/ui/home_page_support/crud_actions.py`

Functions to modify:

1. **`add_tool`** (lines 71-109)
   - Add after line 98 (`dlg.move(x, y)`) and before line 99 (`try:`):
   - Add: `dlg.raise_()`, `dlg.activateWindow()`, and optional Windows API focus

2. **`edit_tool`** (lines 112-181)
   - Add after line 170 (`dlg.move(x, y)`) and before line 171 (`try:`)
   - Same focus fix as add_tool

### File: `Tools and jaws Library/ui/jaw_page_support/crud_actions.py`

Functions to modify:

1. **`add_jaw`** (lines 76-107)
   - Add after line 98 (`dlg.move(x, y)`) and before line 99 (`try:`)

2. **`edit_jaw`** (lines 110-157)
   - Add after line 148 (`dlg.move(x, y)`) and before line 149 (`try:`)

## IMPLEMENTATION DETAILS

### Focus Fix Code Pattern

```python
# After dlg.move(x, y) and before try: block
dlg.show()
dlg.raise_()
dlg.activateWindow()
try:
    import ctypes
    ctypes.windll.user32.SetForegroundWindow(int(dlg.winId()))
except Exception:
    pass
```

Alternative Qt-only approach:

```python
# After dlg.move(x, y) and before try: block
from PySide6.QtCore import QTimer
QTimer.singleShot(0, dlg.raise_)
QTimer.singleShot(0, dlg.activateWindow)
```

## TESTING PROTOCOL

1. Manual test: Open editor 20+ times rapidly from tool list
2. Verify: No PYTHONW3.EXE in taskbar during launch
3. Verify: No white screen flash
4. Verify: Main window remains stable behind modal

## REGRESSION CHECKS

- [ ] Tool Editor open/close: No white screen
- [ ] Jaw Editor open/close: No white screen
- [ ] Blur effect still visible during editor open
- [ ] Save/cancel semantics unchanged
- [ ] Rapid open/close sequence stable
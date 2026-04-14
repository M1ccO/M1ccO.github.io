# Library Detail Panel, Selector & Warmup — Fix Log

Branch: `codex/before-shared-styles`

---

## What was broken

Three separate issues, each silently compounding the others.

### 1. Library crashed on startup — ImportError in `jaw_page.py`

The branch removed the `_warmup_preview_engine()` call from `jaw_page._perform_initial_load`
but left behind the import that fed it:

```python
# jaw_page_support/__init__.py never re-exported this name
from ui.jaw_page_support import warmup_preview_engine as _warmup_preview_engine_impl
```

`jaw_page_support/__init__.py` did not re-export `warmup_preview_engine` (it lives in
`jaw_page_support/detached_preview.py` directly). The moment the Library process started,
Python raised `ImportError: cannot import name 'warmup_preview_engine' from 'ui.jaw_page_support'`
and the app died silently — `pythonw.exe` swallowed stderr, so nothing appeared in `app.log`.

**Fix:** removed the broken import line and the dead `_warmup_preview_engine` wrapper method
from `jaw_page.py`.

---

### 2. Tool Selector dialog crashed on construction — AttributeError

After fixing the startup crash, the Library received the IPC selector request from Setup
Manager and started constructing `ToolSelectorDialog`. During `__init__` it called
`_prime_detail_panel_cache()`, which internally calls `populate_detail_panel`, which
eventually reaches `detail_panel_builder.py` line 459:

```python
if self.page._detail_preview_model_key != current_key:   # AttributeError here
```

`HomePage` had been updated on this branch to initialize `_detail_preview_model_key` and
`_detail_preview_widget` explicitly. `JawSelectorDialog` already had them. `ToolSelectorDialog`
was missed.

**Fix:** added the two missing attribute initializations to `ToolSelectorDialog.__init__`:

```python
self._detail_preview_widget = None
self._detail_preview_model_key = None
```

---

### 3. Dead `_warmup_preview_engine` wrapper left in `home_page.py`

The same dead-import pattern existed in `home_page.py`, though it did not crash (the import
path was a direct module reference, not a package re-export). The wrapper method was never
called. Removed the import alias and the method.

---

### 4. Setup Manager `SetupPage` — entire dead detail panel removed

`SetupPage` still contained a full detail panel implementation that was never activated:
`_details_open` was always `False`, `show_details`/`hide_details` were no-ops, and none of
the detail UI widgets (`detail_id_label`, `detail_sections`, etc.) were ever instantiated.
The splitter only added one panel.

**Removed:**

| Category | What was removed |
|---|---|
| Imports from `setup_page_support` | `AdaptiveColumnsWidget`, `clear_section`, `format_lookup`, `format_lookup_list`, `head_zero_fields`, `make_detail_field`, `set_jaw_overview`, `set_section_fields`, `set_tool_cards`, `ToolNameCardWidget`, `WorkRowWidget` |
| Imports from `config` | `TOOL_ICONS_DIR`, `TOOL_TYPE_TO_ICON`, `DEFAULT_TOOL_ICON` |
| Qt import | `QScrollArea` |
| `__init__` variables | `_clamping_splitter`, `_section_title_keys`, `_section_titles`, `_detail_section_title_labels`, `_details_open` |
| Dead local variable | `details_were_open` in `refresh_works` |
| Dead `apply_localization` code | `_section_titles` rebuild, `detail_heading_key` guard, `_detail_section_title_labels` loop |
| Dead `_on_external_references_maybe_changed` block | `if self._details_open and self.current_work_id: self._refresh_details()` |
| No-op methods | `_on_detail_toggle_clicked`, `show_details`, `hide_details`, `_on_splitter_moved` |
| Dead methods | `_format_lookup`, `_format_lookup_list`, `_set_section_fields`, `_make_detail_field`, `_clear_section`, `_set_jaw_overview`, `_set_tool_cards`, `_refresh_details` |
| Deleted files | `setup_page_support/detail_fields.py`, `detail_rendering.py`, `row_widgets.py` |
| `setup_page_support/__init__.py` | Stripped to only the three live exports |

---

### 5. Window flash on first detail-panel open — OpenGL warmup restored

On Windows, the first time a `StlPreviewWidget` (an OpenGL widget) is created inside an
already-visible window, the OS briefly hides and reshows the window to accommodate the new
OpenGL pixel format. This made the whole Library window appear to close and reopen the first
time the user opened the detail panel.

The branch had removed the `_warmup_preview_engine()` call from both pages' deferred load.
The function itself still existed in `home_page_support/detached_preview.py` and
`jaw_page_support/detached_preview.py` — complete with a comment reading:

> "Force one-time OpenGL initialization offscreen so the first visible detail preview does
> not appear to close/reopen the whole window."

**Fix:** restored the call at the end of `_perform_initial_load` in both pages, using an
inline import to avoid polluting module-level imports:

```python
# home_page.py
from ui.home_page_support.detached_preview import warmup_preview_engine
warmup_preview_engine(self)

# jaw_page.py
from ui.jaw_page_support.detached_preview import warmup_preview_engine
warmup_preview_engine(self)
```

The warmup creates a tiny 8×8 `StlPreviewWidget` at position (-10000, -10000), shows it for
one event-loop tick to trigger the OpenGL init, then hides it. After 10 seconds it is
deleted. From the user's perspective: no flash, ever.

---

## Result

| Before | After |
|---|---|
| Library crashes on startup (ImportError) | Library starts cleanly |
| Tool Selector never opens (AttributeError) | Tool & Jaw Selectors open instantly |
| Detail panel flashes window closed on first open | Detail panel opens seamlessly every time |
| ~350 lines of dead detail-panel code in Setup Manager | Gone |

---

## Potential improvements

The following are not bugs — the app works correctly after the fixes above. These are
architectural notes for future cleanup passes.

### High value

1. **Move `_prime_detail_panel_cache` out of selector constructors**
   Both `ToolSelectorDialog` and `JawSelectorDialog` call `_prime_detail_panel_cache()` at
   the end of `__init__`. This pre-renders the first detail payload synchronously, blocking
   the constructor. It should be deferred to a `QTimer.singleShot(0, ...)` so the dialog
   appears immediately and populates on the next tick — matching the pattern already used
   in `toggle_tool_details`.

2. **Single `_warmup_preview_engine` in shared code**
   The warmup function is duplicated in `home_page_support/detached_preview.py` and
   `jaw_page_support/detached_preview.py` with near-identical bodies. It could live in
   `shared/ui/helpers/` and both pages import it from there, cutting the duplication.

3. **`_inline_preview_warmup` guard missing in `home_page_support`**
   `jaw_page_support/detached_preview.warmup_preview_engine` guards against being called
   twice (`if getattr(page, '_inline_preview_warmup', None) is not None: return`).
   The `home_page_support` version does not have this guard. If `showEvent` fires twice
   before `_initial_load_done` is set (rare but possible), the warmup would run twice.
   Add the same guard.

4. **`detail_panel_builder` accesses attributes without `getattr`**
   Line 459 in `home_page_support/detail_panel_builder.py` does a direct attribute access
   on `self.page._detail_preview_model_key`. Any future class that acts as a `page` for
   this builder must remember to initialize both `_detail_preview_widget` and
   `_detail_preview_model_key` in its `__init__`. A `getattr(..., None)` default would make
   this contract implicit and prevent a repeat of Bug #2.

### Medium value

5. **`consume_socket` exceptions go to stderr only**
   In `Tools and jaws Library/main.py`, the `consume_socket` callback uses
   `traceback.print_exc()` which goes to stderr — invisible when the app runs under
   `pythonw.exe`. Any IPC-handling exception (like the AttributeError in Bug #2) silently
   drops the selector request. Replace with `logging.exception(...)` so crashes appear in
   `app.log` and are diagnosable without attaching a debugger.

6. **`setup_page_support/library_context.py` still exports `format_lookup` / `format_lookup_list`**
   These were previously used only by the now-deleted Setup Manager detail panel. Check
   whether any other module consumes them; if not, remove them from `library_context.py`
   as well to keep the module focused on context payload building.

### Low value / cosmetic

7. **`QSplitter` in `SetupPage` is now a single-panel splitter**
   After removing the detail panel, the `QSplitter` wrapping the work list has only one
   child and `setChildrenCollapsible(False)` / `setCollapsible(0, False)` are no-ops. The
   splitter itself could be replaced with a plain `QVBoxLayout` container, removing the
   `QSplitter` import from `setup_page.py` entirely.

8. **`_external_refs_timer` in `SetupPage` only tracks mtime changes**
   Now that `_refresh_details()` is gone, `_on_external_references_maybe_changed` updates
   the stored mtime values and returns without doing anything visible. The timer is still
   running every 1.5 s. If there is no other consumer of mtime change events planned,
   the timer and its two `_*_mtime` attributes could be removed.

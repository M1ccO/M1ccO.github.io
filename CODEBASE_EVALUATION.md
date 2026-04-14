# NTX Setup Manager — Codebase Evaluation
*April 2026 | Based on current HEAD state*

---

## Quick Numbers

| | Files | Lines |
|---|---|---|
| Tools and Jaws Library | 132 | 27,125 |
| Setup Manager | 57 | 14,382 |
| Shared | 35 | 5,096 |
| **Total** | **224** | **46,603** |

Tests: 1 test file (`tests/test_shared_regressions.py`, 157 lines) + 1 smoke test. No unit tests.

---

## Overall Verdict

**This is a well-designed, professionally structured desktop application.** The architectural thinking behind it is genuinely good — the platform abstraction layer, the separation of apps via IPC, the support-module pattern, and the phase-driven refactor history all show deliberate and careful design. For a solo or small-team project at this scale, that's impressive.

The weaknesses are not architectural — they are operational. The app would be difficult to hand off to a new developer without a lot of verbal explanation, primarily because there are almost no tests, limited inline reasoning, and no developer guide. The delegation pattern (everything forwarded to support modules) is clean but makes it hard to trace what actually happens when you click a button.

---

## What's Working Well

### 1. Platform Abstraction Layer
`shared/ui/platforms/catalog_page_base.py` (434 lines) is the best code in the project. It defines a clean contract for catalog pages (4 abstract methods, clear signals, stable roles) and `HomePage` and `JawPage` both inherit from it cleanly. If you wanted to add a "Fixtures Library" or "Holder Library" page, you'd have a solid template to follow. This was clearly worth the investment.

### 2. The Support-Module Pattern
Both `home_page_support/` and `jaw_page_support/` have ~17–18 modules each, each with a single clear responsibility (`crud_actions.py`, `filter_coordinator.py`, `detail_visibility.py`, etc.). The orchestrator files (`home_page.py`, `jaw_page.py`) are thin and readable as a result. This is the right approach for a codebase of this size.

### 3. The Selector Dialogs (New)
The recent refactor of the selector UX into standalone `ToolSelectorDialog` / `JawSelectorDialog` (in `ui/selectors/`) is the right call. The old approach — activating a panel mode inside the catalog page — was fragile and hard to reason about. The dialogs are self-contained with their own state, layout, and lifecycle. Much easier to maintain.

### 4. IPC Architecture
Using `QLocalSocket` JSON payloads between Setup Manager and the Library is a reasonable choice for two PySide6 apps that need to pass structured data. It keeps the apps properly decoupled while allowing rich interaction (tool assignment buckets, head/spindle context, etc.).

### 5. Modular Migrations
The split of `tools_migrations.py` / `jaws_migrations.py` (Phase 6) is clean. Each domain owns its own schema evolution and migration functions are named descriptively. This avoids the common "giant SQL blob" migration antipattern.

### 6. Quality Gate Scripts
Having `import_path_checker.py`, `module_boundary_checker.py`, `duplicate_detector.py`, and `run_parity_tests.py` as runnable scripts shows awareness of the maintenance burden. These are practical tools, not just docs.

---

## What Needs Attention

### 1. One File is a Serious Problem: `measurement_editor_dialog.py`
**2,646 lines.** This is the largest file in the project by a large margin — almost twice the size of the next largest. Everything else in the project was refactored into support modules, but this file was not. It almost certainly contains UI layout, state management, validation, and service calls all mixed together. If a bug lives in this file, it is going to be painful to find and fix. This is the highest-priority refactor target.

### 2. Near-Zero Test Coverage
224 Python files. 1 test file with 157 lines. This is the biggest practical risk in the project. The quality gate scripts are good, but they check structure — not behavior. Right now there is nothing stopping a logic change in `filter_coordinator.py` or `work_service.py` from silently producing wrong results. A few targeted tests would pay dividends immediately:
- `tool_service.list_tools()` with search, head, and type filters
- `jaw_service.list_jaws()` with spindle side filtering
- Migration functions on blank + existing schemas
- Selector payload round-trip (encode → decode)

### 3. Silent Failures Throughout
The pattern `except Exception: pass` or `except Exception: return {}` appears across many files — `config.py`, `detail_panel_builder.py`, localization service, migration helpers. In production this means corrupted data, missing translations, and failed icon loads all disappear without a trace. There is no logging infrastructure at all: no `logging.getLogger()`, no debug output, nothing. When something goes wrong in production, diagnosing it is pure guesswork.

### 4. Hard-Coded Colors Everywhere
Colors are scattered as raw hex strings across at least 15 files: `#ffffff`, `#24303c`, `#00C8FF`, `#171a1d`, `#f0f6fc`, etc. The main window has a theme palette system (`THEME_PALETTES`), but most of the UI doesn't use it — it just hard-codes values. If the user ever wants a dark mode, or if a color needs changing, it requires a grep hunt. This is aesthetic but it's also a maintenance time sink.

### 5. The `selector_context.py` is Stranded
`home_page_support/selector_context.py` is 622 lines. It was built to manage the page-level selector panel that is now never activated (because selectors moved to dialogs). Most of this code runs when `set_selector_context()` is called — but that's never called anymore. It's not broken, and the code is still correct, but it's 622 lines of logic running in a page that doesn't need it. Eventually this should either be removed or reduced to the small subset that's actually used (bucket normalization helpers, etc.).

### 6. `setup_page.py` is 994 Lines
The Setup Manager equivalent of the `HomePage` but without the support-module refactor. It's a single file doing filter state, selection logic, detail rendering, and service calls. It's not yet in the bad territory of `measurement_editor_dialog.py` but it's heading that way.

### 7. State Bloat in Page Classes
`HomePage.__init__` initializes 30+ instance variables covering selector state, preview state, filter state, detail panel state, initial load scheduling, and database metadata. These are all logically separate concerns. If you're debugging a preview issue you have to mentally filter past selector and filter state, and vice versa.

---

## Concrete Upgrade List

Ordered by impact-to-effort ratio. Things at the top are either low effort or high impact or both.

---

### Priority 1 — Do These First (Low Effort, High Safety Value)

**Add structured logging**

Every service call, IPC event, and filter evaluation should go somewhere. One line to add to `config.py`:

```python
import logging
logging.basicConfig(
    level=logging.DEBUG if DEV_MODE else logging.WARNING,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(USER_DATA_DIR / 'app.log'), logging.StreamHandler()]
)
```

Then replace `except Exception: pass` with `except Exception: logger.exception("context message")` at the ~12 places where errors are silently swallowed. This alone would have saved hours of debugging on the selector bugs.

**Add 10 targeted tests**

Focus on the parts most likely to break silently:
1. `tool_service.list_tools` — search, head filter, type filter
2. `jaw_service.list_jaws` — spindle side filter, view mode
3. `ToolSelectorDialog._build_initial_buckets` — with and without pre-existing buckets
4. `JawSelectorDialog._send_selector_selection` — deleted jaw does not appear in result
5. Migration idempotence — run `create_or_migrate_tools_schema` twice on same DB, verify no error
6. Localization fallback — missing key returns default, not exception
7. `filter_coordinator.apply_filters` — master filter active/inactive
8. `selector_mime.encode_selector_payload` / `decode_tool_payload` round-trip

None of these require a running Qt app. They are pure logic tests.

**Create a `DEV_MODE` flag and a developer README**

Right now there is no way for a new developer (or a future-you after 6 months) to know how to run the app, what environment it expects, or how to test. A 50-line README covering:
- Python version + `pip install -r requirements.txt`
- How to run each app
- How to run the quality gate
- What `IS_FROZEN` means and when it matters

---

### Priority 2 — Medium Effort, Significant Payoff

**Break up `measurement_editor_dialog.py`**

At 2,646 lines it is an outlier in a project that otherwise has good modularity discipline. Apply the same support-module pattern used for `home_page_support/`:

- `measurement_editor_support/`
  - `layout_builder.py` — widget construction
  - `field_rules.py` — field visibility/validation rules by measurement type
  - `crud_actions.py` — save / delete / duplicate
  - `state_helpers.py` — form ↔ data dict conversion

Target the orchestrator at ≤600 lines.

**Centralize the theme palette**

`MainWindow` already has `THEME_PALETTES` with a proper dict. The problem is nothing else uses it. The fix is one pass through the codebase replacing literal hex colors with calls to a `get_color(key)` helper that reads from the active palette:

```python
# shared/ui/helpers/theme.py
_ACTIVE_PALETTE: dict = {}

def set_palette(palette: dict) -> None:
    _ACTIVE_PALETTE.update(palette)

def color(key: str, fallback: str = '#000000') -> str:
    return _ACTIVE_PALETTE.get(key, fallback)
```

This is also the prerequisite for a dark mode if that's ever wanted.

**Clean up `selector_context.py`**

Now that the selectors run as dialogs and pages are never put in selector mode, `home_page_support/selector_context.py` can be reduced significantly. The parts still needed are:
- `normalize_selector_tool()` — used by `selected_tools_for_setup_assignment()`
- `selector_tool_key()`, `selector_target_key()` — bucket helpers
- `tool_matches_selector_spindle()` — catalog filter

Everything else (800 lines of panel show/hide, assignment list rebuild, button state management) is now dead code. Removing it shrinks the file by ~75% and removes a maintenance hazard.

**Reduce state bloat in `HomePage` and `JawPage`**

Extract logically separate groups of instance variables into small state objects:

```python
# Instead of 30 vars on self:
self._preview = PreviewState()          # _detached_preview_*, _inline_*
self._filter = FilterState()            # _external_head_filter, _head_filter_value, _master_filter_*
self._selector = SelectorPageState()    # _selector_active, _selector_head, etc.
```

This doesn't change any behavior but makes the classes far easier to reason about.

---

### Priority 3 — Larger Effort, Worth Planning

**Apply the support-module pattern to `setup_page.py`**

At 994 lines, `setup_page.py` is the Setup Manager equivalent of what `home_page.py` looked like before Phase 4. The same refactor applies: extract a `setup_page_support/` package with modules for filter coordination, CRUD actions, detail visibility, selection helpers. The orchestrator should be under 400 lines.

**High-DPI and scaling audit**

The catalog delegates hard-code pixel values (`ICON_SIZE = 40`, margin values, font sizes in `pt`). On 4K displays or displays with 150% scaling these look wrong. Qt provides `QScreen.devicePixelRatio()` and `fontMetrics()` to scale dynamically. This is particularly visible in the mini assignment cards and selector panels.

**Async catalog loading**

`refresh_catalog()` runs synchronously on the main thread. For small catalogs (< 200 items) this is fine. For large catalogs (500+ tools with STL paths, component data) it can cause a visible freeze on the UI thread. The pattern:

```python
# In a QThread or asyncio bridge:
tools = await self.tool_service.list_tools_async(...)
self._populate_model.emit(tools)  # back on main thread
```

The deferred load pattern (`_schedule_initial_load`) is already in place — extending it to fully async population would complete the picture.

**Consider a proper dark/light theme toggle**

The color centralization (Priority 2) is a prerequisite. Once colors come from a palette, toggling themes is a single `set_palette()` call. Given the CNC workshop context (often poorly lit, glare from machines), dark mode is a practical feature, not just cosmetic.

---

## Things NOT Worth Doing

**Don't replace PySide6 with something else.** PySide6 is the right choice for this kind of desktop app. Electron would be a massive regression.

**Don't add a database ORM.** SQLite with direct SQL is fine here. The migrations pattern works. An ORM would add complexity without solving a real problem in this codebase.

**Don't split into microservices.** The IPC boundary between the two apps is already the right level of separation. Breaking things down further would add latency and operational complexity for no benefit.

**Don't rewrite `catalog_page_base.py`.** It's well-designed and stable. Leave it alone.

---

## File-by-File Summary (Largest Files)

| File | Lines | State |
|---|---|---|
| `measurement_editor_dialog.py` | 2,646 | Needs breaking up — only outlier in otherwise modular codebase |
| `main_window.py` (Library) | 1,332 | Large but organized; selector session code is clean |
| `print_service.py` | 1,196 | Print/PDF generation; size is expected for this domain |
| `setup_page.py` | 994 | Refactor candidate — hasn't had the support-module treatment yet |
| `tool_editor_dialog.py` | 985 | Acceptable; editor with many field types |
| `drawing_page.py` | 974 | PDF/drawing management; complex domain |
| `home_page.py` | 676 | Good — thin orchestrator after Phase 4 |
| `jaw_page.py` | 567 | Good — same |
| `tool_catalog_delegate.py` | 556 | All painting code; acceptable for a custom delegate |
| `detail_panel_builder.py` (tools) | 785 | Worth reviewing; 785 lines for a panel builder is borderline |
| `work_editor_dialog.py` | 611 | Not yet refactored but not a crisis |
| `selector_context.py` | 622 | Mostly dead code now — reduce to ~150 lines |
| `tool_selector_state.py` | 525 | New dialog state; reasonable for what it manages |

---

## Summary

The codebase is in better shape than most projects of this size and complexity. The architecture is thought through, the phase-driven refactor was executed well, and the separation between apps is clean. The platform layer in `shared/ui/platforms/` is a genuine asset.

The gaps are almost entirely in operational safety: no logging means silent failures, no tests means regressions go unnoticed, and a few files that escaped the refactor (especially `measurement_editor_dialog.py`) are time bombs. Fixing those three things — logging, a handful of targeted tests, and breaking up the measurement editor — would meaningfully reduce the maintenance burden and make the codebase safer to work in.

Everything else on the list is an improvement, not a fix.

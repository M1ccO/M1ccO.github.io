# NTX Setup Manager — Codebase Evaluation
*April 2026 | Based on current HEAD state*

---

## Session Work Log

### April 2026 — Structured Logging

**Goal:** Replace silent `except Exception: pass` failures with observable log output. Ensure both apps write to a per-user `app.log` file in dev and production.

**Files changed:**

| File | Change |
|---|---|
| `Setup Manager/config.py` | Added `_configure_logging()`. `DEBUG` level in `DEV_MODE`, `WARNING` in production. Writes to both `stderr` and `USER_DATA_DIR/app.log` (file handler wrapped in `try/except OSError` so a read-only filesystem doesn't crash startup). |
| `Tools and jaws Library/config.py` | Same `_configure_logging()` implementation. Both apps now produce identical log format: `%(asctime)s %(name)s %(levelname)s %(message)s`. |
| `shared/services/localization_service.py` | Added `logger = logging.getLogger(__name__)`. Replaced silent catalog-load failures and format-string errors with `logger.warning(..., exc_info=True)` and `logger.debug(...)`. Previously these swallowed corrupted JSON and wrong format kwargs without a trace. |
| `Tools and jaws Library/ui/main_window.py` | Added `logger = logging.getLogger(__name__)`. Selector dialog open/close path now emits `logger.debug(...)`. IPC send failures now use `logger.exception(...)` instead of being silently dropped. |

**What's still open:** Most `except Exception: pass` blocks in service files, detail panel builders, and migration helpers are still silent. The logging infrastructure is in place — the remaining work is a sweep through those call sites replacing bare `pass` with `logger.exception("context")`.

---

### April 2026 — Targeted Unit Tests

**Goal:** Add the targeted test suite recommended in Priority 1 — pure logic tests that require no UI and run without a display server.

**Files added:**

| File | Lines | What it covers |
|---|---|---|
| `tests/test_priority1_targeted.py` | 447 | 27 test cases across 6 test classes (see below) |

**Test classes:**

| Class | Tests | What it verifies |
|---|---|---|
| `TestToolServiceListTools` | 9 | `list_tools()` — all, search by description, search by ID, type filter, head filter HEAD1/HEAD2, combined search+type, empty search, no-match |
| `TestJawServiceListJaws` | 5 | `list_jaws()` — view_mode all/main/sub (including "Both" spindle side), search, type filter |
| `TestMigrationIdempotence` | 2 | `create_or_migrate_tools_schema` and `create_or_migrate_jaws_schema` run twice on same in-memory DB without error |
| `TestLocalizationService` | 5 | Missing key returns default, missing key without default returns key, format failure returns raw template (no raise), corrupted JSON catalog does not raise, language fallback to English |
| `TestSelectorMime` | 4 | Tool encode/decode round-trip, jaw encode/decode round-trip, empty `QMimeData` returns `[]`, corrupt MIME data returns `[]` |
| `TestFilterCoordinator` | 3 | `apply_filters()` with master filter inactive (returns all), active with partial set (restricts correctly), active with empty set (returns nothing) |

**Test infrastructure decisions:**
- `QT_QPA_PLATFORM=offscreen` set before any PySide6 import — tests run headless in CI/terminal without a display
- `QApplication` singleton created once before Qt imports that trigger widget registration
- Services instantiated via `__new__` + direct `.db` assignment to bypass `__init__` side effects (file I/O, seeding)
- All DB fixtures use `sqlite3.connect(":memory:")` — no temp files, no cleanup needed for most tests
- `LocalizationService` tests use `tempfile.TemporaryDirectory` with real JSON files to exercise the full load path

---

### April 2026 — Theme Palette Unification

**Goal:** Make both apps (Setup Manager and Tools/Jaws Library) fully theme-driven — no hardcoded accent or structural colors anywhere in the runtime layer.

**Files changed:**

| File | Change |
|---|---|
| `shared/ui/main_window_helpers.py` | Created. Unified `THEME_PALETTES`, `get_active_theme_palette`, `current_window_rect`, `fade_out_and`, `fade_in`, `is_interactive_widget_click`. Both apps now import from here. |
| `shared/ui/main_window_helpers.py` | Expanded palette to 8 keys: added `accent_light` (top gradient stop) and `icon_hover_bg` (distinct icon button hover tint). |
| `Tools and jaws Library/styles/modules/10-base.qss` | Changed `QMainWindow, QWidget { background-color }` to `QMainWindow, QWidget#appRoot`. Prevents the broad QWidget selector from overriding QPushButton/QComboBox gradients at equal specificity. Now matches Setup Manager's pattern. |
| `Tools and jaws Library/styles/modules/10-base.qss` | Added `QFrame[launchCard="true"]` transparent styles so the nav-rail footer inherits the container background correctly. |
| `Tools and jaws Library/ui/tool_catalog_delegate.py` | Updated `apply_delegate_theme` to accept an optional `accent` parameter. Now also updates `CLR_CARD_SELECTED_BORDER` from the palette, making delegate-painted selection borders theme-driven. |
| `Tools and jaws Library/ui/main_window.py` | Wired `apply_delegate_theme(palette['info_box_bg'], palette['accent'])` in `_apply_style`. Added explicit `viewport().update()` on all 5 catalog list views after `setStyleSheet` to force repaint of delegate-painted items. |
| `Tools and jaws Library/ui/main_window.py` | Completed `_build_ui_preference_overrides` with full palette coverage: structural backgrounds (narrow selectors only), surface/catalog, detail panel, input focus rings, card selection borders, sidebar nav gradient, icon hover tints, and primary action button gradients. |
| `Setup Manager/ui/main_window.py` | Completed `_build_ui_preference_overrides` with: window/surface/info_box backgrounds, input focus rings, card selection borders for `workCard`/`toolListCard`, and a specificity-matched rule for `miniAssignmentCard` (static rule uses `QDialog[workEditorDialog] QFrame[miniAssignmentCard]` at spec 0,3,2 — runtime must match that ancestor to win at equal spec). Primary button gradient at spec-1 (`QPushButton`) plus matching spec-21 overrides for `[navButton][active]` and `[panelActionButton][primaryAction]` which the broad rule cannot reach. |

**Key technical decisions made:**

- **Never use broad `QWidget` in runtime overrides.** `QWidget` at spec 1 comes last and overrides QPushButton/QComboBox gradients (also spec 1). Only use `QWidget#appRoot`, `QFrame#navFrame`, `QFrame#filterFrame`, etc.
- **`background-color:` not `background:` for gradient overrides.** Qt QSS treats these as separate properties; static rules use `background-color: qlineargradient(...)` so runtime must match the same property.
- **Specificity matching for parent-scoped static rules.** When a static rule uses a parent context selector (e.g. `QDialog[workEditorDialog] QFrame[...]`), the runtime override must include the same ancestor prefix to achieve equal specificity — then last-defined wins.
- **Delegate globals need explicit viewport repaint.** `setStyleSheet` on the main window does not reliably repaint delegate-painted QListView viewports. Call `list_view.viewport().update()` explicitly after updating delegate globals.

---

## Quick Numbers

| | Files | Lines |
|---|---|---|
| Tools and Jaws Library | 132 | 27,125 |
| Setup Manager | 57 | 14,382 |
| Shared | 35 | 5,096 |
| **Total** | **224** | **46,603** |

Tests: 2 test files — `tests/test_shared_regressions.py` (157 lines) + `tests/test_priority1_targeted.py` (447 lines, 27 test cases). 604 lines total.

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

### 2. Test Coverage — Priority 1 Suite Complete, Broader Coverage Still Needed
**Progress (April 2026):** `tests/test_priority1_targeted.py` added 27 test cases covering `ToolService.list_tools`, `JawService.list_jaws`, migration idempotence, localization resilience, `selector_mime` round-trips, and `filter_coordinator` master-filter logic. Tests run headless (offscreen Qt platform) with no external dependencies.

**Still open:** No tests for `work_service.py`, `print_service.py`, selector dialog state (`ToolSelectorDialog._build_initial_buckets`, `JawSelectorDialog._send_selector_selection`), detail panel builders, or any Setup Manager-side logic. The service and filter layers now have a foundation — the next priority is covering the business logic in `work_service.py` (highest risk: setups/assignments are the core data structure).

### 3. Silent Failures — Infrastructure Added, Sweep Not Complete
**Progress (April 2026):** Both `config.py` files now call `_configure_logging()` at startup, writing to `stderr` and `USER_DATA_DIR/app.log` at the right level (`DEBUG` in dev, `WARNING` in production). `localization_service.py` and `main_window.py` (Library) now use `logger.getLogger(__name__)` and emit structured warnings/debug messages instead of dropping errors silently.

**Still open:** The bulk of `except Exception: pass` and `except Exception: return {}` sites in service files, detail panel builders, icon loaders, and migration helpers still swallow failures silently. The infrastructure is now in place — the remaining work is a sweep through those ~12 sites replacing bare `pass` with `logger.exception("context message")`.

### 4. Hard-Coded Colors — Runtime Layer Now Solved, Static QSS Remains
**Progress (April 2026):** All structural, accent, surface, and selection colors in both apps' runtime override layers are now palette-driven via `THEME_PALETTES` in `shared/ui/main_window_helpers.py`. The `classic` and `graphite` themes fully control: window/surface/info-box backgrounds, primary button gradients, sidebar nav checked/hover states, icon-only button hover tints, input focus rings, and card selection borders (including delegate-painted items in the Library catalog).

**Still open:** Static QSS modules (`10-base.qss`, `60-catalog.qss`, etc.) still use hardcoded hex strings for non-themed values — neutral grays, text colors, white surfaces. These don't change between themes so they are lower priority, but they remain scattered. If a dark mode is ever wanted, these files will need a second pass. The `#00C8FF` cyan in `50-data-views.qss` (miniAssignmentCard selected state) is now overridden at runtime by the palette accent, but the dead hardcoded value still sits in the static file.

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

**Add structured logging** *(Infrastructure complete — April 2026)*

Both `config.py` files now configure logging at startup. `localization_service.py` and Library `main_window.py` use named loggers. Remaining: sweep through the ~12 `except Exception: pass` sites in service and builder files and replace with `logger.exception("context message")`.

**Add targeted tests** *(Priority 1 suite complete — April 2026)*

`tests/test_priority1_targeted.py` covers all 6 originally listed areas with 27 test cases. Tests run headless via `QT_QPA_PLATFORM=offscreen`. Remaining: `work_service.py` business logic, selector dialog state, Setup Manager-specific services.

**Create a `DEV_MODE` flag and a developer README** *(Still open)*

`DEV_MODE` is now used by both `config.py` files for log levels. The README is still missing. A 50-line guide covering:
- Python version + `pip install -r requirements.txt`
- How to run each app
- How to run the quality gate (`run_parity_tests.py`, etc.)
- How to run the test suite (`python -m pytest tests/`)
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

**Centralize the theme palette** *(Runtime layer complete — April 2026)*

`THEME_PALETTES` is now shared in `shared/ui/main_window_helpers.py` and fully consumed by both apps' `_build_ui_preference_overrides`. All runtime accent, background, and selection colors are palette-driven. The 8-key palette (`window_bg`, `surface_bg`, `info_box_bg`, `accent_light`, `accent`, `accent_hover`, `accent_pressed`, `icon_hover_bg`) covers all interactive surfaces.

**Remaining work:** Static QSS files still have hardcoded values for non-themed neutrals. The `get_color()` global helper approach (below) is still the right path if dark mode is ever wanted — it would let static QSS reference palette values too:

```python
# shared/ui/helpers/theme.py
_ACTIVE_PALETTE: dict = {}

def set_palette(palette: dict) -> None:
    _ACTIVE_PALETTE.update(palette)

def color(key: str, fallback: str = '#000000') -> str:
    return _ACTIVE_PALETTE.get(key, fallback)
```

This is the prerequisite for a full dark mode — the runtime layer is already there, only the static QSS pass remains.

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
| `main_window.py` (Library) | ~1,420 | Grown slightly with theme palette wiring; still organized |
| `print_service.py` | 1,196 | Print/PDF generation; size is expected for this domain |
| `setup_page.py` | 994 | Refactor candidate — hasn't had the support-module treatment yet |
| `tool_editor_dialog.py` | 985 | Acceptable; editor with many field types |
| `drawing_page.py` | 974 | PDF/drawing management; complex domain |
| `home_page.py` | 676 | Good — thin orchestrator after Phase 4 |
| `jaw_page.py` | 567 | Good — same |
| `tool_catalog_delegate.py` | 556 | All painting code; acceptable; `apply_delegate_theme` now theme-aware |
| `detail_panel_builder.py` (tools) | 785 | Worth reviewing; 785 lines for a panel builder is borderline |
| `work_editor_dialog.py` | 611 | Not yet refactored but not a crisis |
| `selector_context.py` | 622 | Mostly dead code now — reduce to ~150 lines |
| `tool_selector_state.py` | 525 | New dialog state; reasonable for what it manages |
| `shared/ui/main_window_helpers.py` | 122 | New shared module — theme palettes, fade helpers, geometry, widget check |

---

## Summary

The codebase is in better shape than most projects of this size and complexity. The architecture is thought through, the phase-driven refactor was executed well, and the separation between apps is clean. The platform layer in `shared/ui/platforms/` is a genuine asset.

The gaps are almost entirely in operational safety: no logging means silent failures, no tests means regressions go unnoticed, and a few files that escaped the refactor (especially `measurement_editor_dialog.py`) are time bombs. Fixing those three things — logging, a handful of targeted tests, and breaking up the measurement editor — would meaningfully reduce the maintenance burden and make the codebase safer to work in.

Everything else on the list is an improvement, not a fix.

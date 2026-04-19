# Style Ownership Map

This document records the verified style owners that were traced before the
shared theme/compiler refactor was connected. It exists so future changes do
not remove a color path based on assumption.

## Priority Screens

| Screen / Surface | Visible Role | Current Owner(s) Before Shared Compiler | Final Semantic Role |
|---|---|---|---|
| Setup Manager main window shell | Page background gray | `Setup Manager/styles/modules/10-base.qss`, `Setup Manager/ui/main_window.py:_build_ui_preference_overrides` | `page_bg` |
| Setup Manager work list viewport | Graphite/blue-gray row area | `Setup Manager/styles/modules/60-catalog.qss`, runtime override builder | `row_area_bg` |
| Setup Manager work cards | White cards + selected border | `Setup Manager/styles/modules/60-catalog.qss`, `Setup Manager/ui/setup_catalog_delegate.py` | `card_bg`, `accent`, `border_strong` |
| Tool Library shell | Page background gray | `Tools and jaws Library/styles/modules/10-base.qss`, `Tools and jaws Library/ui/main_window.py:_build_ui_preference_overrides` | `page_bg` |
| Tool/Jaw catalog viewport | Graphite/blue-gray row area | `Tools and jaws Library/styles/modules/60-catalog.qss`, runtime override builder | `row_area_bg` |
| Tool catalog cards | White cards + selected border | `Tools and jaws Library/ui/tool_catalog_delegate.py`, `Tools and jaws Library/styles/modules/60-catalog.qss` | `card_bg`, `accent`, `border_strong` |
| Standalone selectors outer dialog | Page-family background | `Tools and jaws Library/ui/selectors/common.py` via `paintEvent`, palette/autofill, local `setStyleSheet` | `page_bg` |
| Selector inner assignment/list hosts | Page-family row area / card mix | selector layouts, selector QSS modules, local palette/autofill | `row_area_bg`, `card_bg` |
| Selector toolbars / splitters | Host background and divider strips | `ui/selectors/tool_selector_layout.py`, `ui/selectors/jaw_selector_layout.py`, local palette/setStyleSheet fallbacks | `page_bg`, `border` |
| Work Editor dialog | White editor shell | host stylesheet inheritance, fallback disk stylesheet load, app QSS modules | `editor_bg` |
| Tool/Jaw editors | White editor shell | app QSS modules, shared editor helpers, local widget styles | `editor_bg` |
| Editor sections | Light blue section group with title on border | `shared/ui/helpers/editor_helpers.py`, `Tools and jaws Library/ui/measurement_editor/forms/shared_sections.py`, app QSS group-box rules | `section_bg`, `editor_bg`, `border` |
| Measurement Editor dialog | White editor shell + local overlays | `Tools and jaws Library/ui/measurement_editor_dialog.py` inline styles, app QSS, runtime app stylesheet | `editor_bg`, `section_bg`, `accent` |
| Preferences dialogs | White editor-style dialog | app QSS, `shared/ui/preferences_dialog_base.py`, some local checkbox/button styles | `editor_bg`, `border` |
| Secondary editor-style dialogs | White editor shell + white text surfaces | `Setup Manager/ui/main_window_support/compatibility_dialog.py`, `ui/setup_page_support/log_entry_dialog.py`, helper-local inline styles | `editor_bg`, `card_bg`, `border` |

## High-Risk Ownership Sources

- App-local QSS modules under both `styles/modules/*.qss`
- Runtime override builders in:
  - `Setup Manager/ui/main_window.py`
  - `Tools and jaws Library/ui/main_window.py`
- Delegate paint code in:
  - `Setup Manager/ui/setup_catalog_delegate.py`
  - `Tools and jaws Library/ui/tool_catalog_delegate.py`
- Inline widget styles in shared/common helpers:
  - `shared/ui/helpers/editor_helpers.py`
  - `Tools and jaws Library/ui/measurement_editor/forms/shared_sections.py`
  - `Tools and jaws Library/ui/selectors/common.py`
  - `Tools and jaws Library/ui/measurement_editor_dialog.py`
- Palette / background workarounds in selector/dialog hosts:
  - `Tools and jaws Library/ui/selectors/common.py`
  - `Tools and jaws Library/ui/main_window.py`
  - `Setup Manager/ui/work_editor_dialog.py`

## Migration Rules

- A legacy color owner may remain temporarily if it is still needed for parity.
- No legacy owner should be deleted until the shared compiler/property path has
  been verified to produce the same visible result on the target surface.
- Transparent is not treated as a color source. It is only valid when the
  parent surface is known and intentional.

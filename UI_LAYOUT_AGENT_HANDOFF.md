# UI Layout Agent Handoff

This file is the authoritative reference for AI agents continuing layout work in this repo.
Read it fully before touching any layout code.

---

## Scope

This document covers:
- Card frame size and position (top/left insets, right/bottom anchoring)
- Topbar (filter toolbar) alignment relative to card frame
- Left nav rail structure, title, nav buttons, launch card
- Bottom action bar margins
- Cross-app visual parity between Setup Manager and Libraries

Not covered here: colors, QSS theme tokens, editor section behavior, delegate card geometry.

---

## Current Visual State (as of 2026-04-19)

Both apps are visually aligned. Key confirmed values:

| Dimension | Setup Manager | Tool Library | Jaw Library |
|---|---|---|---|
| Window root margins | (0,0,12,0) | (0,0,12,0) | same |
| Nav rail width | 210px | 210px | same |
| Rail layout margins | (12,14,12,14) | (12,14,12,14) | same |
| Rail layout spacing | 8px | 8px | same |
| Rail title font | 20pt bold, no wrap | 20pt bold, no wrap | same |
| Rail title fixed height | — | 36px | same |
| Card frame host (list_host) margins | (56,8,0,0) | (56,8,0,0) | (56,8,0,0) |
| Topbar host margins | addSpacing(30) before frame | (0,30,0,4) | (0,30,0,4) |
| Filter frame left margin | 56px (controls layout) | 56px | 56px |
| SM topbar controls margins | (56,6,8,6) | n/a | n/a |
| Bottom bar margins | (10,10,10,6) | (10,10,10,6) | (10,10,10,6) |
| Launch card margins | (12,12,12,12) | (12,12,12,12) | same |
| QStatusBar | yes (with DB info) | yes (no content) | same |

---

## Non-Negotiable Rules

### 1. Card frame shrinks from TOP and LEFT only

Right edge = 0 (never add right inset to list_host).
Bottom edge = 0 (never add bottom inset to list_host).
Increase top/left margins to make frame visually smaller.

### 2. Do not change card geometry

Never touch for frame-size requests:
- `ROW_HEIGHT`, `ROW_HEIGHT_COMPACT`
- `CARD_MARGIN_H`, `CARD_MARGIN_V`
- list internal padding

### 3. Detail panel left inset stays 0

`detail_layout.setContentsMargins(0, 8, 0, 0)` — horizontal must stay 0.
Changing left creates a visible gap between list frame and detail panel.

### 4. No inline setStyleSheet blocks for layout fixes

Use property-driven QSS. Don't add random `widget.setStyleSheet(...)` blocks to solve spacing.

### 5. Do not touch section-shell (QGroupBox[editorSection]) behavior

### 6. Topbar filter frame left margin: page topbars = 56, selector dialogs = 56

`build_filter_frame(left_margin=56)` for all page topbars — aligns icons with card frame left edge.
Selector layout callers also keep default `left_margin=56`.
SM topbar: `controls.setContentsMargins(56, 6, 8, 6)`.
Do not change to 8 — icons would misalign from card edge.

---

## Ownership Map

### Setup Manager card frame
**File:** `Setup Manager/ui/setup_page.py`
**Owner:** `list_shell_container_layout.setContentsMargins(56, 40, 0, 0)`
Do NOT use `setup_catalog_delegate.py` for frame-only changes.

### Tool Library card frame
**File:** `Tools and jaws Library/ui/home_page_support/page_builders.py`
**Owner:** `list_host_layout.setContentsMargins(56, 40, 0, 0)` in `build_catalog_list_card`
Topbar alignment: `topbar_host_layout.setContentsMargins(0, 0, 0, 4)` in `build_tool_page_layout`

### Jaw Library card frame
**File:** `Tools and jaws Library/ui/jaw_page_support/page_builders.py`
**Owner:** `list_host_layout.setContentsMargins(56, 40, 0, 0)` in `_build_catalog_list_card`
Topbar alignment: `topbar_host_layout.setContentsMargins(0, 0, 0, 4)` in `build_jaw_page_layout`

### Detail container vertical alignment
**Files:** both `page_builders.py` above
`detail_layout.setContentsMargins(0, 8, 0, 0)` — top=8 matches list_host top reduced by spacing.

### Nav rail (Library)
**File:** `Tools and jaws Library/ui/main_window.py` — `_build_ui`
- Rail: `QFrame`, `navRail=True`, `setFixedWidth(210)`
- Layout: `(12, 14, 12, 14)` margins, spacing=8
- Title: `rail_title`, 20pt bold, `setWordWrap(False)`, `setFixedHeight(36)`
- HEAD nav buttons: `navButton=True`, `active=True/False` property drives QSS highlight
- Launch card: `launchCard=True`, margins `(12,12,12,12)`, spacing=8
  - `launch_title` label with `sectionTitle` property
  - `launch_body` label with `navHint` property, `setMaximumHeight(48)`
  - `module_toggle_btn` — single toggle button (LEUAT ↔ TYÖKALUT)
  - `back_to_setup_btn` — 38×38, `topBarIconButton`, `Qt.AlignHCenter`
- Hidden `tool_head_filter_combo` (RailHeadToggleButton) kept for page API compat

### Nav rail (Setup Manager)
**File:** `Setup Manager/ui/main_window.py` — `_build_ui`
- Rail: `QFrame`, `navRail=True`, `setFixedWidth(210)`
- Layout: `(12, 14, 12, 14)` margins, spacing=8
- Title: `rail_title_label`, 20pt bold, `setWordWrap(False)`
- Nav buttons: ASETUKSET / LOKIKIRJA with `navButton=True`
- Launch card: same structure, 2 launch buttons + `preferences_btn` at bottom centered

### Filter frame left margin
**File:** `shared/ui/helpers/topbar_common.py`
`build_filter_frame(left_margin=8)` — page topbars pass 8.
Selector layouts keep default 56.

### Bottom bar margins
**Files:** `home_page_support/page_builders.py` `build_bottom_bars`, `jaw_page_support/bottom_bars_builder.py`
`actions.setContentsMargins(10, 10, 10, 6)` — matches Setup Manager.

### QStatusBar
Library has a no-content status bar added in `_build_ui` after `root.addWidget(self.stack, 1)`.
Structural parity with SM — keeps bottom button gap identical.

---

## Shared Helpers — Do Not Edit for Frame Tasks

- `shared/ui/helpers/page_scaffold_common.py`
- `shared/ui/platforms/catalog_delegate.py`
- `Tools and jaws Library/ui/tool_catalog_delegate.py`
- `Tools and jaws Library/ui/jaw_catalog_delegate.py`
- `Setup Manager/ui/setup_catalog_delegate.py`

Only touch these if the user explicitly asks to change card size, list item spacing, or delegate rendering.

---

## How to Make Frame Smaller

1. In all three owner files increase top and left margins only:
   - `Setup Manager/ui/setup_page.py` → `list_shell_container_layout.setContentsMargins(LEFT, TOP, 0, 0)`
   - `home_page_support/page_builders.py` → `list_host_layout.setContentsMargins(LEFT, TOP, 0, 0)` (currently LEFT=56, TOP=8)
   - `jaw_page_support/page_builders.py` → `list_host_layout.setContentsMargins(LEFT, TOP, 0, 0)` (currently LEFT=56, TOP=8)
2. Right and bottom stay 0.
3. Do not touch delegate card geometry.

---

## QSS Property Map (Library-specific additions)

| Property | Widget | File |
|---|---|---|
| `navRail=True` | QFrame rail | `Tools and jaws Library/styles/modules/10-base.qss` |
| `navButton=True` | QPushButton | `Tools and jaws Library/styles/modules/40-buttons.qss` |
| `navButton=True, active=True` | QPushButton | `Tools and jaws Library/styles/modules/40-buttons.qss` |
| `sidebarLaunchButton=True` | QPushButton | `Tools and jaws Library/styles/modules/40-buttons.qss` |
| `launchCard=True` | QFrame | `Tools and jaws Library/styles/modules/10-base.qss` |

---

## Minimum Verification After Layout Edits

```bash
python -m py_compile "Setup Manager/ui/setup_page.py"
python -m py_compile "Tools and jaws Library/ui/home_page_support/page_builders.py"
python -m py_compile "Tools and jaws Library/ui/jaw_page_support/page_builders.py"
python -m py_compile "Tools and jaws Library/ui/main_window.py"
python -m unittest discover -s tests -p test_shared_theme_contract.py
python -m unittest discover -s tests -p test_selector_embedded_mode.py
```

If shared helpers touched: also run `python scripts/run_quality_gate.py`.

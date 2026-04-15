# Machine Profile Architecture

## Overview

Machine profiles are now an active runtime contract across both applications, not just metadata.
The selected profile controls machine family (lathe or machining center), UI terminology, visible controls, selector behavior, and work payload shape.

Current implementation status:
- Lathe profiles: implemented and in production paths.
- Machining center profiles: implemented with dedicated fixtures and operation-based flow.

## Where the Active Profile Comes From

### Authoritative source (database-bound)

The canonical profile key is stored in Setup Manager database config:

| Table | Key | Value example |
|---|---|---|
| app_config | machine_profile_key | ntx_2sp_2h |

This is machine-instance configuration, not a casual UI preference.

### Shared mirror for cross-app UI coordination

Setup Manager mirrors the active key into shared preferences so Tools and jaws Library can adapt without direct imports:

```
.runtime/shared_ui_preferences.json -> machine_profile_key
```

## Bootstrap and Change Flow

Startup flow:
1. Database migrations ensure app_config and machine_profile_key exist.
2. If key is empty on a fresh DB, Machine Setup Wizard is shown.
3. Chosen key is written to DB through WorkService.
4. Key is mirrored to shared preferences.
5. Both apps render according to that key.

Profile change flow:
1. Preferences -> Configure Machine opens Machine Setup Wizard.
2. Accept writes new key to DB and shared preferences.
3. Restart notice is shown.

## Implemented Profile Set

As implemented in Setup Manager profile registry:

| Key | Name | Family | Notes |
|---|---|---|---|
| ntx_2sp_2h | NTX 2 Spindles / 2 Turret Heads | lathe | legacy default |
| lathe_2sp_1mill | Lathe 2 Spindles / 1 Milling Head | lathe | milling head, dual spindle |
| lathe_2sp_3h | Lathe 2 Spindles / 3 Turret Heads | lathe | includes HEAD3 |
| lathe_1sp_1h | Lathe 1 Spindle / 1 Turret Head | lathe | OP terminology |
| lathe_1sp_1mill | Lathe 1 Spindle / 1 Milling Head | lathe | OP terminology |
| machining_center_3ax | Machining Center - 3 Axis | machining_center | XYZ operations + fixtures |
| machining_center_4ax | Machining Center - 4 Axis | machining_center | XYZ + rotary axis |
| machining_center_5ax | Machining Center - 5 Axis | machining_center | XYZ + two rotary axes |

## Runtime Model in Use

Core dataclasses in machine_profiles.py:
- MachineHeadProfile
- MachineSpindleProfile
- MachineProfile

Fields actively used by current UI logic:
- machine_type
- heads and head capability flags
- spindles (lathe paths)
- use_op_terminology
- zero_axes
- supports_sub_pickup
- supports_print_pots
- supports_zero_xy_toggle
- machining center axis_count and axis letters

## What Is Profile-Driven Today

### Setup Manager

- Work Editor switches between lathe and machining-center layouts based on machine_type.
- Machining center Zeros tab uses operation cards (OP10, OP20, ...), per-operation work offset, sub-program, axis inputs, and fixtures selection.
- Machining center Tool IDs uses operation-targeted assignments (active OP selector + per-OP tool payload).
- Selector bridge supports tool, jaw, and fixture selectors with profile-aware behavior.
- Work payload persists machining center operation data via mc_operation_count and mc_operations.

### Tools and jaws Library

- Main window resolves profile key into lightweight machine context and detects machining-center mode.
- In machining-center mode, module routing and labels switch to Fixtures instead of Jaws in Setup handoff scenarios.
- Fixtures page is first-class and can be targeted by selector session payloads.
- Tool Selector now hides lathe-only head/spindle toggle controls when session is machining-center.

## Data and Migration State

The schema includes machining-center work columns:
- mc_operation_count (INTEGER)
- mc_operations (TEXT JSON list)

Migration behavior remains additive and backward-compatible:
- Existing DBs are backfilled with ntx_2sp_2h when no profile key exists and works are present.
- Fresh DBs can remain empty-key until wizard selection.

## Current Cross-App Boundary

Important implementation detail:
- Setup Manager uses full MachineProfile objects from machine_profiles.py.
- Tools and jaws Library currently uses a lightweight resolved mapping from key (machine_type + normalized head/spindle placeholders) rather than importing full Setup Manager registry.

This separation is intentional for process isolation and loose coupling.

## Known Remaining Gaps

These are the practical gaps relative to the current architecture:
1. Tools and jaws Library profile resolution is simplified (not full capability parity with Setup Manager profile flags).
2. Some head-capability enforcement paths (for example rotating-tool restrictions by turret capability) are still partial in editor validation UX.
3. Documentation and comments in a few source files still contain old "future" wording even though machining-center flows are now active.

## Storage Contract

Stable persisted identifiers that should not be repurposed:

| Domain | Stored values |
|---|---|
| tools.tool_head | HEAD1, HEAD2, HEAD3 |
| tools.spindle_orientation | main, sub |
| jaws.spindle_side | Main spindle, Sub spindle, Both |
| works head payload fields | head1_*, head2_*, head3_* |
| works machining-center payload | mc_operation_count, mc_operations |

Display labels may change per profile and language, but persisted keys remain stable.

# Work Editor Embedded Selector Rework Plan

## 1. Scope and Objective

This plan defines a full rework to run selector workflows inside Setup Manager Work Editor (embedded mode) instead of launching external selector dialogs in Tool Library.

Target behavior:
1. User opens selector from Work Editor.
2. Work Editor switches to selector-only mode.
3. Work Editor grows wider to fit selector UI.
4. User presses DONE or CANCEL.
5. Work Editor returns to normal mode and previous geometry.

Primary goal:
- Remove cross-process selector orchestration for Work Editor flows.

Secondary goals:
- Preserve visual style parity (buttons, cards, headers, filters, list delegates).
- Preserve selector payload semantics and assignment rules.
- Keep migration low risk with feature flag and compatibility wrappers.

Out of scope (this phase):
- Full merge of Setup Manager and Tool Library processes.
- Large redesign of editor form layout and styling.

---

## 2. Baseline Architecture (Current State)

### 2.1 Setup Manager selector orchestration

Main integration points:
- Setup Manager/ui/work_editor_dialog.py
- Setup Manager/ui/work_editor_support/bridge.py
- Setup Manager/ui/work_editor_support/bridge_actions.py
- Setup Manager/ui/work_editor_support/selector_flow.py
- Setup Manager/ui/work_editor_support/selector_adapter.py
- Setup Manager/ui/work_editor_support/selectors.py

Current flow summary:
1. Work Editor opens selector via bridge API.
2. Bridge opens callback server and launches/sends request to Tool Library process.
3. Tool Library opens standalone selector dialog.
4. Dialog submit sends payload back through IPC callback.
5. Setup Manager applies result to ordered lists and jaw selectors.

### 2.2 Tool Library selector implementations

Current selector dialogs:
- Tools and jaws Library/ui/selectors/tool_selector_dialog.py
- Tools and jaws Library/ui/selectors/jaw_selector_dialog.py
- Tools and jaws Library/ui/selectors/fixture_selector_dialog.py
- Shared dialog helpers in Tools and jaws Library/ui/selectors/common.py

Current selector internals rely on QDialog lifecycle methods:
- _cancel_dialog
- _finish_submit
- closeEvent acceptance/rejection

### 2.3 Work Editor layout baseline

Work Editor currently builds tabs and button row with:
- Setup Manager/ui/work_editor_support/dialog_lifecycle.py

Current composition:
- One root QVBoxLayout.
- QTabWidget for editor tabs.
- QDialogButtonBox for Save/Cancel.

No embedded selector page exists yet.

---

## 3. Target Architecture

### 3.1 High-level design

Introduce embedded selector mode in Work Editor with a dedicated host:
1. Work Editor has two UI states:
   - normal mode (tabs + save/cancel)
   - selector mode (selector widget only)
2. Selector mode is rendered inside Work Editor using widget-based selector cores.
3. External bridge path remains available initially behind feature flag.

### 3.2 Core components to introduce

#### A. Embedded selector host
New module:
- Setup Manager/ui/work_editor_support/embedded_selector_host.py

Responsibilities:
- Switch Work Editor mode normal <-> selector.
- Capture/restore geometry.
- Expand/shrink dialog width.
- Mount/unmount current selector widget.
- Connect DONE/CANCEL callbacks.

#### B. Selector widget cores
New shared module group:
- shared/ui/selectors/base_selector_widget.py
- shared/ui/selectors/tool_selector_widget.py
- shared/ui/selectors/jaw_selector_widget.py
- shared/ui/selectors/fixture_selector_widget.py

Signal contract (required):
- submitted(dict payload)
- canceled()

#### C. Setup Manager selector providers/adapters
New module:
- Setup Manager/ui/work_editor_support/selector_provider.py

Responsibilities:
- Supply selector widget data from Setup Manager caches/services.
- Keep payload format compatible with existing apply_*_selector_result code.

#### D. Compatibility wrappers
Keep existing dialog wrappers in Tool Library and adapt them to host the new widget cores.

---

## 4. Data and Payload Compatibility Requirements

All embedded selectors must produce payloads equivalent to existing flows.

### 4.1 Tool selector payload requirements
Required keys:
- kind = tools
- selected_items: list[dict]
- selector_head: str
- selector_spindle: str
- assignment_buckets_by_target: dict[str, list[dict]]

Bucket key format:
- HEADx:spindle, for example HEAD1:main, HEAD2:sub

### 4.2 Jaw selector payload requirements
Required keys:
- kind = jaws
- selected_items: list[dict]

Per-item slot/spindle metadata must remain available where currently expected.

### 4.3 Fixture selector payload requirements
Required keys:
- kind = fixtures
- selected_items: list[dict]
- target_key: str
- assignment_buckets_by_target: dict[str, list[dict]]

### 4.4 Apply path compatibility
Do not change these public adapters in phase 1 unless unavoidable:
- apply_tool_selector_result
- apply_jaw_selector_result
- apply_fixture_selector_result

If payload shape changes are required, add adapter normalization layer instead of changing all callsites.

---

## 5. UI and Geometry Behavior Specification

### 5.1 Mode switching behavior

Enter selector mode:
1. Save current geometry and min size.
2. Hide normal editor view.
3. Show selector host view.
4. Expand width to target selector width.
5. Keep dialog on-screen with clamping.

Exit selector mode:
1. Unmount selector widget.
2. Hide selector host view.
3. Show normal editor view.
4. Restore original geometry and min size.

### 5.2 Width expansion rules

Recommended defaults:
- min selector content width: 1100
- expansion delta: +420 to +560 from current width

Algorithm:
1. desired_width = max(current_width + delta, min_selector_width)
2. clamp against available screen width
3. resize while preserving top-left anchor when possible

### 5.3 Visual parity rules

Preserve style hooks used by QSS:
- panelActionButton
- primaryAction
- secondaryAction
- detailHeader
- detailHint
- topBarIconButton
- bottomBar
- toolBadge

Preserve object names where style depends on them:
- sideNavButton
- toolHeadRailFilter
- topTypeFilter

No visual redesign in this phase.

---

## 6. Migration Phases

### Phase 0: Guardrails and feature flag

Tasks:
1. Add feature flag for selector transport mode.
2. Keep default = external to avoid behavior changes until validated.
3. Add telemetry/logging points for open/submit/cancel events.

Files:
- Setup Manager/ui/work_editor_dialog.py
- Setup Manager config/prefs service integration points

Deliverable:
- Runtime switch between external and embedded modes.

### Phase 1: Work Editor container refactor

Tasks:
1. Refactor dialog root to QStackedWidget with two pages:
   - normal page: existing tabs + Save/Cancel
   - selector page: empty host container
2. Add mode helpers in WorkEditorDialog:
   - _enter_selector_mode
   - _exit_selector_mode
   - _capture_selector_restore_state
   - _restore_from_selector_state

Files:
- Setup Manager/ui/work_editor_support/dialog_lifecycle.py
- Setup Manager/ui/work_editor_dialog.py

Deliverable:
- Work Editor can toggle pages without selectors yet.

### Phase 2: Introduce embedded selector host

Tasks:
1. Implement WorkEditorSelectorHost class.
2. Implement geometry expansion/restore logic.
3. Implement mount/unmount lifecycle.
4. Wire host instance into WorkEditorDialog.

Files:
- Setup Manager/ui/work_editor_support/embedded_selector_host.py (new)
- Setup Manager/ui/work_editor_dialog.py

Deliverable:
- Host can display placeholder selector widget and restore mode safely.

### Phase 3: Extract selector widget cores

Tasks:
1. Extract Tool selector dialog UI/state/payload into ToolSelectorWidget.
2. Extract Jaw selector dialog UI/state/payload into JawSelectorWidget.
3. Extract Fixture selector dialog UI/state/payload into FixtureSelectorWidget.
4. Keep thin QDialog wrappers for Tool Library compatibility.

Files:
- shared/ui/selectors/* (new)
- Tools and jaws Library/ui/selectors/tool_selector_dialog.py
- Tools and jaws Library/ui/selectors/jaw_selector_dialog.py
- Tools and jaws Library/ui/selectors/fixture_selector_dialog.py
- Tools and jaws Library/ui/selectors/common.py

Deliverable:
- Dialog wrappers use widget cores internally.

### Phase 4: Setup Manager provider adapters

Tasks:
1. Create provider APIs for tool/jaw/fixture selector widgets.
2. Implement providers using existing caches and helper functions:
   - load_external_tool_refs
   - merge_tool_refs
   - merge_jaw_refs
3. Normalize all IDs and spindle/head keys consistently.

Files:
- Setup Manager/ui/work_editor_support/selector_provider.py (new)
- Setup Manager/ui/work_editor_support/selectors.py
- Setup Manager/ui/work_editor_support/selector_adapter.py

Deliverable:
- Embedded widgets can run without Tool Library process.

### Phase 5: Route Work Editor selector actions to embedded host

Tasks:
1. Update:
   - _open_tool_selector
   - _open_jaw_selector
   - _open_fixture_selector
2. If feature flag = embedded, open via host.
3. If feature flag = external, keep bridge path unchanged.
4. Connect submitted payloads to existing apply_*_selector_result.

Files:
- Setup Manager/ui/work_editor_dialog.py
- Setup Manager/ui/work_editor_support/selector_flow.py

Deliverable:
- Embedded selector end-to-end path operational.

### Phase 6: Validation and parity hardening

Tasks:
1. Validate payload parity between embedded and external modes.
2. Validate assignment ordering and spindle mapping.
3. Validate geometry restore in all close paths.
4. Validate style parity for all selector controls.

Files:
- tests/* (add/extend)

Deliverable:
- Embedded path stable enough to become default.

### Phase 7: Default switch and bridge deprecation for Work Editor

Tasks:
1. Switch default feature flag to embedded.
2. Keep external path as fallback for one release cycle.
3. Add deprecation comments in bridge modules for Work Editor usage.

Files:
- Setup Manager/ui/work_editor_dialog.py
- Setup Manager/ui/work_editor_support/bridge*.py
- docs/*

Deliverable:
- Embedded mode is production default.

### Phase 8: Cleanup

Tasks:
1. Remove unused Work Editor-specific external bridge code paths.
2. Keep shared bridge only if used elsewhere.
3. Finalize architecture docs.

Deliverable:
- Reduced complexity and dead code removed.

---

## 7. Detailed Task Matrix (Agent-Executable)

### 7.1 Setup Manager tasks

Task SM-001
- File: Setup Manager/ui/work_editor_support/dialog_lifecycle.py
- Change: Introduce dialog._root_stack with normal and selector pages.
- Verify: Existing tabs and save/cancel still render in normal page.

Task SM-002
- File: Setup Manager/ui/work_editor_dialog.py
- Change: Add selector mode geometry capture/restore fields and methods.
- Verify: Repeated enter/exit cycles restore original size exactly.

Task SM-003
- File: Setup Manager/ui/work_editor_support/embedded_selector_host.py (new)
- Change: Implement host class and public open/close APIs.
- Verify: Placeholder widget opens in selector page and closes cleanly.

Task SM-004
- File: Setup Manager/ui/work_editor_support/selector_provider.py (new)
- Change: Implement provider interfaces consumed by selector widgets.
- Verify: Provider returns complete data for tool/jaw/fixture lists.

Task SM-005
- File: Setup Manager/ui/work_editor_dialog.py
- Change: Route _open_tool_selector to embedded host path (feature-flagged).
- Verify: Tool selector opens in Work Editor and submits payload.

Task SM-006
- File: Setup Manager/ui/work_editor_dialog.py
- Change: Route _open_jaw_selector and _open_fixture_selector similarly.
- Verify: Jaw and fixture selectors open embedded and apply results.

Task SM-007
- File: Setup Manager/ui/work_editor_support/selector_flow.py
- Change: Keep flow wrappers, add embedded path integration where needed.
- Verify: No regression in existing callsites.

Task SM-008
- File: Setup Manager/ui/work_editor_support/bridge.py
- Change: Mark Work Editor path deprecated, keep fallback active.
- Verify: external mode still works when flag forces it.

### 7.2 Shared selector widget tasks

Task SH-001
- File: shared/ui/selectors/base_selector_widget.py
- Change: Add base widget with submitted/canceled signals and helper hooks.
- Verify: Unit test signal behavior.

Task SH-002
- File: shared/ui/selectors/tool_selector_widget.py
- Change: Port Tool selector layout/state/payload from Tool Library dialog mixins.
- Verify: Payload parity with current tool selector dialog.

Task SH-003
- File: shared/ui/selectors/jaw_selector_widget.py
- Change: Port jaw selector logic.
- Verify: main/sub mapping parity.

Task SH-004
- File: shared/ui/selectors/fixture_selector_widget.py
- Change: Port fixture selector logic with target buckets.
- Verify: bucket and target_key payload parity.

### 7.3 Tool Library compatibility wrapper tasks

Task TL-001
- File: Tools and jaws Library/ui/selectors/tool_selector_dialog.py
- Change: Replace internal body with ToolSelectorWidget host.
- Verify: Existing standalone dialog behavior unchanged.

Task TL-002
- File: Tools and jaws Library/ui/selectors/jaw_selector_dialog.py
- Change: Wrapper over JawSelectorWidget.
- Verify: Existing dialog payload unchanged.

Task TL-003
- File: Tools and jaws Library/ui/selectors/fixture_selector_dialog.py
- Change: Wrapper over FixtureSelectorWidget.
- Verify: Existing dialog payload unchanged.

---

## 8. Testing Strategy

### 8.1 Unit tests

Add tests for:
1. Geometry state machine in selector host.
2. Payload parity snapshots:
   - tool selector payload
   - jaw selector payload
   - fixture selector payload
3. Adapter behavior:
   - apply_tool_selector_result
   - apply_jaw_selector_result
   - apply_fixture_selector_result

### 8.2 Integration tests

Test cases:
1. Open Work Editor -> open tool selector embedded -> DONE -> verify tool assignments updated.
2. Open Work Editor -> open tool selector embedded -> CANCEL -> verify no mutation.
3. Repeat above for jaw and fixture selectors.
4. Verify window width expands on open and shrinks on close.
5. Verify behavior in both machine profile types:
   - turning profile
   - machining center profile

### 8.3 Regression command set

Run after each phase:

```bash
python scripts/run_quality_gate.py
python scripts/smoke_test.py
python -m pytest tests/test_priority1_targeted.py
python -m pytest tests/test_shared_regressions.py
```

---

## 9. Risk Register

Risk R1: Hidden coupling to QDialog in selector code.
- Mitigation: keep wrappers, port incrementally to widget cores.

Risk R2: Visual drift after extraction.
- Mitigation: preserve style properties/object names and compare screenshots.

Risk R3: Geometry restore bugs on small screens.
- Mitigation: clamp calculations and test edge geometries.

Risk R4: Payload mismatch causing assignment corruption.
- Mitigation: parity tests with fixtures from current payload outputs.

Risk R5: Boundary violations between apps.
- Mitigation: move reusable UI to shared, keep app adapters local.

---

## 10. Acceptance Criteria

Functional acceptance:
1. Embedded selector mode completes tool/jaw/fixture selection without external process.
2. DONE and CANCEL semantics match current behavior.
3. Assignment buckets and target keys preserved correctly.

UX acceptance:
1. Work Editor expands in selector mode and restores after close.
2. Selector view is selector-only and does not show normal tab content.
3. No focus, z-order, or ghost window issues.

Quality acceptance:
1. Quality gate passes.
2. Targeted and regression tests pass.
3. No new lint/type/runtime errors in touched modules.

---

## 11. Rollout Plan

1. Ship with feature flag default external for one validation cycle.
2. Enable embedded mode for internal testing.
3. After parity acceptance, switch default to embedded.
4. Keep external fallback one release cycle.
5. Remove deprecated Work Editor bridge path.

---

## 12. Notes for Implementing AI Agent

Execution order guidance:
1. Do not start by deleting bridge code.
2. Build dual-path safely first.
3. Keep apply_* selector result APIs stable until final cleanup.
4. Commit in small phases aligned to section 6.

Definition of completion:
- All acceptance criteria in section 10 are satisfied.
- Work Editor selector experience is fully embedded and stable.

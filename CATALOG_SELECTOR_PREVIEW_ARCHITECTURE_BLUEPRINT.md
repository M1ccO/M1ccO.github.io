# Catalog / Selector / Preview Architecture Blueprint

This file is the authoritative implementation blueprint for the current fade, selector-hosting, and detached-preview refactor.

Future AI agents should read this file after `AGENTS.md` and `CLAUDE.md` and before making more changes to:

- cross-process Setup Manager <-> Library handoff
- selector hosting or selector IPC
- detached 3D preview lifecycle
- preview warmup / preload behavior

This file supersedes patch-by-patch local fixes as the main structural reference for this workstream.

## GOALS

### Primary Goal

Restructure the application so that:

- Libraries remain the only source of truth for tool, jaw, and fixture metadata.
- Setup Manager becomes the production host for selector UX.
- Cross-process fades are used only for true catalog-window handoff.
- Detached 3D preview opens instantly without closing, hiding, or reopening the host UI.

### Target End State

- `Setup Manager/` hosts production selector sessions through the existing embedded selector parity path.
- `Tools and jaws Library/` remains the owner of full catalog windows, CRUD screens, exports, and authoritative metadata services.
- The cross-process handoff boundary exists only for catalog windows, not for selector opening.
- `shared/ui/transition_shell.py` is reduced to a catalog-transition subsystem with a persistent host window and a strict receiver-ready reveal contract.
- Preview runtime is no longer a single reparented widget. Each hosting process owns an explicit preview runtime pool or preview host manager.
- Selector dialogs and catalog pages stop borrowing each other's detached-preview helpers through implicit page contracts.

### Required Outcomes

- Opening Tool Library or Jaw Library from Setup Manager shows a visible, stable fade without jitter.
- Opening Tool Selector, Jaw Selector, or Fixture Selector from Work Editor does not involve a cross-process top-level dialog handoff.
- Embedded selector mode may temporarily grow larger than the base Work Editor dialog, but exiting selector mode must restore the original Work Editor geometry.
- Selector DONE and CANCEL paths return instantly and deterministically.
- First detached preview open is hot in:
  - Library pages
  - standalone Library selectors, if still retained temporarily
  - Setup Manager embedded selector hosts
- Opening detached preview does not close, hide, or recreate the surrounding UI.
- Preview warmup remains predictable across repeated opens. The first successful preview open must not consume the only warmed instance.
- DWM-aware window geometry parity remains exact for catalog-window handoff after move and resize.

### Acceptance Criteria

- Catalog handoff passes a real visual check on Windows: Setup Manager -> Library and Library -> Setup Manager both look intentional and smooth.
- Selector opening passes a visual check: no flash, no extra Library window creation feeling, no visible desktop gap.
- Detached preview passes a visual check: no host bounce, no selector close/reopen behavior, no cold-start lag on first open after startup.
- Automated coverage exists for:
  - transition host lifecycle
  - selector production path
  - preview pool claim / release
  - selector preview host stability
  - geometry regressions
- `python scripts/run_quality_gate.py` passes after every major phase.

### Non-Goals

- Do not move authoritative metadata ownership from Libraries into Setup Manager.
- Do not move full catalog pages into Setup Manager.
- Do not continue using cross-process selector dialogs as the long-term production architecture.
- Do not keep adding timing-only fixes on top of the current mixed selector / preview / transition model.
- Do not keep the current single `StlPreviewWidget` reparenting model as the final preload architecture.
- Do not add new runtime dependencies unless the Qt + Win32-only plan has been proven insufficient.

## RULES

### Source Of Truth Rules

- `Tools and jaws Library/` remains the sole source of truth for tool, jaw, and fixture metadata.
- Setup Manager may host selectors, but it must not become the owner of Library metadata.
- Any selector hosted in Setup Manager must read through Library-domain services or resolvers backed by the configured Library database paths.
- Setup cards, Work Editor rows, and selector rows must all resolve display information from the same canonical Library-backed data path.

### Hosting Rules

- Production selector UX belongs in `Setup Manager/`.
- Full catalog UX belongs in `Tools and jaws Library/`.
- The existing embedded selector parity seam in `Setup Manager/ui/work_editor_support/selector_parity_factory.py` is the migration target, not a side path.
- The existing cross-process selector open path in `Setup Manager/ui/work_editor_support/selector_session_controller.py::_try_open_via_ipc()` is legacy during migration and should not remain the final production path.

### Transition Rules

- Transition-shell fades apply only to true cross-process catalog window handoff.
- Selector open and selector close must not depend on cross-process top-level fade choreography.
- Embedded selector open and close may use a local in-process snapshot or page fade, but that transition must stay inside the Work Editor surface and must not reuse the catalog transition shell.
- The transition subsystem must use a persistent transition host per process, not a fresh helper top-level window per handoff.
- Reveal may begin only after receiver-ready is true.
- Receiver-ready means all of the following are complete:
  - frame geometry applied
  - show / showNormal completed
  - raise / activate / foreground work completed
  - one stable compositor-visible frame boundary reached
- Sender-side blind timers are not an acceptable substitute for receiver-ready.
- If catalog handoff feels slow to start, tune `shared/ui/transition_shell_config.py::sender_complete_delay_ms` first. That is the safest latency reduction because it shortens dead time before the visible sender fade starts without weakening the receiver-ready contract.
- If the transition still feels lazy after that safe reduction, the next aggressive step is an immediate sender-side visual cue on click. That cue may begin before receiver-ready, but actual sender completion / hide must still remain bound to the receiver-ready boundary.

### Preview Rules

- Preview runtime is allowed to be local to the process that hosts the visible preview UI.
- Preview data ownership still remains Library-owned.
- Embedded selector open should proactively warm the Library-process preview runtime before the first selector preview click whenever the Library host is hidden or not yet ready.
- Replace `shared/ui/helpers/preview_runtime.py` single-widget reparenting with an explicit preview runtime pool or preview host manager.
- No preview open action may hide, close, or recreate the surrounding page or selector UI.
- Catalog-page detached preview dialogs should avoid direct parent-window ownership churn during preview open. Independent tool-window hosting is allowed when it produces more stable Windows behavior than page-owned or host-owned parenting.
- No selector should import page detached-preview helpers as the long-term architecture if those helpers assume catalog-page ownership or lifecycle.
- Claim / release semantics must be explicit. A preview runtime instance must not be implicitly stolen by reparenting.

### Lifecycle Rules

- There must be one production selector session path after migration.
- There must be one production detached-preview path per host type after migration.
- Preview pools must support repeated open / close cycles without degrading into cold creation after the first use.
- Work Editor shutdown must dispose embedded selector runtime cleanly.
- Library shutdown must dispose transition host and preview runtime cleanly.

### Repository Boundary Rules

- Respect the workspace architecture and import boundaries described in `AGENTS.md` and `CLAUDE.md`.
- Do not introduce cross-app imports from `Setup Manager/` into `Tools and jaws Library/` or the reverse unless they already flow through canonical shared or alias-based parity infrastructure.
- Do not replace canonical `shared.*` imports with legacy paths.
- Any migration must keep `Tools and jaws Library/` and `Setup Manager/` as separate applications.

### AI Agent Working Rules

- Read this file first for any task touching fades, selectors, or preview runtime.
- Do not start with small visual patches if the task touches selector hosting or preview lifecycle.
- Implement phase-by-phase and keep each phase responsibility-scoped.
- Preserve existing tests where possible and add targeted tests for new shared helpers.
- Run `python scripts/run_quality_gate.py` after each major phase or before declaring completion.
- If a phase changes visible UX, require a manual Windows verification pass before calling the phase complete.

## STATUS

### Approved Architectural Direction

- Selectors may move into Setup Manager, but Library data ownership must stay exactly as it is now.
- Preview runtime may be local to the process that hosts the preview UI.
- Transition-shell fades should target catalog-window handoff only.
- The current mixed model should be replaced with one structural refactor, not more isolated quick fixes.

### Current Structural Diagnosis

The current implementation still mixes three incompatible lifecycles:

- cross-process catalog handoff
- cross-process selector opening
- single-widget detached-preview reuse through reparenting

That mixed model is the root reason for the current symptom pattern:

- fade implementation changes create selector glitches
- selector fixes do not stabilize detached preview
- preview warmup changes do not stay hot after the first borrow
- opening detached preview can destabilize or visually bounce the host UI

### Current Code Reality

- Embedded selector hosting already exists through:
  - `Setup Manager/ui/work_editor_support/selector_session_controller.py`
  - `Setup Manager/ui/work_editor_support/selector_parity_factory.py`
- Current split between embedded and cross-process selector paths:
  - `_try_open_embedded()` in `Setup Manager/ui/work_editor_support/selector_session_controller.py`
  - `_try_open_via_ipc()` in `Setup Manager/ui/work_editor_support/selector_session_controller.py`
- Library still opens standalone selector dialogs through:
  - `_open_selector_dialog_for_session()` in `Tools and jaws Library/ui/main_window.py`
- Transition-shell prototype already exists in:
  - `shared/ui/transition_shell.py`
  - `shared/ui/transition_shell_config.py`
- DWM-aware geometry path already exists in:
  - `shared/ui/main_window_helpers.py`
- Preview warmup now starts early in `Tools and jaws Library/main.py`, and `shared/ui/helpers/preview_runtime.py` now uses an explicit available-widget pool with claim / release semantics.
- Embedded selector open now preloads the hidden Library preview host through an explicit `warm_preview_runtime` command, and selector mode can temporarily resize larger than Work Editor while restoring the original dialog geometry on exit.
- Hidden Library preload now also schedules preview-runtime warmup for catalog-page preview opens, so Library preview latency does not lag behind selector preview latency.
- Library catalog-page detached preview helpers now return detached viewers to the runtime pool on close in:
  - `Tools and jaws Library/ui/home_page_support/detached_preview.py`
  - `Tools and jaws Library/ui/jaw_page_support/detached_preview.py`
  - `Tools and jaws Library/ui/fixture_page_support/detached_preview.py`
- Selector dialogs now use selector-local detached preview hosting in:
  - `Tools and jaws Library/ui/selectors/detached_preview.py`
  - `Tools and jaws Library/ui/selectors/tool_selector_dialog.py`
  - `Tools and jaws Library/ui/selectors/jaw_selector_dialog.py`
  - `Tools and jaws Library/ui/selectors/fixture_selector_dialog.py`
- Fixture preview normalization was split into the selector-safe shared module:
  - `Tools and jaws Library/ui/fixture_preview_rules.py`
- Transition-shell completion is no longer driven by a fixed receiver timer. Receiver-side reveal completion now waits for visible, geometry-stable frames through `shared/ui/transition_shell.py`, and the shell host is reused per sender window instead of recreated per handoff.
- Embedded selector open now starts with an immediate local snapshot shield and fades that shield out only after the selector subtree is mounted and settled, so the transition begins on click without exposing live widget jitter.
- Catalog-page detached preview dialogs now use independent tool-window hosting for stable Windows behavior instead of remaining coupled to the Library shell ownership chain.
- Current latency-tuning order for catalog handoff is now explicit:
  - first reduce only the post-ready sender completion delay in `shared/ui/transition_shell_config.py`
  - only if the handoff still feels too lazy, add a subtle sender-side visual cue that starts immediately on click while keeping sender hide on the receiver-ready boundary

### Code Path Index

#### Setup Manager

- `Setup Manager/main.py`
  - receiver-side catalog handoff sequencing
  - selector result delivery
- `Setup Manager/ui/main_window_support/library_handoff_controller.py`
  - sender-side catalog open requests
- `Setup Manager/ui/work_editor_support/selector_session_controller.py`
  - current split between embedded selector hosting and Library IPC selector hosting
- `Setup Manager/ui/work_editor_support/selector_parity_factory.py`
  - current embedded selector parity builder and runtime bundle creation
- `Setup Manager/ui/work_editor_support/embedded_selector_host.py`
  - embedded selector mount / detach surface inside Work Editor
- `Setup Manager/ui/work_editor_support/selector_adapter.py`
  - selector result apply rules
- `Setup Manager/ui/work_editor_support/selector_provider.py`
  - selector request defaults / initial state

#### Tools And Jaws Library

- `Tools and jaws Library/main.py`
  - Library app bootstrap, preview warmup scheduling, receiver-side handoff sequencing
- `Tools and jaws Library/ui/main_window.py`
  - selector session state, warm-cache dialogs, selector dialog open path
- `Tools and jaws Library/ui/main_window_support/setup_handoff.py`
  - Library -> Setup Manager catalog return path
- `Tools and jaws Library/ui/main_window_support/selector_session.py`
  - selector payload-to-session normalization
- `Tools and jaws Library/ui/selectors/`
  - standalone selector dialogs and embedded parity widgets
- `Tools and jaws Library/ui/home_page_support/detached_preview.py`
  - tool detached preview lifecycle
- `Tools and jaws Library/ui/jaw_page_support/detached_preview.py`
  - jaw detached preview lifecycle
- `Tools and jaws Library/ui/fixture_page_support/detached_preview.py`
  - fixture detached preview lifecycle

#### Shared

- `shared/ui/transition_shell.py`
  - current sender-fade shell prototype
- `shared/ui/transition_shell_config.py`
  - mode and timing settings
- `shared/ui/main_window_helpers.py`
  - DWM-aware geometry capture / apply and snapshot helper
- `shared/ui/helpers/preview_runtime.py`
  - current single-widget preview runtime registration and claim path
- `shared/ui/helpers/detached_preview_common.py`
  - detached preview dialog host rules and selector-safe independent dialog logic
- `shared/ui/stl_preview.py`
  - underlying QWebEngine preview widget lifecycle

#### Tests

- `tests/test_transition_shell.py`
- `tests/test_main_window_helpers_geometry.py`
- `tests/test_main_window_helpers_snapshot.py`
- `tests/test_preview_runtime.py`
- `tests/test_selector_preview_hosting.py`
- `tests/test_work_editor_embedded_selector.py`

### Implementation Phases

| Phase | Name | Depends On | Primary Files / Directories | Target Outcome | Status |
| --- | --- | --- | --- | --- | --- |
| 0 | Freeze Architecture | none | root blueprint docs | confirm selector host, preview ownership, fade scope | Approved |
| 1 | Promote Embedded Selectors | 0 | `Setup Manager/ui/work_editor_support/selector_session_controller.py`, `Setup Manager/ui/work_editor_support/selector_parity_factory.py`, `Tools and jaws Library/ui/selectors/` | Setup Manager becomes production selector host | In progress - embedded is the default production path; IPC remains fallback only |
| 2 | Harden Embedded Selector Parity | 1 | `Setup Manager/ui/work_editor_support/embedded_selector_host.py`, `Setup Manager/ui/work_editor_support/selector_adapter.py`, `Setup Manager/ui/work_editor_support/selector_provider.py`, `Tools and jaws Library/ui/selectors/` | embedded selectors reach production parity for submit, cancel, reset, and detail state | In progress - cached fixture reuse, reset cleanup, preview guards, and preview-host preload are implemented |
| 3 | Extract Selector Preview Host Contract | 1, 2 | `shared/ui/helpers/`, `Tools and jaws Library/ui/selectors/`, detached preview helpers | selectors stop borrowing catalog-page preview lifecycle implicitly | Substantially complete - selector-local detached preview host exists for tool, jaw, and fixture selectors |
| 4 | Replace Preview Singleton With Pool | 1, 3 | `shared/ui/helpers/preview_runtime.py`, `shared/ui/stl_preview.py`, detached preview modules in both apps | preview becomes truly hot and reusable without UI bounce | In progress - runtime pool claim / release is implemented, and embedded selectors now proactively warm the Library preview runtime before first preview open |
| 5 | Narrow Fades To Catalog Only | 1 | `shared/ui/transition_shell.py`, `shared/ui/transition_shell_config.py`, `Setup Manager/main.py`, `Tools and jaws Library/main.py` | selector opening removed from cross-process fade surface | In progress - catalog handoff remains the only cross-process fade boundary; embedded selectors now use a local in-process page fade |
| 6 | Add Persistent Transition Host + Receiver-Ready Reveal | 5 | catalog handoff files plus `shared/ui/main_window_helpers.py` | visible stable fades with no helper-window feeling and no jitter | In progress - receiver-ready gating and persistent shell reuse are implemented; manual Windows verification still required |
| 7 | Retire Legacy Cross-Process Selector Path | 2, 3, 4 | `Setup Manager/ui/work_editor_support/selector_session_controller.py`, `Tools and jaws Library/ui/main_window.py`, `Tools and jaws Library/main.py` | one production selector path remains | Not started |
| 8 | Diagnostics, Tests, Cleanup | 1-7 | `tests/`, shared helpers, logging points | measurable latency, green quality gate, final cleanup | Not started |

### Phase Relations

- Phase 1 is the structural pivot. Do not treat fade or preview as final until selector hosting is moved.
- Phase 2 depends on Phase 1 because parity work only matters after embedded selector hosting becomes the production target.
- Phase 3 depends on Phases 1 and 2 because selector preview contracts should be designed around the final selector host, not the legacy cross-process dialog path.
- Phase 4 depends on Phase 3 because preview pooling must plug into explicit host contracts, not implicit page-helper reuse.
- Phase 5 may begin once Phase 1 is committed because fade scope should be reduced as soon as selector opening is no longer a production cross-process path.
- Phase 6 depends on Phase 5 because persistent transition host and receiver-ready reveal only make sense after fade scope is narrowed to catalog handoff.
- Phase 7 depends on Phases 2, 3, and 4 because legacy selector IPC should not be retired until embedded selector parity and preview behavior are verified.
- Phase 8 spans the whole effort but should be treated as a formal closeout phase after structural migration is complete.

### Detailed Phase Notes

#### Phase 1 - Promote Embedded Selectors

Primary implementation targets:

- `Setup Manager/ui/work_editor_support/selector_session_controller.py`
  - make `_try_open_embedded()` the default selector open path
  - demote `_try_open_via_ipc()` to fallback or temporary compatibility route
- `Setup Manager/ui/work_editor_support/selector_parity_factory.py`
  - keep Library-domain data access while hosting the selector UI in Setup Manager
- `Tools and jaws Library/ui/selectors/tool_selector_dialog.py`
- `Tools and jaws Library/ui/selectors/jaw_selector_dialog.py`
- `Tools and jaws Library/ui/selectors/fixture_selector_dialog.py`

Exit criteria:

- Work Editor opens selectors without spawning or surfacing Library top-level dialog UX.
- Selector submit and cancel paths remain correct.

#### Phase 2 - Harden Embedded Selector Parity

Primary implementation targets:

- ensure session reset, mount / detach, and reuse caching are deterministic
- ensure selector-local state and assignment state do not visually rebuild mid-session
- confirm Library-domain services are reused safely when hosted in Setup Manager

Exit criteria:

- embedded selector behavior matches current production selector capability for normal sessions
- no Work Editor shutdown leak or selector lifetime leak remains

#### Phase 3 - Extract Selector Preview Host Contract

Primary implementation targets:

- stop direct selector imports of catalog page detached-preview helpers
- add explicit selector preview host helpers under `shared/ui/helpers/` or selector-specific support modules

Exit criteria:

- selector preview open / close behavior no longer depends on catalog-page assumptions

#### Phase 4 - Replace Preview Singleton With Pool

Primary implementation targets:

- replace `register_preview_runtime_widget()` / `claim_prewarmed_preview_widget()` singleton behavior
- implement preview pool or preview host manager per process
- add explicit claim / release API

Exit criteria:

- first preview open is hot
- second preview open is still hot
- closing preview does not consume or orphan the only warmed runtime

#### Phase 5 - Narrow Fades To Catalog Only

Primary implementation targets:

- remove selector-open dependencies from fade logic
- treat `shared/ui/transition_shell.py` as catalog-only infrastructure

Exit criteria:

- selector UX no longer participates in cross-process fade choreography

#### Phase 6 - Persistent Transition Host + Receiver-Ready Reveal

Primary implementation targets:

- replace per-handoff helper top-level creation with persistent transition host per process
- implement explicit receiver-ready reveal in:
  - `Setup Manager/main.py`
  - `Tools and jaws Library/main.py`
  - `Setup Manager/ui/main_window_support/library_handoff_controller.py`
  - `Tools and jaws Library/ui/main_window_support/setup_handoff.py`
- apply transition tuning in this order:
  - first reduce dead time before the visible fade by trimming `sender_complete_delay_ms`
  - only after that, consider an immediate sender-side click cue if real Windows validation still shows perceptible startup lag

Exit criteria:

- fade is visible
- no extra helper-window feeling
- no jitter at reveal
- transition starts promptly after click without regressing receiver-ready correctness

#### Phase 7 - Retire Legacy Paths

Primary implementation targets:

- reduce or remove `_try_open_via_ipc()` as the default production path
- reduce or remove Library selector dialog orchestration that only exists for Setup Manager selector sessions

Exit criteria:

- one production selector host path remains
- remaining legacy path, if any, is explicitly marked fallback-only

#### Phase 8 - Diagnostics, Tests, Cleanup

Add instrumentation for:

- transition prepare latency
- receiver-ready latency
- reveal duration
- preview claim latency
- preview cold-create fallback count

Add or expand tests for:

- embedded selector production path
- persistent transition host state machine
- preview pool claim / release and reuse
- selector preview host stability

Final exit criteria:

- manual Windows verification passes
- `python scripts/run_quality_gate.py` passes
- obsolete experimental paths are removed or clearly marked temporary

### Agent Startup Checklist

Before implementing the next change in this workstream:

1. Read `AGENTS.md`.
2. Read `CLAUDE.md`.
3. Read this file.
4. Read `WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md` for prior selector ownership decisions.
5. Identify the current phase and its dependencies.
6. Do not skip to a later phase unless all earlier dependencies are already satisfied in code.

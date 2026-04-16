# Work Editor Glitching Status (April 16, 2026)

## Final Outcome
- Resolved: user-confirmed glitching is gone for both `ADD WORK` and `EDIT WORK`.
- Resolved: no more Work Editor startup crashes from missing lazy-built widgets.

## Confirmed Root Cause
- The remaining visible glitching was profile-specific startup load on lathe configurations.
- Lathe startup eagerly built heavy `Zero Points` and `Tool IDs` tab content before first stable frame.
- Machining Center path was lighter, which is why MC looked stable earlier.

## Implemented Fix (Shipped)
- Kept selector/session and style-host hardening already completed earlier.
- Introduced lathe-only lazy build for heavy tabs:
	- `Zero Points` tab builds on first activation.
	- `Tool IDs` tab builds on first activation.
- Added build-before-save guard so payload collection always has required widgets.
- Added payload adapter safety checks so `EDIT WORK` can load even when lazy tabs are not yet built.

## Regression Fixes During Rollout
- Fixed missing `shared_move_up_btn` crash by guarding tool-sync/action calls until Tools tab is built.
- Fixed missing `main_program_input` crash by guarding payload adapter access and applying value when lazy Zero tab initializes.

## Cleanup Completed
- Removed obsolete deferred-lathe startup path that was no longer used:
	- removed dead deferred state fields from `WorkEditorDialog`
	- removed dead `_finish_deferred_lathe_startup` flow
	- removed deferred-startup hook in launch priming helper
- Kept active startup/visibility guards that still provide safe behavior.

## Files Changed In Final Resolution
- `Setup Manager/ui/work_editor_dialog.py`
- `Setup Manager/ui/work_editor_support/model.py`
- `Setup Manager/ui/setup_page_support/work_editor_launch.py`

## Verification Snapshot
- Focused regression slice remained green through the final fixes:
	- `tests.test_work_editor_launch_parent`
	- `tests.test_selector_adapter_phase6`
	- `tests.test_selector_host_phase6`
	- `tests.test_work_editor_geometry_phase6`
	- `tests.test_work_editor_embedded_selector`
	- `tests.test_work_editor_style_inheritance`
- User acceptance result: glitching gone.

## Follow-Up Guidance
- Treat lathe startup widget cost as the first suspect if similar visual glitches return.
- Keep lazy-build + payload guards in place for profile-specific heavy tabs.

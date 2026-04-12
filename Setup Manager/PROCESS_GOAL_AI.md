# Process Goal + Status (AI Resume)

## Objective
Refactor oversized UI/editor modules into support modules, preserve behavior and DB compatibility, and prepare capability/profile-driven machine variants.

## Progress
- Phase completion: ~90% (main-module modularization pass).

## Completed
- Setup Manager Work Editor refactor (`ui/work_editor_dialog.py`):
  - extracted tab builders, tools tab builder, selector flow, pot editor, IO/validation, and tool actions into:
    - `ui/work_editor_support/tab_builders.py`
    - `ui/work_editor_support/tools_tab_builder.py`
    - `ui/work_editor_support/selector_flow.py`
    - `ui/work_editor_support/pot_editor.py`
    - `ui/work_editor_support/io_validation.py`
    - `ui/work_editor_support/tool_actions.py`
  - removed large wrapper/delegate blocks from dialog.
  - size reduction: `work_editor_dialog.py` ~2785 -> ~2035 lines.

- Tools & Jaws Library Home page refactor (`ui/home_page.py`):
  - moved selector action logic into:
    - `ui/home_page_support/selector_actions.py`
  - rewired selector card/bottom bars to direct support callbacks.
  - removed thin selector wrapper methods.
  - size reduction: `home_page.py` ~2361 -> ~2199 lines.

- Tools & Jaws Library Jaw page refactor (`ui/jaw_page.py`):
  - moved selector actions into:
    - `ui/jaw_page_support/selector_actions.py`
  - rewired selector slot/card actions to controller/helper callbacks.
  - removed selector wrapper methods.
  - size reduction: `jaw_page.py` ~1775 -> ~1691 lines.

- Shared support wiring:
  - support-package `__init__.py` exports updated for extracted modules.
  - selector card/bottom bar builders now call support helpers directly.

## Validation Done
- `py_compile` on touched modules.
- support `compileall` for `work_editor_support`, `home_page_support`, `jaw_page_support`.
- import smoke:
  - `WorkEditorDialog`
  - `HomePage`
  - `JawPage`
  - `AddEditToolDialog`

## Open / Remaining
- Machine profile capability layer still partial (gating exists, not yet fully centralized into one explicit profile contract).
- Compatibility view-model layer still partial (legacy adapters improved, not fully unified across all editors).
- No automated regression test suite yet (current verification is compile/import + manual behavior checks).
- Repo still has staged-unready mixed edits; needs final cleanup + commit segmentation.

## Next Priority
1. Final doc/status sync:
   - update top-level selector status doc with this phase outcomes.
2. Final manual regression sweep:
   - Setup Manager -> Tool/Jaw selector open/return
   - tool/jaw assignment save/load
   - selector cancel/done semantics
3. Small hygiene pass:
   - remove residual unused imports/helpers from touched modules.
4. Commit in 1-2 coherent chunks.

## Constraints
- Keep Python/PySide6 architecture.
- Keep DB compatibility-first (additive-only migrations).
- Keep ownership boundary:
  - Setup Manager = reference consumer
  - Tool/Jaw Library = master-data owner.

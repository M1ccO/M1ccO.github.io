# Tools and Jaws Library — Modular Platform Overhaul: Rules for AI Agents

These rules govern all contributions to the Tools and Jaws Library during the modular platform overhaul (Phases 0-9). Follow them to maintain backward compatibility, architecture determinism, and codebase health.

---

## Fundamental Non-Negotiables

### 1. Backwards Compatibility (STRICT)

**Rule**: No destructive changes to database schemas, IPC handoff, user workflows, or file format.

**Permitted**:
- ✅ Add columns to tables (migrations additive-only)
- ✅ Add new services or service methods without changing old signatures
- ✅ Refactor internal logic if old call sites still work (use adapters)
- ✅ Create new support modules if they don't break existing imports

**Forbidden**:
- ❌ `ALTER TABLE DROP COLUMN` or `DROP TABLE`
- ❌ Change existing function signature without double-path support (new sig + adapter)
- ❌ Move/rename file unless you maintain a shim at the old path and log removal target date
- ❌ Break IPC protocol between Setup Manager and Tool Library

**Verification**:
- Run `python scripts/smoke_test.py` before and after changes
- Existing `.db` files must open without manual intervention
- CRUD workflows must pass parity tests (see [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md))

---

### 2. Import Boundaries (ENFORCED)

**Rule**: Import paths are governed by canonical rules in [AGENTS.md](../AGENTS.md).

**Permitted**:
- ✅ Imports from `shared.*` (canonical shared modules)
- ✅ App-local imports within same app (e.g., `from ui.home_page_support import ...`)
- ✅ Imports from domain module __init__.py after Phase 1

**Forbidden**:
- ❌ Direct import from one app into another (e.g., `Tools and jaws Library` importing from `Setup Manager`)
- ❌ Legacy paths like `from shared.editor_helpers` instead of `from shared.ui.helpers.editor_helpers`
- ❌ Circular imports (service A imports service B which imports service A)

**Verification**:
```bash
python scripts/import_path_checker.py
```
Must exit with code 0 (no violations). Add violations ONLY if you update [AGENTS.md](../AGENTS.md) import rules AND run quality gate.

---

### 3. Duplication Baseline (TRACKED)

**Rule**: Reduce code duplication incrementally per phase. Do not increase duplication without explicit alignment with this document.

**Current Baseline** (as of April 13, 2026):
- `home_page.py` + `jaw_page.py`: 85% duplicated (selector/batch/detail logic)
- `tool_catalog_delegate.py` + `jaw_catalog_delegate.py`: 95% duplicated
- `home_page_support/*` + `jaw_page_support/*`: 15 vs 7 files; same patterns
- `ToolService` + `JawService`: 70% duplicated

**Permitted**:
- ✅ Move duplicated code into shared base classes during phases 3-5
- ✅ Create support modules if they are domain-independent (e.g., `measurement_rules.py` usable by both editors)
- ✅ Intentional duplication if documented (see "Intentional Duplication" section below)

**Forbidden**:
- ❌ Add new code that duplicates existing patterns if a shared option exists
- ❌ Increase duplication in targeted hotspots (home_page.py, jaw_page.py, delegates, services) during phases 3-5

**Verification**:
```bash
python scripts/duplicate_detector.py
```
Run before and after; document delta in phase completion note.

---

### 4. Phase Sequencing (STRICT ORDER)

**Rule**: Phases must complete in order. Do not start Phase N until Phase N-1 is signed off.

**Dependencies**:
- Phase 1 depends on Phase 0 complete
- Phase 2 depends on Phase 1 complete
- Phases 3, 4, 5, 6 can run with careful coordination (see overlap gates below)
- Phase 7 parallel with 4-6 but complete before 8
- Phase 8 depends on 4, 5, 7 complete
- Phase 9 depends on 8 complete

**Overlap Allowed** (during phases 3-6):
- Platform layer (Phase 3) can harden in parallel with TOOLS migration (Phase 4) IF:
  - Platform layer uses adapters to not break current TOOLS/JAWS
  - TOOLS migration only touches `ui/domain_modules/tools_module/*`; does not modify `ui/home_page.py` until Phase 4 cut-over
  - JAWS migration (Phase 5) does not start until TOOLS Phase 4 is parity-tested

**Verification**:
- Check phase status in [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md)
- Add completion proof (test output, acceptance criteria checklist) before marking phase complete

---

## Architecture-Specific Rules

### 5. Module Ownership and Boundaries

**Rule**: Each module has explicit owner and public API. Do not cross boundaries without architectural review.

**Current Ownership** (as of Phase 0):
- `ui/home_page.py`: TOOLS page (1500L monolith, target for Phase 4 migration)
- `ui/jaw_page.py`: JAWS page (1300L monolith, target for Phase 5 migration)
- `ui/tool_editor_dialog.py`: TOOLS editor (1000L, already partially extracted in Phase 1)
- `ui/jaw_editor_dialog.py`: JAWS editor (900L, target for Phase 5)
- `ui/tool_editor_support/*`: TOOLS editor helpers (reusable: measurement_rules.py, transform_rules.py)
- `ui/jaw_page_support/*`: JAWS page helpers (duplicated patterns, target for Phase 5)
- `services/tool_service.py`: TOOLS CRUD (300L, 70% shared with JawService)
- `services/jaw_service.py`: JAWS CRUD (400L, 70% shared with ToolService)
- `services/export_service.py`: TOOLS export (domain-specific, target for Phase 3)
- `data/migrations.py`: both tools+jaws migrations (branchy, target for Phase 6 segmentation)

**Permitted**:
- ✅ Refactor within owned module (e.g., extract from home_page.py into home_page_support/*)
- ✅ Move to `shared/*` if change is cross-domain and approved in Phase 2
- ✅ Add new support modules under `tools_module/` or `jaws_module/` after Phase 1

**Forbidden**:
- ❌ Cross-modify TOOLS and JAWS boundaries without architecture review
- ❌ Move code between domains before explicit Phase N gate
- ❌ Add logic to `tool_editor_support/` that JAWS needs; make it shared first

**Verification**:
- Owner of file listed in [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md) module tracker
- If you need to modify a file you don't own, ask in PR/review; don't sneak changes

---

### 6. Adapter and Shim Lifecycle

**Rule**: Temporary adapters exist to bridge refactors. Mark them with removal target; retire only after parity proof.

**Permitted**:
- ✅ Add adapter if it lets old code call new code without changes
  - Example: `_JawToolServiceAdapter` in `jaw_export_page.py` wraps JawService as ToolService-like interface
- ✅ Keep adapter for 1-2 minor releases during refactor
- ✅ Need explicit removal target in comment:
```python
# ADAPTER: Retire Q2-2026 after ExportPage refactor complete
# Replacement: ExportPage.from_export_spec()
class _JawToolServiceAdapter:
    ...
```

**Forbidden**:
- ❌ Add adapter without removal target and justification
- ❌ Keep adapter beyond target date without re-approval
- ❌ Add new code that depends on adapter (adapters are bridges, not features)

**Verification**:
- Search for `ADAPTER:` and `SHIM:` comments; verify removal targets have phase gates
- Run quality gate to check shim-registry (when Phase 2 complete)

---

### 7. Test Coverage and Parity Proof

**Rule**: Any refactoring that changes file/class organization must prove user-visible behavior is identical.

**Required Parity Tests**:

Per Phase:

| Phase | TOOLS Tests | JAWS Tests | Export Tests | IPC Tests |
|-------|------------|-----------|--------------|-----------|
| 4 (TOOLS) | ✅ Additive field CRUD (add tool, edit, delete) | N/A | ✅ Excel export | N/A |
| 4 (TOOLS) | ✅ Copy tool | N/A | ✅ Excel import | N/A |
| 4 (TOOLS) | ✅ STL preview inline + detached | N/A | ✅ DB switching | N/A |
| 5 (JAWS) | N/A | ✅ Jaw CRUD | ✅ Jaw export | N/A |
| 5 (JAWS) | N/A | ✅ Preview plane + rotation save | ✅ Jaw import | N/A |
| 5 (JAWS) | N/A | ✅ Spindle filtering | N/A | N/A |
| 8 (Retire) | ✅ IPC handoff (Setup → Tools → Setup) | ✅ IPC handoff | N/A | ✅ Verified |

**Acceptance Criteria** (per refactor slice):
1. Run parity test baseline BEFORE changes
2. Apply changes
3. Run parity test after
4. Diff results; must show PASS for all cases
5. Include before/after output in phase completion note

**Verification**:
```bash
python scripts/smoke_test.py
# Run manual parity suite listed in TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md
```

---

### 8. Public API and Contracts

**Rule** (Phase 1 onward): Every refactored module must declare its public API and contract.

**Required per Module**:

1. **`__all__` export list** in `__init__.py`:
```python
__all__ = [
    'CatalogPageBase',
    'EditorDialogBase',
    'CatalogDelegate',
]
```

2. **Module contract document** (`contracts.md`):
```markdown
# Module: tools_module

## Public API
- `ToolsPage(CatalogPageBase)` — page orchestrator for TOOLS
- `AddEditToolDialog(EditorDialogBase)` — editor orchestrator for TOOLS

## Inputs (Injected)
- catalog_service: ToolService

## Outputs (Signals)
- item_selected(item_id: str)
- item_deleted(item_id: str)

## Lifecycle
1. Constructor + init_ui()
2. connect signals to caller
3. User interactions → signals fire
4. Caller responds → call methods on page

## Not In Scope
- Jaw-specific logic (spindle filtering, preview plane)
- JAWS module must provide its own page
```

**Permitted**:
- ✅ Add public methods/signals to module after publishing contract
- ✅ Change contract if you update all call sites and phase gate
- ✅ Deprecate old API with 6-month removal target

**Forbidden**:
- ❌ Refactor module without publishing contract
- ❌ Hide implementation details; make public API explicit
- ❌ Let agents guess what's in `__all__`

**Verification**:
- Every module in `ui/domain_modules/*/` must have `contracts.md`
- Every platform/ module must have contract doc or docstrings + `__all__`

---

## Intentional Duplication (Allowed)

Some duplication is intentional to preserve domain isolation. Document it explicitly.

**Allowed**:
- ✅ `ToolsExportSpec` (TOOLS export config) vs `JawsExportSpec` (JAWS export config)
  - Reason: tools and jaws have different fields; config-driven specs reduce copy-paste
  - Risk: none; specs are data, not code
- ✅ Tool-specific selector logic (spindle orientation, head assignment) vs Jaws-specific (spindle filters)
  - Reason: semantics differ; attempting unification hides domain requirements
  - Risk: low if isolated in domain subclasses
- ✅ Tool component picker (borrowing component codes from existing tools) vs Jaws (no such feature)
  - Reason: feature only makes sense for tools; jaws don't have reusable components
  - Risk: none; different responsibilities

**Not Allowed**:
- ❌ Duplicated batch-action helpers in both home_page_support/ and jaw_page_support/
  - Reason: identical logic, different naming; creates maintenance burden
  - Migration: extract to platforms/batch_actions.py (Phase 3)
- ❌ Two nearly-identical delegates (tool_catalog_delegate.py, jaw_catalog_delegate.py)
  - Reason: paint/sizing/role logic identical; only icon and detail differ
  - Migration: extract to platforms/catalog_delegate.py with callbacks (Phase 3)

**Verification**:
- Document intentional duplication with `# INTENTIONAL: reason` comments
- Include in duplicate_detector baseline exceptions if deliberate

---

## Working With Existing Support Modules

### 9. Tool Editor Support (`ui/tool_editor_support/`)

**Current Status** (as of April 2026):
- Partially extracted: ~428 lines moved into `component_picker_dialog.py`, `spare_parts_table_coordinator.py`, `component_linking_dialog.py`
- Result: `tool_editor_dialog.py` reduced from ~1400L to ~970L
- Grab bag pattern: contains both tool-specific (component picker) AND reusable utilities (measurement_rules, transform_rules)

**Permitted**:
- ✅ Extract more logic from `tool_editor_dialog.py` into `tool_editor_support/*` following same pattern
- ✅ Move `measurement_rules.py` and `transform_rules.py` to `shared.ui.helpers` if needed by jaw_editor (Phase 3)
- ✅ Refactor internal organization of tool_editor_support/ without changing public exports

**Forbidden**:
- ❌ Modify `component_picker_dialog.py` or `spare_parts_table_coordinator.py` without reviewing call sites (both are tool-specific)
- ❌ Export tool-specific logic from tool_editor_support/ as if it's reusable
- ❌ Import from tool_editor_support/ in jaw_editor_dialog unless you check if logic is truly reusable

**Verification**:
- Check `__all__` in `tool_editor_support/__init__.py`
- Imported by jaw_editor? Must be reusable, not tool-specific

---

### 10. Home Page and Jaw Page Support

**Current Status** (updated April 13, 2026 — post Phase 5):
- home_page_support/: thin domain orchestrators; home_page.py reduced 2,223L → 700L (Phase 4 complete)
- jaw_page_support/: thin domain orchestrators; jaw_page.py reduced 1,423L → 558L (Phase 5 complete)
- Both pages now delegate to support modules; shared platform logic lives in shared/ui/platforms/
- Structural duplication retired; remaining legacy coupling tracked in Phase 8

**Permitted** (Phases 0-2):
- ✅ Bug fixes in either support suite (fix both if pattern is identical)
- ✅ Extract more from home_page.py into home_page_support/ (preserve modular structure)
- ✅ Extract more from jaw_page.py into jaw_page_support/ (preserve modular structure)

**Forbidden** (Phases 0-2):
- ❌ New feature added to only one support suite (add to both if you add to either)
- ❌ Move code from home_page_support/ to shared/ without architecture review (Phase 3 gate)

**Permitted** (Phases 3-5):
- ✅ Extract shared patterns from both suites into platforms/ (Phase 3)
- ✅ Replace home_page_support/ with thin domain config after TOOLS migration (Phase 4)
- ✅ Replace jaw_page_support/ with thin domain config after JAWS migration (Phase 5)

**Verification**:
- Compare identical files in home_page_support/ and jaw_page_support/
- If 90%+ similar, file issue for Phase 3 extraction
- If different, document reason why in both files

---

## Quality Gates and Verification

### 11. Required Checks Before Committing

**Run before any commit**:
```bash
# 1. Code style and syntax
python -m py_compile "Tools and jaws Library"/*.py

# 2. Imports valid
python scripts/import_path_checker.py

# 3. Duplication baseline
python scripts/duplicate_detector.py

# 4. App startup
python scripts/smoke_test.py

# 5. Full quality gate
python scripts/run_quality_gate.py
```

**All must exit with code 0.**

---

### 12. Phase Completion Checklist

Before marking phase complete, verify:

- [ ] All required files created/modified per phase spec
- [ ] Parity tests pass (if applicable to phase)
- [ ] import_path_checker.py passes
- [ ] smoke_test.py passes
- [ ] No new import violations introduced
- [ ] Duplication baseline delta matches phase goals (or documented exception)
- [ ] Backward compatibility preserved (existing `.db` files work)
- [ ] Module contracts published (if Phase 1+)
- [ ] Adapter removal targets documented (if Phase 3+)
- [ ] Phase completion note added to [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md)

---

## Escalation and Exceptions

### Exception Process

If a rule must be violated (e.g., experimental feature requires cross-boundary import):

1. **File issue** in Tools and jaws Library project with:
   - Rule being violated
   - Reason why
   - Planned removal date
   - Risk assessment

2. **Add exception marker** in code:
```python
# EXCEPTION: [ticket-id] — Justification; remove [date]
# Risk: [assessment]
from Setup Manager.some_module import something
```

3. **Track in deprecations.json** (Phase 2 onward) with explicit removal target

4. **Expire automatically**: Removal target date passes → agent must either:
   - Implement intended fix and remove exception
   - File renewal request with new target date

---

## For AI Agents: Key Decision Points

**When you encounter a conflict, use this priority**:

1. **Backward compatibility** > Architecture beauty
   - If refactoring breaks one, preserve compat; defer architecture cleanup (add to Phase N backlog)

2. **Phase sequencing** > Tempting shortcuts
   - If Phase N is not complete, don't jump to Phase N+2
   - Document blocker in [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md), wait for approval

3. **Parity proof** > Code cleanup
   - If behavior is identical after refactor, cleanup is safe; prioritize parity tests first

4. **Explicit ownership** > Guessing
   - If you're unsure who owns a file or module, check [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md) module tracker before modifying

5. **Public contracts** > Hidden implementation
   - Publish `__all__`, contracts, and API docs before declaring refactor complete

---

See [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md) for current phase status, blockers, and ownership assignments.

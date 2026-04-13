# Tools and Jaws Library — Modular Platform Overhaul

## Vision

Transform Tools and Jaws Library from two duplicated, monolithic domains into a **reusable module platform** where TOOLS and JAWS are first-class domain modules, future domains (Fixtures, Robots, machine preferences, etc.) can be added with minimal copy-paste, and AI agents can work deterministically on the codebase without guessing architectural patterns.

---

## High-Level Goals

### 1. Eliminate Courage-Based Duplication (66% code reduction across UI)
- **Current state**: HomePage (1500L) + JawPage (1300L) with 85% duplicated logic
  - Selector state machines, batch actions, detail panel rendering all reimplemented
  - Same 15 files in `home_page_support/` AND `jaw_page_support/`
- **Target**: Single `CatalogPageBase` orchestrator
  - HomePage and JawPage become thin subclasses with domain config only (~300L each)
  - Domain-specific behavior (spindle filtering, head assignment) remains as overrides
  - Selector bug fixed once; applies to all domains automatically

### 2. Make Editors Declarative, Not Procedural (50% reduction in dialog code)
- **Current state**: `tool_editor_dialog.py` (1000L) + `jaw_editor_dialog.py` (900L)
  - Each dialog owns field builders, validation logic, tab orchestration
  - Adding a new field requires edits in 4+ places per dialog
- **Target**: Editor schemas define structure; base class handles orchestration
  - Tool/Jaw dialogs become 280-300L each (subclasses + schema definitions only)
  - Field metadata drives rendering, validation, serialization
  - Adding a field = update schema, no code rewrites

### 3. Unify Service Layer with Domain Specialization (50% reduction in service code)
- **Current state**: `ToolService` (300L) + `JawService` (400L)
  - 70% duplicated search/CRUD/normalization logic
  - No shared base; parallel implementations risk drift
- **Target**: `CatalogService` base (shared CRUD/search) + thin domain subclasses
  - ToolService/JawService: 50L each (only domain-specific filtering/normalization)
  - New domain (Fixtures): add 50L service, no duplication

### 4. Enable Zero-Copy Domain Onboarding (75% faster for new domains)
- **Current barrier**: Adding Fixtures module = copy 4500+ lines (home_page + jaw_page + services + support suites), debug for 3-4 weeks
- **Target**: Add 1000 lines total
  - Model + contracts (100L)
  - Thin page orchestrator (300L)
  - Thin editor subclass (300L)
  - Service subclass (50L)
  - Export spec (50L)
  - Migrations (50L)
  - Done in ~1 week with confidence

### 5. Make Architecture Deterministic for AI Agents
- **Current barriers**: 
  - No explicit module contracts; agents reverse-engineer patterns
  - Import rules not machine-checked; violations found in code review
  - Refactor status scattered across comments; unclear what's safe to extract
- **Target**:
  - Public API declared per module with `__all__` + module contracts
  - Boundary enforcement in quality gate script
  - Refactor tracking tied to phase gates with explicit completion criteria
  - Agents read contracts, not guess intent

### 6. Preserve Strict Backward Compatibility
- **Non-negotiables**:
  - No destructive schema changes; migrations additive-only
  - Existing `.db` files must upgrade silently
  - IPC handoff between Setup Manager and Tool Library unchanged
  - Excel import/export format unchanged
  - User workflows (CRUD, preview, switching) identical
- **Migration strategy**:
  - Phase in via adapters during refactor phases
  - Retire adapters only after parity tests pass
  - Deprecation tracking with explicit removal target dates

---

## Phase System

Work is divided into 10 phases, each with specific deliverables, acceptance criteria, and permissible scope.

### Phase 0: Baseline and Freeze Rules
- Measure file sizes, import violations, duplicate signatures (baseline)
- Define explicit non-negotiables: additive migrations, no cross-app direct imports, no behavior loss
- Lock in backwards-compatibility strategy
- **Outcome**: Baseline metrics + frozen rules document

### Phase 1: Domain Module Contracts
- Draft formal contracts for TOOLS and JAWS: public APIs, data shapes, lifecycle, allowed dependencies
- Outcome: `contracts.py` per module, acceptance tests proving compliance

### Phase 2: Module Governance Artifacts
- Machine-readable: module registry, ADRs, deprecation tracker, ownership map
- Wire new checks into quality gate
- Outcome: Enforceable boundary rules; agents can validate compliance

### Phase 3: Shared Module Platform Layer
- Build reusable abstractions: `CatalogPageBase`, `EditorDialogBase`, `CatalogDelegate`, `SelectorState`, `ExportSpecification`
- Keep TOOLS/JAWS running on current code via adapters; platform hardens in parallel
- Outcome: Platform layer tested without breaking existing apps

### Phase 4: TOOLS Migration (Pilot)
- Migrate TOOLS to use platform layer
- Preserve DB schema and UI behavior via adapters
- Reduce monolithic files to thin orchestrators
- Outcome: TOOLS fully using platform; parity tests pass

### Phase 5: JAWS Migration
- Port JAWS to platform, eliminating duplication with TOOLS
- Preserve jaw-specific behavior (preview plane, spindle filters) as configuration
- Outcome: JAWS using platform; no behavioral regression

### Phase 6: Data/Migration Segmentation
- Split migration ownership into explicit domain entry points
- Maintain backward compatibility; keep old upgrade paths working
- Outcome: Clean migration routing; future domains can add schemas independently

### Phase 7: AI-Agent Hardening
- Add entrypoint index, public API lists, contribution checklists per module
- Extend boundary checks to validate extension points
- Outcome: Agents can navigate codebase deterministically

### Phase 8: Legacy Coupling Retirement
- Remove temporary adapters, duplicated support modules after parity proof
- Track retirement with explicit criteria and dates
- Outcome: Clean codebase; all legacy code retired with proof

### Phase 9: Future Domain Onboarding Template
- Deliver documented pattern for adding new domains (Fixtures, etc.)
- Capture service/UI/export/migration/test contracts
- Outcome: Repeatable template for 5+ new domains

---

## Success Criteria

### By End of Phase 5 (JAWS Migration):
- ✅ HomePage: 1500L → 300-400L (80% reduction); JawPage: 1300L → 300-400L
- ✅ No import inside `ui/home_page_support/`, `ui/jaw_page_support/` from each other
- ✅ Selector bug in one domain automatically fixed for all
- ✅ Duplicate signatures in delegates/services dropped to baseline + 5% threshold
- ✅ Excel import/export works identically to today
- ✅ CRUD workflows unchanged
- ✅ Existing `.db` files open without migration
- ✅ Agents can read `contracts.py` and implement domain logic without copy-pasting

### By End of Phase 9 (Future Template):
- ✅ New domain (Fixtures) can be added in ~1000 lines, 1 week
- ✅ Shared platform used for 3 domains (tools, jaws, fixtures) with minimal duplication
- ✅ All boundary rules enforced by quality gate
- ✅ Code reduction from ~9000L core to ~5500L core (39% smaller)

---

## Out of Scope (First Program Increment)

- ❌ Merging tools and jaws into single database table (too risky; Phase B architecture only)
- ❌ Cross-app data ownership changes
- ❌ New features while refactoring (must prove parity first)
- ❌ Rewriting existing workflows (preservation only)
- ❌ Removing Setup Manager's read-only access to tool/jaw master data

---

## Risk Mitigation

1. **Adapter fallback paths**: Each phase ships with adapters so old code paths still work during transition
2. **Parity gates**: Don't retire legacy code until acceptance tests prove identical behavior
3. **Regression snapshots**: Key workflows captured at baseline; run before/after each phase
4. **Phase sequencing**: Each phase depends on prior completion; no parallel code rewrite of overlapping domains
5. **Deprecation tracking**: Explicit removal dates tied to phase gates; no surprises

---

## Further Reading

- [TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md](TOOLS_JAWS_MODULAR_OVERHAUL_RULES.md) — constraints and guidelines for agents
- [TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md](TOOLS_JAWS_MODULAR_OVERHAUL_STATUS.md) — current phase status and blockers
- [AGENTS.md](../AGENTS.md) — canonical import rules and validation commands
- Architecture-Map.json — machine-readable ownership/dependency baseline

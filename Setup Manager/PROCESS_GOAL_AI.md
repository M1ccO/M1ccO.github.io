# Process Goal (Refactor Program)

## Objective
Refactor main modules to be smaller, modular, and easier to evolve across machine variants, while preserving behavior and database compatibility.

## Technical Targets
- Split oversized UI/dialog files by responsibility.
- Replace repeated widget-construction blocks with shared builders/spec-driven layout rules.
- Centralize compatibility mapping (legacy DB fields <-> editor view-model).
- Gate UI/features by machine profile (capability-driven composition).
- Remove dead/forced abstractions and unreachable paths.
- Keep comments short and only on non-obvious logic.

## Constraints
- Keep Python + PySide6 architecture.
- Keep existing DB contract; additive-only migrations.
- Keep Setup Manager as reference consumer of Tool/Jaw master data.
- No broad framework rewrite.

## Definition of Success
1. Same user workflows and outputs for current NTX profile.
2. Reduced module size and duplicate logic in main editors/pages.
3. New machine variants can disable unsupported fields by profile, not by ad-hoc condition chains.
4. Cross-app switching and selector flows stay stable.

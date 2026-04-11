# Setup Manager — AI Quick Spec

## Product Contract
- App role: operational setup + run-history manager.
- Tool/Jaw authoring is out-of-scope (belongs to sibling Tool Library).
- External tool/jaw DB access must stay read-only.

## Non-Negotiables
- Do not add tool/jaw master schema to Setup Manager DB.
- Do not write into Tool Library DB files.
- Keep migrations additive-only.
- Keep work rows ID-reference based.

## Core Paths
- `main.py`: bootstrap.
- `config.py`: canonical paths + server names.
- `data/migrations.py`: setup schema.
- `services/work_service.py`: works CRUD.
- `services/logbook_service.py`: logbook CRUD + serial.
- `services/draw_service.py`: drawing + read-only master refs.
- `ui/main_window.py`: navigation + Tool Library IPC handoff.
- `ui/setup_page.py`, `ui/work_editor_dialog.py`, `ui/logbook_page.py`.

## IPC / Handoff
- Setup Manager <-> Tool Library switch uses local IPC (`QLocalSocket`/`QLocalServer`).
- Preserve existing handoff flow; avoid hardcoded window-title automation.
- If handoff fails, surface explicit errors (no silent swallow).

## Change Strategy
- Prefer small, behavior-preserving refactors.
- Extract repeated UI/build logic into support modules.
- Remove dead code only after call-site check.
- Add comments only for non-obvious compatibility or machine-specific logic.

## Done Criteria for Any Change
1. `py_compile` passes for touched modules.
2. Setup Manager opens Tool Library and returns.
3. Work editor load/save unchanged.
4. Logbook add/filter/export unchanged.

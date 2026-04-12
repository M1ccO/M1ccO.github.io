# Shim Retirement Policy

## Purpose
Temporary compatibility shims are allowed only to support in-flight migrations. They must be removed quickly to keep AI-agent edits deterministic.

## Rules
1. Every shim must include a clear removal note in its header comment.
2. Every shim must have an owner and target removal phase/date in the related task.
3. Shims that only forward imports are allowed for one cleanup cycle maximum.
4. New feature work must not target shim paths.

## Removal Gates
A shim can be deleted when all conditions are met:
1. No repository import references remain to the shim path.
2. Import-path checker passes with zero legacy-path violations.
3. Smoke-test runner passes in both app roots.
4. CI quality gate passes on pull request.

## Enforcement
- Local: `python scripts/run_quality_gate.py`
- CI: `.github/workflows/quality-gate.yml`

## Exception Process
If a shim must stay longer:
1. Add explicit exception note and reason.
2. Add target removal milestone.
3. Re-approve exception in next cleanup cycle.

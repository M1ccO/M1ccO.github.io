## Summary
- [ ] Briefly describe what changed and why.

## Agent Safety Checklist
- [ ] Shared import policy respected (`shared.*` canonical paths used where applicable).
- [ ] `python scripts/import_path_checker.py` passes.
- [ ] `python scripts/run_quality_gate.py` passes.
- [ ] Duplicate baseline policy reviewed:
- [ ] No baseline change needed.
- [ ] Baseline reduced.
- [ ] Baseline increased with explicit justification.
- [ ] New collision signatures (if any) are tagged in `scripts/duplicate_baseline.json` as `intentional` or `refactor_target`.

## Risk Notes
- [ ] UI behavior verified in both apps for touched flows.
- [ ] Any app-boundary exceptions documented.

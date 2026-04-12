# Duplicate Reduction Plan

Goal: steadily reduce cross-app signature collisions below the current baseline while preserving behavior and app boundaries.

## Policy
- Keep `max_cross_app_signature_collisions` stable or lower.
- Every active collision signature must be tagged in `scripts/duplicate_baseline.json`.
- New collisions must be either removed or explicitly classified in the same PR.

## Prioritized Targets

### Wave 1 (highest ROI)
- Consolidate shared UI widget utilities duplicated in both apps under common modules.
- Focus signatures tagged as `refactor_target` from `ui/widgets/common.py` first.
- Expected impact: largest reduction with low behavior risk.

### Wave 2 (editor delegates and sizing)
- Unify duplicate list/delegate sizing patterns currently implemented separately in setup/tools catalog delegates.
- Move stable logic to shared UI helpers.

### Wave 3 (main-window visual helpers)
- Review tooltip style and light palette helper signatures.
- Keep app-specific appearance behavior where needed, but centralize common style hooks.

## Execution Strategy
1. Pick 3 to 5 `refactor_target` signatures per PR.
2. Extract to canonical `shared.*` modules.
3. Rewire both apps to the shared implementation.
4. Run quality gate.
5. If collisions decreased, update baseline downward.

## Baseline Update Rules
- Use `python scripts/duplicate_detector.py --update-baseline` only after intentional changes.
- Baseline increase requires explicit rationale in PR description.
- Baseline decrease should be the default outcome for extraction PRs.

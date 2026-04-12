from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP_ROOT = ROOT / "Setup Manager"
TOOLS_ROOT = ROOT / "Tools and jaws Library"

EXCLUDE_PARTS = {".git", ".venv", "__pycache__", ".runtime", ".codex"}
BASELINE_PATH = ROOT / "scripts" / "duplicate_baseline.json"

DEFAULT_BASELINE = {
    "max_cross_app_signature_collisions": 0,
    "classification": {
        "intentional": [],
        "refactor_target": [],
    },
}


def iter_py_files(base: Path):
    for path in base.rglob("*.py"):
        parts = set(path.parts)
        if parts & EXCLUDE_PARTS:
            continue
        yield path


def function_fingerprints(base: Path):
    items: dict[str, list[str]] = {}
    for path in iter_py_files(base):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            continue
        rel = path.relative_to(base).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                try:
                    node_src = ast.get_source_segment(source, node) or ""
                except Exception:
                    node_src = ""
                sig = f"{type(node).__name__}:{node.name}:{hashlib.sha1(node_src.encode('utf-8')).hexdigest()}"
                items.setdefault(sig, []).append(rel)
    return items


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return dict(DEFAULT_BASELINE)
    try:
        payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_BASELINE)
    if not isinstance(payload, dict):
        return dict(DEFAULT_BASELINE)

    normalized = dict(DEFAULT_BASELINE)
    normalized.update(payload)

    classification = payload.get("classification")
    if not isinstance(classification, dict):
        classification = {}
    normalized["classification"] = {
        "intentional": list(classification.get("intentional", [])),
        "refactor_target": list(classification.get("refactor_target", [])),
    }
    return normalized


def save_baseline(max_collisions: int) -> None:
    payload = load_baseline()
    payload["max_cross_app_signature_collisions"] = int(max_collisions)
    payload["notes"] = "Fail when collisions exceed this baseline. Tag each baseline signature by intent."
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def classify_signatures(signatures: set[str], baseline: dict) -> tuple[dict[str, str], list[str], list[str]]:
    classification = baseline.get("classification") or {}
    if not isinstance(classification, dict):
        classification = {}

    tag_map: dict[str, str] = {}
    stale_signatures: list[str] = []
    for tag in ("refactor_target", "intentional"):
        tagged = classification.get(tag, [])
        if not isinstance(tagged, list):
            continue
        for sig in tagged:
            if not isinstance(sig, str):
                continue
            if sig in signatures:
                # If duplicate tags exist, refactor_target wins (processed first).
                tag_map.setdefault(sig, tag)
            else:
                stale_signatures.append(sig)

    unclassified = sorted(signatures - set(tag_map.keys()))
    return tag_map, sorted(set(stale_signatures)), unclassified


def main() -> int:
    update_mode = "--update-baseline" in set(sys.argv[1:])
    setup_fp = function_fingerprints(SETUP_ROOT)
    tools_fp = function_fingerprints(TOOLS_ROOT)

    collisions = []
    for sig, setup_paths in setup_fp.items():
        tools_paths = tools_fp.get(sig)
        if not tools_paths:
            continue
        collisions.append((sig, sorted(set(setup_paths)), sorted(set(tools_paths))))

    collisions.sort(key=lambda item: item[0])

    print(f"duplicate-detector: cross-app-signature-collisions={len(collisions)}")
    for sig, setup_paths, tools_paths in collisions[:50]:
        print(f"- {sig}")
        print(f"  setup: {', '.join(setup_paths)}")
        print(f"  tools: {', '.join(tools_paths)}")

    if update_mode:
        save_baseline(len(collisions))
        print(f"duplicate-detector: baseline updated at {BASELINE_PATH}")
        return 0

    baseline = load_baseline()
    max_collisions = int(baseline.get("max_cross_app_signature_collisions", 0))
    print(f"duplicate-detector: allowed-max-collisions={max_collisions}")

    collision_signatures = {sig for sig, _, _ in collisions}
    tag_map, stale_signatures, unclassified = classify_signatures(collision_signatures, baseline)
    refactor_count = sum(1 for sig in collision_signatures if tag_map.get(sig) == "refactor_target")
    intentional_count = sum(1 for sig in collision_signatures if tag_map.get(sig) == "intentional")
    print(
        "duplicate-detector: classification "
        f"refactor_target={refactor_count} intentional={intentional_count} unclassified={len(unclassified)}"
    )

    if stale_signatures:
        print(f"duplicate-detector: stale-tagged-signatures={len(stale_signatures)}")

    if len(collisions) > max_collisions:
        print(
            "duplicate-detector: FAILED - collisions exceed baseline. "
            "Run with --update-baseline only when intentionally accepting a new baseline."
        )
        return 1

    if unclassified:
        print("duplicate-detector: FAILED - unclassified collisions detected. Tag them in scripts/duplicate_baseline.json.")
        for sig in unclassified[:20]:
            print(f"  - {sig}")
        return 1

    print("duplicate-detector: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

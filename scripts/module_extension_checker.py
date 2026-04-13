"""
module_extension_checker.py — Phase 7 quality gate extension.

Validates platform extension points so agents cannot add ad-hoc subclasses or
silently skip required abstract override methods.

Rules:
  1. Only classes registered in docs/module-extension-points.json may subclass:
     - CatalogPageBase
     - CatalogDelegate
     - EditorDialogBase
  2. Each registered class must exist and inherit from the declared base.
  3. Each registered class must define required override methods.

Exit code 0 = all checks pass.
Exit code 1 = one or more violations found.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_APP = ROOT / "Tools and jaws Library"
EXTENSION_POINTS_FILE = TOOLS_APP / "docs" / "module-extension-points.json"

TRACKED_BASES = {"CatalogPageBase", "CatalogDelegate", "EditorDialogBase"}
EXCLUDED_DIR_PARTS = {".git", ".venv", "__pycache__", ".runtime", ".codex", "scripts", "tests"}


class ExtensionClassInfo:
    def __init__(self, rel_path: str, class_name: str, base_name: str, methods: set[str]) -> None:
        self.rel_path = rel_path
        self.class_name = class_name
        self.base_name = base_name
        self.methods = methods


def _is_excluded(path: Path) -> bool:
    return bool(set(path.parts) & EXCLUDED_DIR_PARTS)


def _base_name(base_node: ast.expr) -> str | None:
    if isinstance(base_node, ast.Name):
        return base_node.id
    if isinstance(base_node, ast.Attribute):
        return base_node.attr
    if isinstance(base_node, ast.Subscript):
        return _base_name(base_node.value)
    if isinstance(base_node, ast.Call):
        return _base_name(base_node.func)
    return None


def _collect_platform_subclasses() -> list[ExtensionClassInfo]:
    collected: list[ExtensionClassInfo] = []
    for py_file in TOOLS_APP.glob("**/*.py"):
        if not py_file.is_file() or _is_excluded(py_file):
            continue
        try:
            source = py_file.read_text(encoding="utf-8-sig", errors="ignore")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        rel_path = py_file.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            base_names = {_base_name(base) for base in node.bases}
            tracked = [name for name in base_names if name in TRACKED_BASES]
            if not tracked:
                continue

            methods = {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for base_name in tracked:
                collected.append(
                    ExtensionClassInfo(
                        rel_path=rel_path,
                        class_name=node.name,
                        base_name=base_name,
                        methods=methods,
                    )
                )
    return collected


def _load_extension_specs() -> list[dict]:
    if not EXTENSION_POINTS_FILE.exists():
        raise FileNotFoundError(f"Missing extension points file: {EXTENSION_POINTS_FILE}")
    text = EXTENSION_POINTS_FILE.read_text(encoding="utf-8-sig")
    payload = json.loads(text)
    entries = payload.get("extensions")
    if not isinstance(entries, list):
        raise ValueError("module-extension-points.json must contain an 'extensions' list")
    return entries


def check_extensions() -> list[str]:
    issues: list[str] = []
    discovered = _collect_platform_subclasses()

    try:
        specs = _load_extension_specs()
    except Exception as exc:
        return [f"  [E-000] Failed to load extension spec: {exc}"]

    discovered_map = {
        (item.rel_path, item.class_name, item.base_name): item for item in discovered
    }

    allowed_keys: set[tuple[str, str, str]] = set()
    for spec in specs:
        rel_file = f"Tools and jaws Library/{spec.get('file', '').strip()}"
        class_name = str(spec.get("class", "")).strip()
        base_name = str(spec.get("base", "")).strip()
        required_methods = spec.get("required_methods") or []

        key = (rel_file, class_name, base_name)
        allowed_keys.add(key)

        if base_name not in TRACKED_BASES:
            issues.append(
                f"  [E-001] Invalid base '{base_name}' in extension spec for {rel_file}:{class_name}."
            )
            continue

        discovered_item = discovered_map.get(key)
        if discovered_item is None:
            issues.append(
                f"  [E-002] Registered extension class not found or base mismatch: "
                f"{rel_file}:{class_name} ({base_name})."
            )
            continue

        missing_methods = [name for name in required_methods if name not in discovered_item.methods]
        if missing_methods:
            issues.append(
                f"  [E-003] Missing required overrides in {rel_file}:{class_name} -> {', '.join(missing_methods)}"
            )

    for item in discovered:
        key = (item.rel_path, item.class_name, item.base_name)
        if key in allowed_keys:
            continue
        issues.append(
            f"  [E-004] Unregistered platform extension class: "
            f"{item.rel_path}:{item.class_name} ({item.base_name})."
        )

    return issues


def main() -> int:
    issues = check_extensions()
    if issues:
        print("module-extension-checker: FAILED\n")
        for issue in issues:
            print(issue)
        print(f"\n{len(issues)} extension-point violation(s).")
        return 1

    print("module-extension-checker: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

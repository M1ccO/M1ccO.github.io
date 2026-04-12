from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PY_GLOB = "**/*.py"

DENY_PATTERNS = {
    "legacy_shared_editor_helpers": re.compile(r"\bfrom\s+shared\.editor_helpers\s+import\b"),
    "legacy_shared_editor_table": re.compile(r"\bfrom\s+shared\.editor_table\s+import\b"),
    "legacy_shared_editor_table_sanity": re.compile(r"\bfrom\s+shared\.editor_table_sanity\s+import\b"),
    "legacy_shared_mini_assignment": re.compile(r"\bfrom\s+shared\.mini_assignment_card\s+import\b"),
    "legacy_shared_model_paths": re.compile(r"\bfrom\s+shared\.model_paths\s+import\b"),
    "legacy_services_localization": re.compile(r"\bfrom\s+services\.localization_service\s+import\b"),
    "legacy_services_ui_preferences": re.compile(r"\bfrom\s+services\.ui_preferences_service\s+import\b"),
    "legacy_ui_stl_preview": re.compile(r"\bfrom\s+ui\.stl_preview\s+import\b"),
}

CROSS_APP_PATTERNS = {
    "cross_import_setup_from_tools": re.compile(r"\bfrom\s+Setup\s+Manager\."),
    "cross_import_tools_from_setup": re.compile(r"\bfrom\s+Tools\s+and\s+jaws\s+Library\."),
}


EXCLUDE_DIR_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".runtime",
    ".codex",
}


def iter_py_files(root: Path):
    for path in root.glob(PY_GLOB):
        if not path.is_file():
            continue
        parts = set(path.parts)
        if parts & EXCLUDE_DIR_PARTS:
            continue
        yield path


def line_violations(path: Path, text: str):
    violations: list[tuple[int, str, str]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        for rule_name, pattern in DENY_PATTERNS.items():
            if pattern.search(line):
                violations.append((idx, rule_name, line.strip()))
        for rule_name, pattern in CROSS_APP_PATTERNS.items():
            if pattern.search(line):
                violations.append((idx, rule_name, line.strip()))
    return violations


def main() -> int:
    found = []
    for path in iter_py_files(ROOT):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        violations = line_violations(path, text)
        for line_no, rule_name, line_text in violations:
            found.append((path.relative_to(ROOT).as_posix(), line_no, rule_name, line_text))

    if not found:
        print("import-path-checker: OK")
        return 0

    print("import-path-checker: FAILED")
    for rel_path, line_no, rule_name, line_text in found:
        print(f"- {rel_path}:{line_no} [{rule_name}] {line_text}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

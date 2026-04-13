"""
module_boundary_checker.py — Phase 2 quality gate extension.

Checks intra-app module boundaries that import_path_checker.py does NOT cover:
  1. TOOLS domain must not import from JAWS domain (and vice versa).
  2. home_page_support/ must not import from jaw_page_support/ (and vice versa).
  3. Intra-app schema coupling: Setup Manager services must not query Tool Library tables directly.
  4. Adapter registry: warn if new adapters appear outside of known locations.

Exit code 0 = all checks pass.
Exit code 1 = one or more violations found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_APP = ROOT / "Tools and jaws Library"
SETUP_APP = ROOT / "Setup Manager"

EXCLUDE_DIR_PARTS = {".git", ".venv", "__pycache__", ".runtime", ".codex", "scripts", "tests"}

# ---------------------------------------------------------------------------
# Rule definitions
# Each rule is:
#   (rule_id, description, scope_glob, forbidden_pattern_re)
# scope_glob: glob relative to ROOT selecting which files to check.
# forbidden_pattern_re: compiled regex applied to each source line.
# ---------------------------------------------------------------------------

BOUNDARY_RULES: list[tuple[str, str, str, re.Pattern]] = [

    # Rule B-001: Jaw domain files must not import from tool-domain support modules
    (
        "B-001",
        "JAWS domain must not import from home_page_support/ (TOOLS support dir)",
        "Tools and jaws Library/ui/jaw_page_support/**/*.py",
        re.compile(r"\bfrom\s+[.\s]*home_page_support\b"),
    ),
    (
        "B-001b",
        "JAWS domain must not import from home_page_support/ (absolute)",
        "Tools and jaws Library/ui/jaw_page.py",
        re.compile(r"\bfrom\s+[.\s]*home_page_support\b"),
    ),

    # Rule B-002: Tool domain files must not import from jaw-domain support modules
    (
        "B-002",
        "TOOLS domain must not import from jaw_page_support/ (JAWS support dir)",
        "Tools and jaws Library/ui/home_page_support/**/*.py",
        re.compile(r"\bfrom\s+[.\s]*jaw_page_support\b"),
    ),
    (
        "B-002b",
        "TOOLS domain must not import from jaw_page_support/ (absolute)",
        "Tools and jaws Library/ui/home_page.py",
        re.compile(r"\bfrom\s+[.\s]*jaw_page_support\b"),
    ),

    # Rule B-003: Tool service must not import from jaw service
    (
        "B-003",
        "ToolService must not import JawService (cross-domain service coupling)",
        "Tools and jaws Library/services/tool_service.py",
        re.compile(r"\bfrom\s+[.\s]*jaw_service\b|\bimport\s+jaw_service\b"),
    ),

    # Rule B-004: Jaw service must not import from tool service
    (
        "B-004",
        "JawService must not import ToolService (cross-domain service coupling)",
        "Tools and jaws Library/services/jaw_service.py",
        re.compile(r"\bfrom\s+[.\s]*tool_service\b|\bimport\s+tool_service\b"),
    ),

    # Rule B-005: Setup Manager services must not directly query Tool Library table names
    # Exemption: draw_service.py is the designated cross-DB read-only service (ADR-002).
    # This rule fires on any OTHER service in Setup Manager that queries tools/jaws tables.
    (
        "B-005",
        "Setup Manager services (except draw_service.py) must not query Tool Library DB table 'tools' directly",
        "Setup Manager/services/*.py",
        re.compile(r'execute\s*\(\s*["\'].*\bFROM\s+tools\b', re.IGNORECASE),
    ),
    (
        "B-005b",
        "Setup Manager services (except draw_service.py) must not query Tool Library DB table 'jaws' directly",
        "Setup Manager/services/*.py",
        re.compile(r'execute\s*\(\s*["\'].*\bFROM\s+jaws\b', re.IGNORECASE),
    ),

    # Rule B-006: jaw_editor_dialog must not import from tool_editor_support
    (
        "B-006",
        "jaw_editor_dialog.py must not import from tool_editor_support/",
        "Tools and jaws Library/ui/jaw_editor_dialog.py",
        re.compile(r"\bfrom\s+[.\s]*tool_editor_support\b|\bimport\s+tool_editor_support\b"),
    ),

    # Rule B-007: tool_editor_dialog must not import from jaw_editor_support (if it exists)
    (
        "B-007",
        "tool_editor_dialog.py must not import from jaw_editor_support/",
        "Tools and jaws Library/ui/tool_editor_dialog.py",
        re.compile(r"\bfrom\s+[.\s]*jaw_editor_support\b|\bimport\s+jaw_editor_support\b"),
    ),
]

# ---------------------------------------------------------------------------
# Adapter registry: known adapter locations. Warn if adapter-pattern detected
# outside of these files.
# ---------------------------------------------------------------------------
KNOWN_ADAPTER_FILES = {
    "Tools and jaws Library/ui/jaw_export_page.py",
    "Setup Manager/ui/work_editor_support/model.py",
}

# Regex to detect new private adapter classes (class _SomethingAdapter(...))
ADAPTER_CLASS_PATTERN = re.compile(r"^class\s+_\w+Adapter\b")


def _is_excluded(path: Path) -> bool:
    return bool(set(path.parts) & EXCLUDE_DIR_PARTS)


def _iter_glob(pattern: str) -> list[Path]:
    """Expand a scope glob from ROOT, skip excluded dirs."""
    results = []
    for p in ROOT.glob(pattern):
        if p.is_file() and not _is_excluded(p):
            results.append(p)
    return results


def check_boundary_rules() -> list[str]:
    violations: list[str] = []
    # draw_service.py is the designated cross-DB read-only reader in Setup Manager (ADR-002).
    DRAW_SERVICE_EXEMPTION = "draw_service.py"
    for rule_id, description, scope_glob, pattern in BOUNDARY_RULES:
        files = _iter_glob(scope_glob)
        for fpath in files:
            # Exempt draw_service.py from schema-coupling rules B-005/B-005b
            if rule_id in ("B-005", "B-005b") and fpath.name == DRAW_SERVICE_EXEMPTION:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    rel = fpath.relative_to(ROOT)
                    violations.append(
                        f"  [{rule_id}] {description}\n"
                        f"    -> {rel}:{lineno}: {line.strip()}"
                    )
    return violations


def check_adapter_registry() -> list[str]:
    """Warn about new private adapter classes outside known locations."""
    warnings: list[str] = []
    for fpath in ROOT.glob("**/*.py"):
        if not fpath.is_file() or _is_excluded(fpath):
            continue
        rel_str = fpath.relative_to(ROOT).as_posix()
        if rel_str in KNOWN_ADAPTER_FILES:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if ADAPTER_CLASS_PATTERN.match(line.strip()):
                warnings.append(
                    f"  [B-008] New private adapter class detected outside known adapter files.\n"
                    f"    -> {rel_str}:{lineno}: {line.strip()}\n"
                    f"    -> If intentional, add to KNOWN_ADAPTER_FILES in module_boundary_checker.py and deprecations.json."
                )
    return warnings


def main() -> int:
    violations = check_boundary_rules()
    adapter_warnings = check_adapter_registry()

    all_issues = violations + adapter_warnings

    if all_issues:
        print("module-boundary-checker: FAILED\n")
        for issue in all_issues:
            print(issue)
        print(f"\n{len(violations)} boundary violation(s), {len(adapter_warnings)} unregistered adapter(s).")
        return 1

    print("module-boundary-checker: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

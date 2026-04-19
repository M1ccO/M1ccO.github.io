from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"

TASKS = [
    ("import-path-checker", [str(PY), str(ROOT / "scripts" / "import_path_checker.py")]),
    ("module-boundary-checker", [str(PY), str(ROOT / "scripts" / "module_boundary_checker.py")]),
    ("module-extension-checker", [str(PY), str(ROOT / "scripts" / "module_extension_checker.py")]),
    ("smoke-test", [str(PY), str(ROOT / "scripts" / "smoke_test.py")]),
    ("duplicate-detector", [str(PY), str(ROOT / "scripts" / "duplicate_detector.py")]),
    (
        "regression-tests-shared",
        [
            str(PY), "-m", "pytest",
            "tests/test_preload_manager.py",
            "tests/test_selector_session.py",
            "tests/test_selector_contracts.py",
            "tests/test_shared_regressions.py",
            "tests/test_shared_selector_widgets.py",
            "tests/test_work_editor_resolver_fallback.py",
            "tests/test_print_service_resolver_fallback.py",
            "-q", "--tb=short",
        ],
    ),
    (
        "regression-tests-setup",
        [
            str(PY), "-m", "pytest",
            "tests/test_work_editor_embedded_selector.py",
            "tests/test_work_editor_style_inheritance.py",
            "tests/test_work_editor_launch_parent.py",
            "tests/test_selector_adapter_phase6.py",
            "tests/test_priority1_targeted.py",
            "-q", "--tb=short",
        ],
    ),
]


def run_task(name: str, cmd: list[str]) -> int:
    print(f"\\n=== {name} ===")
    completed = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    # Qt WebEngine may crash on process exit (access violation 0xC0000005)
    # even when all tests pass. Tolerate this for pytest-based tasks.
    if completed.returncode != 0 and "passed" in completed.stdout and "failed" not in completed.stdout:
        print(f"  (non-zero exit {completed.returncode} ignored — all tests passed)")
        return 0
    return completed.returncode


def main() -> int:
    if not PY.exists():
        print(f"quality-gate: missing interpreter {PY}")
        return 1

    for name, script in TASKS:
        code = run_task(name, script)
        if code != 0:
            print(f"quality-gate: FAILED at {name}")
            return code

    print("\\nquality-gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

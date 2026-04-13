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
        "regression-tests",
        [str(PY), "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
    ),
]


def run_task(name: str, cmd: list[str]) -> int:
    print(f"\\n=== {name} ===")
    completed = subprocess.run(cmd, cwd=str(ROOT))
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

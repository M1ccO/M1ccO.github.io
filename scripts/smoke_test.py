from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"

COMPILE_TARGETS = [
    ROOT / "Setup Manager" / "main.py",
    ROOT / "Setup Manager" / "ui" / "main_window.py",
    ROOT / "Tools and jaws Library" / "main.py",
    ROOT / "Tools and jaws Library" / "ui" / "main_window.py",
    ROOT / "shared" / "services" / "localization_service.py",
    ROOT / "shared" / "services" / "ui_preferences_service.py",
    ROOT / "shared" / "ui" / "stl_preview.py",
    ROOT / "shared" / "ui" / "helpers" / "editor_helpers.py",
    ROOT / "shared" / "ui" / "helpers" / "editor_table.py",
    ROOT / "shared" / "data" / "model_paths.py",
]


def compile_checks() -> None:
    for target in COMPILE_TARGETS:
        py_compile.compile(str(target), doraise=True)


def run_import_smoke(cwd: Path, code: str) -> None:
    cmd = [str(PY), "-c", code]
    completed = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Import smoke failed in {cwd}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def main() -> int:
    if not PY.exists():
        print(f"smoke-test: missing interpreter {PY}")
        return 1

    try:
        compile_checks()
        run_import_smoke(
            ROOT / "Setup Manager",
            "from ui.main_window import MainWindow; from shared.ui.stl_preview import StlPreviewWidget; print('setup-smoke-ok')",
        )
        run_import_smoke(
            ROOT / "Tools and jaws Library",
            "from ui.main_window import MainWindow; from ui.jaw_page import JawPage; from shared.ui.stl_preview import StlPreviewWidget; print('tools-smoke-ok')",
        )
    except Exception as exc:
        print(f"smoke-test: FAILED\n{exc}")
        return 1

    print("smoke-test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

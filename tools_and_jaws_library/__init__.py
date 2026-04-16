from __future__ import annotations

from pathlib import Path

# TEMP SHIM (embedded-selector parity migration):
# Expose "Tools and jaws Library" under a valid package name so selector
# modules can be imported with package-relative paths in-process.
_REAL_PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "Tools and jaws Library"
__path__ = [str(_REAL_PACKAGE_ROOT)]

"""Always-on lightweight runtime trace for Library editor CRUD paths.

Gated by env var NTX_RUNTIME_TRACE. Writes to Library/Setup Manager app.log
via stdlib logging plus optional explicit file at NTX_RUNTIME_TRACE_FILE.

Keep logging minimal and guarded — production runs set the env var off.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

LOG = logging.getLogger("ntx.runtime_trace")
_START = time.monotonic()
_ENABLED_VALUES = {"1", "true", "yes", "on", "debug"}


def runtime_trace_enabled() -> bool:
    value = os.environ.get("NTX_RUNTIME_TRACE", "")
    return value.strip().lower() in _ENABLED_VALUES


def _trace_file_path() -> Path | None:
    configured = os.environ.get("NTX_RUNTIME_TRACE_FILE", "").strip()
    if configured:
        return Path(configured)
    return None


def _safe(value: Any) -> str:
    try:
        text = str(value)
    except Exception:
        text = repr(value)
    if len(text) > 400:
        text = text[:400] + "...<truncated>"
    return text.replace("\n", "\\n").replace("\r", "\\r")


def rtrace(event: str, **fields: Any) -> None:
    """Emit one runtime trace line when NTX_RUNTIME_TRACE is enabled."""
    if not runtime_trace_enabled():
        return

    parts = [
        f"wall={datetime.now().isoformat(timespec='milliseconds')}",
        f"t_ms={int((time.monotonic() - _START) * 1000)}",
        f"event={event}",
    ]
    for key, value in fields.items():
        parts.append(f"{key}={_safe(value)!r}")
    line = " ".join(parts)

    LOG.warning("rtrace %s", line)

    path = _trace_file_path()
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            LOG.exception("rtrace file write failed path=%s", path)


__all__ = ["rtrace", "runtime_trace_enabled"]

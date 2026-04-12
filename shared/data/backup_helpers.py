"""Shared backup helpers for .bak rotation and creation."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def prune_backups(db_path: Path, tag: str, keep: int = 5) -> None:
    """Delete old .bak files beyond *keep* most-recent for *tag*."""
    prefix = f"{db_path.stem}_{tag}_"
    backups = sorted(
        db_path.parent.glob(f"{prefix}*.bak"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for stale in backups[keep:]:
        try:
            stale.unlink()
        except Exception:
            pass


def create_db_backup(db_path: Path, tag: str, keep: int = 5) -> Path:
    """Create a timestamped .bak copy of *db_path* and prune old backups."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_{tag}_{timestamp}.bak"
    shutil.copy2(db_path, backup_path)
    prune_backups(db_path, tag, keep)
    return backup_path

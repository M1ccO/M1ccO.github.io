from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def resolve_icon_path_with_fallback(path_like) -> Path | None:
    path = Path(path_like)
    candidates = [path]
    suffix = path.suffix.lower()
    if suffix == '.svg':
        candidates.append(path.with_suffix('.png'))
    elif suffix == '.png':
        candidates.append(path.with_suffix('.svg'))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def icon_from_path(path_like, *, size: QSize | None = None) -> QIcon:
    resolved = resolve_icon_path_with_fallback(path_like)
    if resolved is None:
        return QIcon()

    if resolved.suffix.lower() != '.svg':
        return QIcon(str(resolved))

    # Render SVG directly to pixmap so icons still load when the Qt SVG icon
    # engine plugin is unavailable in a given runtime/startup path.
    renderer = QSvgRenderer(str(resolved))
    if not renderer.isValid():
        png_fallback = resolved.with_suffix('.png')
        return QIcon(str(png_fallback)) if png_fallback.exists() else QIcon()

    target = size if size is not None else QSize(28, 28)
    if target.width() <= 0 or target.height() <= 0:
        target = QSize(28, 28)

    pm = QPixmap(target)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return QIcon(pm)

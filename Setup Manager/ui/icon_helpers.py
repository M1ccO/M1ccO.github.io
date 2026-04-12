"""Toolbar icon loading utilities for the Setup Manager UI."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from config import ICONS_DIR, TOOL_LIBRARY_TOOL_ICONS_DIR


def svg_icon(path: Path, size: int = 24) -> QIcon:
    """Render an SVG file to a QIcon via QSvgRenderer."""
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def toolbar_icon(name: str, *, png_first: bool = True) -> QIcon:
    """Load a toolbar icon by name, searching app and shared icon directories.

    When *png_first* is True (default) PNG variants are preferred over SVG
    for better toolbar visibility.  Set to False to prefer SVG.
    """
    extensions = [("png", "svg")] if png_first else [("svg", "png")]
    dirs = [ICONS_DIR / "tools", TOOL_LIBRARY_TOOL_ICONS_DIR]

    for first_ext, second_ext in extensions:
        for icon_dir in dirs:
            candidate = icon_dir / f"{name}.{first_ext}"
            if candidate.exists():
                if first_ext == "svg":
                    return svg_icon(candidate)
                return QIcon(str(candidate))
        for icon_dir in dirs:
            candidate = icon_dir / f"{name}.{second_ext}"
            if candidate.exists():
                if second_ext == "svg":
                    return svg_icon(candidate)
                return QIcon(str(candidate))
    return QIcon()


def toolbar_icon_with_svg_render_fallback(name: str, size: int = 28) -> QIcon:
    """Load toolbar icons robustly even when Qt SVG image plugin is unavailable."""
    svg_candidates = [
        ICONS_DIR / "tools" / f"{name}.svg",
        TOOL_LIBRARY_TOOL_ICONS_DIR / "tools" / f"{name}.svg",
    ]
    for svg_path in svg_candidates:
        if not svg_path.exists():
            continue
        icon = QIcon(str(svg_path))
        if not icon.isNull():
            return icon
        renderer = QSvgRenderer(str(svg_path))
        if renderer.isValid():
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)

    png_candidates = [
        ICONS_DIR / "tools" / f"{name}.png",
        TOOL_LIBRARY_TOOL_ICONS_DIR / "tools" / f"{name}.png",
    ]
    for png_path in png_candidates:
        if png_path.exists():
            return QIcon(str(png_path))
    return QIcon()

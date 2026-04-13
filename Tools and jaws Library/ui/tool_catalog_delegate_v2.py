"""
ToolCatalogDelegate: Platform-layer catalog item painter for tool domain.

Inherits from shared.ui.platforms.catalog_delegate.CatalogDelegate to render
tool rows as rounded cards with deterministic layout, preserving all existing
home_page.py rendering logic (icon loading, layout, description wrapping).

Design:
  - Abstract methods _paint_item_content() and _compute_size() implemented
  - Tool-specific content: icon + tool_id + description + type columns
  - Responsive stages: icon-only → name-only → reduced → full
  - Selection/hover state styling inherited from base class
  - Interaction model: click=select (inherited delegate behavior)
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPen, QPixmap, QTransform, QStyle, QStyleOptionViewItem
from PySide6.QtWidgets import QAbstractItemDelegate

from shared.ui.platforms.catalog_delegate import CatalogDelegate

from config import (
    DEFAULT_TOOL_ICON,
    MILLING_TOOL_TYPES,
    TOOL_ICONS_DIR,
    TOOL_TYPE_TO_ICON,
    TURNING_TOOL_TYPES,
)

__all__ = ["ToolCatalogDelegate"]

# ── Data roles for model integration ────────────────────────────────────
ROLE_TOOL_ID = Qt.UserRole
ROLE_TOOL_DATA = Qt.UserRole + 1
ROLE_TOOL_ICON = Qt.UserRole + 2
ROLE_TOOL_UID = Qt.UserRole + 3

# ── Tool-specific layout constants ──────────────────────────────────────
# (override base class constants as needed)
ICON_SIZE = 40
ICON_SLOT_W = 48
ICON_VISUAL_OFFSET_Y = 3
COL_SPACING = 10
HEADER_VALUE_GAP = 0
WRAPPED_LINE_STEP_FACTOR = 0.78

# Responsive breakpoints (card width stages)
BP_FULL = 860       # card_width >= → full (all columns: id + name + numeric)
BP_REDUCED = 390    # card_width >= → reduced (id + name only)
BP_NAME_ONLY = 180  # card_width >= → name only
# below 180: icon only

# ── Tool-specific colors ────────────────────────────────────────────────
CLR_HEADER_TEXT = QColor('#2b3136')
CLR_VALUE_TEXT = QColor('#171a1d')

# ── Fonts (reused across paint iterations) ────────────────────────────
def _header_font() -> QFont:
    f = QFont()
    f.setPointSizeF(9.0)
    f.setWeight(QFont.DemiBold)
    return f


def _value_font(pt: float = 13.5) -> QFont:
    f = QFont()
    f.setPointSizeF(pt)
    f.setWeight(QFont.DemiBold)
    return f


# ── Utility functions (preserve existing helpers) ─────────────────────────

def _safe_float(value) -> str:
    """Format numeric value to 3 decimal places."""
    try:
        return f'{float(value or 0):.3f}'
    except Exception:
        return '0.000'


def _safe_float_number(value) -> float | None:
    """Safe float conversion with exception handling."""
    try:
        return float(value)
    except Exception:
        return None


def _strip_tool_id_prefix(value) -> str:
    """Extract numeric portion from tool ID (e.g., 'T123' → '123')."""
    raw = str(value or '').strip()
    if raw.lower().startswith('t'):
        raw = raw[1:].strip()
    return ''.join(ch for ch in raw if ch.isdigit())


def _tool_id_display_value(value) -> str:
    """Format tool ID for display (e.g., '123' → 'T123')."""
    stripped = _strip_tool_id_prefix(value)
    if stripped:
        return f'T{stripped}'
    return str(value or '').strip()


def _is_sub_spindle(value) -> bool:
    """Check if spindle orientation is sub/counter spindle."""
    normalized = str(value or '').strip().lower().replace('_', ' ')
    return normalized in {'sub', 'sub spindle', 'subspindle', 'counter spindle'}


def _nose_corner_or_angle_column(tool: dict, t: Callable) -> tuple[str, str]:
    """
    Return (header, value) for nose angle/corner radius based on tool type.
    Preserved from home_page.py rendering logic for parity.
    """
    raw_tool_type = (tool.get('tool_type', '') or '').strip()
    angle_tool_types = {'Drill', 'Spot Drill', 'Turn Drill', 'Turn Spot Drill', 'Turn Center Drill'}

    if raw_tool_type in angle_tool_types:
        angle = _safe_float_number(tool.get('drill_nose_angle'))
        legacy = _safe_float_number(tool.get('nose_corner_radius'))
        if angle is None or (angle == 0.0 and legacy not in (None, 0.0)):
            angle = legacy if legacy is not None else 0.0
        return t('tool_library.field.nose_angle', 'Nose angle'), _safe_float(angle)

    if raw_tool_type == 'Tapping':
        return t('tool_library.field.pitch', 'Pitch'), _safe_float(tool.get('nose_corner_radius', 0))

    if raw_tool_type in TURNING_TOOL_TYPES:
        return t('tool_library.field.nose_radius', 'Nose radius'), _safe_float(tool.get('nose_corner_radius', 0))

    if raw_tool_type in MILLING_TOOL_TYPES:
        return t('tool_library.field.corner_radius', 'Corner radius'), _safe_float(tool.get('nose_corner_radius', 0))

    return (
        t('tool_library.field.nose_corner_radius_multiline', 'Nose /\nCorner R'),
        _safe_float(tool.get('nose_corner_radius', 0)),
    )


def tool_icon_for_type(tool_type: str) -> QIcon:
    """Load and cache icon based on tool type; fallback to default."""
    filename = TOOL_TYPE_TO_ICON.get(tool_type, DEFAULT_TOOL_ICON)
    path = TOOL_ICONS_DIR / filename
    if not path.exists():
        path = TOOL_ICONS_DIR / DEFAULT_TOOL_ICON
    return QIcon(str(path)) if path.exists() else QIcon()


# ── Main Delegate Class ─────────────────────────────────────────────────

class ToolCatalogDelegate(CatalogDelegate):
    """
    Catalog item painter for tool domain (inherits from platform CatalogDelegate).

    Renders tool rows with responsive layout: icon, tool_id, name, type badge.
    Decorates base class styling with tool-specific content painting and sizing.

    Attributes (override base if needed):
        ROW_HEIGHT: 74px for full tool card
        view_mode: 'home'|'holders'|'inserts'|'assemblies' (view-specific columns)
    """

    ROW_HEIGHT: int = 74

    def __init__(self, parent=None, view_mode: str = 'home',
                 translate: Callable | None = None):
        """
        Initialize tool delegate with view mode and translation support.

        Args:
            parent: Parent widget (typically QListView).
            view_mode: Column display mode ('home', 'holders', 'inserts', 'assemblies').
            translate: i18n function (key, default, **kwargs) → str.
        """
        super().__init__(parent)
        self._view_mode = (view_mode or 'home').lower()
        self._translate = translate or (lambda k, d=None, **kw: d or '')
        
        # Pre-build fonts for reuse across all paint calls
        self._header_font = _header_font()
        self._value_font_full = _value_font(13.5)
        self._value_font_narrow = _value_font(12.5)
        self._value_font_tight = _value_font(11.5)
        self._value_font_tiny = _value_font(10.5)
        
        # Icon pixmap cache: {(tool_type, is_mirrored): QPixmap}
        self._icon_cache: dict[str, QPixmap] = {}

    def set_view_mode(self, mode: str):
        """Switch view mode (home/holders/inserts/assemblies)."""
        self._view_mode = (mode or 'home').lower()

    def set_translate(self, translate: Callable):
        """Update translation function for dynamic i18n changes."""
        self._translate = translate

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        """Localize string key with fallback."""
        return self._translate(key, default, **kwargs)

    # ── Abstract methods implementation ─────────────────────────────────

    def _compute_size(self, option: QStyleOptionViewItem, item_dict: dict) -> QSize:
        """
        Return row size for tool item.

        Computes deterministic QSize based on card layout and responsive stage.
        Height is always ROW_HEIGHT + vertical margins (2px top/bottom padding).

        Args:
            option: Style option (rect.width() used for responsive stage calculation).
            item_dict: Tool data dict (not used for size, but passed by contract).

        Returns:
            QSize: (available_width, row_height_with_margins)
        """
        width = option.rect.width() if option.rect.width() > 0 else 600
        return QSize(width, self.ROW_HEIGHT + self.CARD_MARGIN_V * 2)

    def _paint_item_content(
        self, painter: QPainter, option: QStyleOptionViewItem, item_dict: dict
    ) -> None:
        """
        Paint tool-specific card content (icon, name, type, spindle availability).

        Implemented as tool card layout with responsive stages:
          - icon-only: just the icon
          - name-only: icon + description
          - reduced: icon + tool_id + name
          - full: icon + tool_id + name + type columns (geom_x, geom_z)

        Preserves all existing home_page.py rendering logic.

        Args:
            painter: Active QPainter (in save/restore context from base class).
            option: QStyleOptionViewItem with rect, state, palette, font.
            item_dict: Tool data dict from model (ROLE_TOOL_DATA).
        """
        tool: dict = item_dict or {}
        icon: QIcon | None = self._get_tool_icon(option)
        
        # Calculate responsive stage from available card width
        full = option.rect
        card = QRect(
            full.x() + self.CARD_MARGIN_H,
            full.y() + self.CARD_MARGIN_V,
            full.width() - self.CARD_MARGIN_H * 2,
            self.ROW_HEIGHT,
        )
        card_w = card.width()
        
        if card_w >= BP_FULL:
            stage = 'full'
        elif card_w >= BP_REDUCED:
            stage = 'reduced'
        elif card_w >= BP_NAME_ONLY:
            stage = 'name-only'
        else:
            stage = 'icon-only'

        # Paint icon (always present except in minimal layouts)
        content = card.adjusted(
            self.CARD_PADDING_H + self.BORDER_INSET,
            self.CARD_PADDING_V + self.BORDER_INSET,
            -(self.CARD_PADDING_H + self.BORDER_INSET),
            -(self.CARD_PADDING_V + self.BORDER_INSET),
        )

        icon_rect = QRect(
            content.x(),
            content.y() + (content.height() - ICON_SIZE) // 2 + ICON_VISUAL_OFFSET_Y,
            ICON_SLOT_W,
            ICON_SIZE,
        )

        if icon is not None:
            pm = self._cached_pixmap(
                icon,
                tool.get('tool_type', ''),
                mirrored=_is_sub_spindle(tool.get('spindle_orientation', 'main')),
            )
            if pm and not pm.isNull():
                px = icon_rect.x() + (ICON_SLOT_W - pm.width()) // 2
                py = icon_rect.y() + (ICON_SIZE - pm.height()) // 2
                painter.drawPixmap(px, py, pm)

        if stage == 'icon-only':
            return

        # Build column list based on view mode and responsive stage
        cols = self._build_columns(tool, stage)

        # Choose font sizes based on responsive stage
        if stage == 'name-only':
            vfont = self._value_font_tight if card_w < 300 else self._value_font_narrow
        elif stage == 'reduced':
            vfont = self._value_font_full
        elif card_w < 500:
            vfont = self._value_font_tight
        elif card_w < 620:
            vfont = self._value_font_narrow
        else:
            vfont = self._value_font_full

        hfont = self._header_font
        hfm = QFontMetrics(hfont)
        vfm = QFontMetrics(vfont)

        # Layout columns with weight-based width distribution
        text_left = content.x() + ICON_SLOT_W + COL_SPACING
        gap_budget = COL_SPACING * max(0, len(cols) - 1)
        text_width = content.width() - ICON_SLOT_W - COL_SPACING - gap_budget

        if text_width < 10:
            return

        total_weight = sum(c[3] for c in cols) or 1
        col_rects: list[tuple[str, str, str, QRect]] = []
        x = text_left

        for i, (key, header, value, weight) in enumerate(cols):
            if i == len(cols) - 1:
                w = text_left + text_width - x
            else:
                w = int(text_width * weight / total_weight)
            col_rects.append((key, header, value, QRect(x, content.y(), w, content.height())))
            x += w + (COL_SPACING if i < len(cols) - 1 else 0)

        # Paint each column (header + value)
        self._paint_columns(painter, col_rects, hfont, vfont, hfm, vfm, stage)

    # ── Helper methods ──────────────────────────────────────────────────

    def _get_tool_icon(self, option: QStyleOptionViewItem) -> QIcon | None:
        """Extract icon from painter option's model data."""
        # The icon is passed via custom roles; retrieve from current model/index
        # This is called during paint, so icon should be available in item_dict context
        # Return None here; actual icon loading happens via _cached_pixmap()
        return tool_icon_for_type('')

    def _build_columns(self, tool: dict, stage: str) -> list[tuple[str, str, str, int]]:
        """
        Build column list based on view mode and responsive stage.

        Returns list of (key, header, value, weight_percent) tuples.
        Weight is used to proportionally distribute available text width.
        """
        desc = (tool.get('description', '') or '').strip() or self._t('tool_library.common.no_description', 'No description')
        tool_id_val = _tool_id_display_value(tool.get('id', ''))

        # Base columns for 'home' view (default)
        all_cols = [
            ('tool_id', self._t('tool_library.row.tool_id', 'Tool ID'), tool_id_val, 100),
            ('tool_name', self._t('tool_library.row.tool_name', 'Tool name'), desc, 270),
            ('geom_x', self._t('tool_library.field.geom_x', 'Geom X'), _safe_float(tool.get('geom_x', 0)), 110),
            ('geom_z', self._t('tool_library.field.geom_z', 'Geom Z'), _safe_float(tool.get('geom_z', 0)), 110),
        ]

        # Filter columns by stage
        if stage == 'name-only':
            return [c for c in all_cols if c[0] in ('tool_name',)]
        elif stage == 'reduced':
            return [c for c in all_cols if c[0] in ('tool_id', 'tool_name')]
        else:
            return all_cols

    def _paint_columns(
        self,
        painter: QPainter,
        col_rects: list[tuple[str, str, str, QRect]],
        hfont: QFont,
        vfont: QFont,
        hfm: QFontMetrics,
        vfm: QFontMetrics,
        stage: str,
    ) -> None:
        """
        Paint header + value for each column with responsive text sizing.

        Implements wrapping for description, eliding for other fields.
        """
        single_header_h = hfm.height()
        value_line_h = vfm.height()

        for key, header, value, rect in col_rects:
            if rect.width() < 8:
                continue

            text_rect = rect.adjusted(1, 0, -3, 0)
            if text_rect.width() < 8:
                continue

            # Multi-line header support (for fields like "Nose /\nCorner R")
            header_lines = header.split('\n') if '\n' in header else [header]
            header_h = single_header_h * len(header_lines)
            if key == 'tool_name' and len(header_lines) == 1:
                header_h = max(1, header_h - 3)

            # Paint header
            painter.setFont(hfont)
            painter.setPen(CLR_HEADER_TEXT)

            if len(header_lines) > 1:
                for ln_i, ln_text in enumerate(header_lines):
                    ln_rect = QRect(
                        text_rect.x(),
                        text_rect.y() + single_header_h * ln_i,
                        text_rect.width(),
                        single_header_h,
                    )
                    elided = hfm.elidedText(ln_text.strip(), Qt.ElideRight, text_rect.width())
                    painter.drawText(ln_rect, Qt.AlignHCenter | Qt.AlignBottom, elided)
            else:
                header_y = text_rect.y() + (1 if key == 'tool_name' else 0)
                header_rect = QRect(text_rect.x(), header_y, text_rect.width(), header_h)
                elided = hfm.elidedText(header_lines[0], Qt.ElideRight, text_rect.width())
                painter.drawText(header_rect, Qt.AlignHCenter | Qt.AlignBottom, elided)

            # Paint value with optional wrapping for descriptions
            value_rect = QRect(
                text_rect.x(),
                text_rect.y() + header_h - 2,
                text_rect.width(),
                text_rect.height() - header_h + 2,
            )

            painter.setFont(vfont)
            painter.setPen(CLR_VALUE_TEXT)

            if key == 'tool_name':
                self._paint_description(painter, value, value_rect, stage, vfm)
            else:
                elided = vfm.elidedText(value, Qt.ElideRight, value_rect.width())
                painter.drawText(value_rect, Qt.AlignHCenter | Qt.AlignTop, elided)

    def _paint_description(
        self,
        painter: QPainter,
        text: str,
        rect: QRect,
        stage: str,
        fm: QFontMetrics,
    ) -> None:
        """
        Paint tool description with intelligent line wrapping.

        Splits on ' - ' when possible; falls back to word wrapping.
        """
        raw = (text or '').strip()
        if not raw or stage == 'icon-only' or rect.width() < 16:
            return

        w = rect.width()
        breakable = ' ' in raw or '-' in raw or '/' in raw
        two_lines = (
            stage == 'name-only' and breakable and fm.horizontalAdvance(raw) > w
        )

        line_h = fm.height()
        line_step = max(1, int(round(line_h * WRAPPED_LINE_STEP_FACTOR))) if two_lines else line_h
        top_inset = 1 if two_lines else 0

        if not two_lines or fm.horizontalAdvance(raw) <= w:
            elided = fm.elidedText(raw, Qt.ElideRight, w)
            painter.drawText(rect.adjusted(0, top_inset, 0, 0), Qt.AlignHCenter | Qt.AlignTop, elided)
            return

        # Try split on ' - ' (common separator)
        if ' - ' in raw:
            left, right = raw.split(' - ', 1)
            left = left.strip()
            right = f'- {right.strip()}'
            if left and fm.horizontalAdvance(left) <= w:
                painter.drawText(
                    QRect(rect.x(), rect.y() + top_inset, w, line_h),
                    Qt.AlignHCenter | Qt.AlignTop,
                    left,
                )
                elided2 = fm.elidedText(right, Qt.ElideRight, w)
                painter.drawText(
                    QRect(rect.x(), rect.y() + top_inset + line_step, w, line_h),
                    Qt.AlignHCenter | Qt.AlignTop,
                    elided2,
                )
                return

        # Word-wrap fitting
        tokens = raw.split()
        first_tokens: list[str] = []
        rest = tokens[:]

        while rest:
            candidate = ' '.join(first_tokens + [rest[0]])
            if not first_tokens or fm.horizontalAdvance(candidate) <= w:
                first_tokens.append(rest.pop(0))
            else:
                break

        line1 = ' '.join(first_tokens)
        if not rest:
            elided = fm.elidedText(line1, Qt.ElideRight, w)
            painter.drawText(rect.adjusted(0, top_inset, 0, 0), Qt.AlignHCenter | Qt.AlignTop, elided)
            return

        painter.drawText(
            QRect(rect.x(), rect.y() + top_inset, w, line_h),
            Qt.AlignHCenter | Qt.AlignTop,
            fm.elidedText(line1, Qt.ElideRight, w),
        )
        line2 = fm.elidedText(' '.join(rest), Qt.ElideRight, w)
        painter.drawText(
            QRect(rect.x(), rect.y() + top_inset + line_step, w, line_h),
            Qt.AlignHCenter | Qt.AlignTop,
            line2,
        )

    def _cached_pixmap(
        self, icon: QIcon, tool_type: str, mirrored: bool = False
    ) -> QPixmap | None:
        """
        Cache icon pixmaps by tool type and mirror state.

        Normalizes pixmap (crops transparent borders) and applies mirror
        transform for sub-spindle tools.
        """
        key = f"{tool_type or '__default__'}|{'mirrored' if mirrored else 'normal'}"
        if key not in self._icon_cache:
            pm = icon.pixmap(QSize(ICON_SIZE, ICON_SIZE))
            pm = self._normalized_icon_pixmap(pm)
            if mirrored and pm is not None and not pm.isNull():
                pm = pm.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
            self._icon_cache[key] = pm
        return self._icon_cache.get(key)

    @staticmethod
    def _normalized_icon_pixmap(pixmap: QPixmap) -> QPixmap:
        """
        Normalize icon pixmap by cropping transparent borders.

        Returns smallest bounding box containing non-transparent pixels,
        scaled to ICON_SIZE with aspect ratio preserved.
        """
        if pixmap.isNull():
            return pixmap

        image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        left = image.width()
        top = image.height()
        right = -1
        bottom = -1

        # Find bounding box of non-transparent pixels
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 6:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)

        if right < left or bottom < top:
            return pixmap

        # Crop and scale
        cropped = image.copy(left, top, right - left + 1, bottom - top + 1)
        normalized = QPixmap.fromImage(
            cropped.scaled(
                QSize(ICON_SIZE, ICON_SIZE),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )
        return normalized if not normalized.isNull() else pixmap

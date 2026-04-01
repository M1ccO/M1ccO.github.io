"""
Custom QStyledItemDelegate for painting jaw catalog rows.

Mirrors the tool catalog delegate architecture:
- no embedded row widgets
- deterministic painting with QPainter
- responsive column visibility by available width
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from config import TOOL_ICONS_DIR

ROLE_JAW_ID = Qt.UserRole
ROLE_JAW_DATA = Qt.UserRole + 1
ROLE_JAW_ICON = Qt.UserRole + 2

ROW_HEIGHT = 74
ICON_SIZE = 40
ICON_SLOT_W = 40
CARD_RADIUS = 8
CARD_MARGIN_H = 6
CARD_MARGIN_V = 2
CARD_PADDING_H = 10
CARD_PADDING_V = 1
COL_SPACING = 10
HEADER_VALUE_GAP = 0
BORDER_INSET = 3
WRAPPED_LINE_STEP_FACTOR = 0.82

BP_FULL = 620
BP_REDUCED = 390
BP_NAME_ONLY = 180

CLR_CARD_BG = QColor("#ffffff")
CLR_CARD_HOVER = QColor("#f7fbff")
CLR_CARD_BORDER = QColor("#3e4a56")
CLR_CARD_SELECTED_BORDER = QColor("#42a5f5")
CLR_HEADER_TEXT = QColor("#2b3136")
CLR_VALUE_TEXT = QColor("#171a1d")
_ICON_OBJECT_CACHE: dict[str, QIcon] = {}


def _header_font() -> QFont:
    font = QFont()
    font.setPointSizeF(9.0)
    font.setWeight(QFont.DemiBold)
    return font


def _value_font(pt: float) -> QFont:
    font = QFont()
    font.setPointSizeF(pt)
    font.setWeight(QFont.DemiBold)
    return font


def _normalized(value: str) -> str:
    return (value or "").strip().lower()


def _is_sub_spindle(spindle_side: str) -> bool:
    normalized = _normalized(spindle_side)
    return ("sub" in normalized) or ("vasta" in normalized) or ("ala" in normalized)


def _jaw_icon_filename(jaw_type: str) -> str:
    _ = jaw_type
    # Keep one stable base icon for jaw rows; sub spindle rows mirror it.
    return "hard_jaw.png"


def jaw_icon_for_row(jaw: dict) -> QIcon:
    filename = _jaw_icon_filename(jaw.get("jaw_type", ""))
    path = TOOL_ICONS_DIR / filename
    if not path.exists():
        fallback = TOOL_ICONS_DIR / "jaw_icon.png"
        path = fallback if fallback.exists() else path
    if not path.exists():
        return QIcon()
    cache_key = str(path).lower()
    cached = _ICON_OBJECT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    icon = QIcon(str(path))
    _ICON_OBJECT_CACHE[cache_key] = icon
    return icon


def _clean_icon_image(path: Path, target_size: QSize | None = None, threshold: int = 232) -> QImage:
    image = QImage(str(path))
    if image.isNull():
        return image
    image = image.convertToFormat(QImage.Format_ARGB32)
    if target_size is not None and not target_size.isEmpty():
        image = image.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    for y in range(image.height()):
        for x in range(image.width()):
            color = QColor(image.pixel(x, y))
            # Remove near-white matte backgrounds while keeping icon details.
            hsv = color.toHsv()
            near_white_rgb = color.red() >= threshold and color.green() >= threshold and color.blue() >= threshold
            near_white_hsv = hsv.value() >= 232 and hsv.saturation() <= 26
            if color.alpha() > 0 and (near_white_rgb or near_white_hsv):
                color.setAlpha(0)
                image.setPixelColor(x, y, color)
    return image


class JawCatalogDelegate(QStyledItemDelegate):
    """Paint each jaw row as a rounded card with responsive text columns."""

    def __init__(self, parent=None, translate: Callable | None = None):
        super().__init__(parent)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._header_font = _header_font()
        self._value_font_full = _value_font(13.4)
        self._value_font_narrow = _value_font(12.4)
        self._value_font_tight = _value_font(11.4)
        self._value_font_tiny = _value_font(10.4)
        self._icon_cache: dict[tuple[str, str], QPixmap] = {}

    def set_translate(self, translate: Callable):
        self._translate = translate

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _description_line_count(self, metrics: QFontMetrics, text: str, width: int, stage: str) -> int:
        raw = (text or "").strip()
        if not raw or stage == "icon-only" or width < 16:
            return 1
        breakable = " " in raw or "-" in raw or "/" in raw
        if stage == "name-only" and breakable:
            return 2
        if metrics.horizontalAdvance(raw) <= width:
            return 1
        if not breakable:
            return 1
        return 2

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        width = option.rect.width() if option.rect.width() > 0 else 600
        return QSize(width, ROW_HEIGHT + CARD_MARGIN_V * 2)

    def _columns(self, jaw: dict) -> list[tuple[str, str, str, int]]:
        dash = "-"
        jaw_type = self._t(
            f"jaw_library.jaw_type.{(jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
            jaw.get("jaw_type", ""),
        )
        return [
            ("jaw_id", self._t("jaw_library.row.jaw_id", "Jaw ID"), jaw.get("jaw_id", "") or dash, 180),
            ("jaw_type", self._t("jaw_library.row.jaw_type", "Jaw type"), jaw_type or dash, 210),
            (
                "diameter",
                self._t("jaw_library.row.clamping_diameter_multiline", "Clamping\ndiameter"),
                jaw.get("clamping_diameter_text", "") or dash,
                190,
            ),
            (
                "length",
                self._t("jaw_library.row.clamping_length_multiline", "Clamping\nlength"),
                jaw.get("clamping_length", "") or dash,
                180,
            ),
        ]

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        jaw: dict = index.data(ROLE_JAW_DATA) or {}
        icon: QIcon | None = index.data(ROLE_JAW_ICON)
        jaw_type = jaw.get("jaw_type", "")
        spindle_side = jaw.get("spindle_side", "")

        full = option.rect
        card = QRect(
            full.x() + CARD_MARGIN_H,
            full.y() + CARD_MARGIN_V,
            full.width() - CARD_MARGIN_H * 2,
            ROW_HEIGHT,
        )
        card_width = card.width()

        if card_width >= BP_FULL:
            stage = "full"
        elif card_width >= BP_REDUCED:
            stage = "reduced"
        elif card_width >= BP_NAME_ONLY:
            stage = "name-only"
        else:
            stage = "icon-only"

        hovered = bool(option.state & QStyle.State_MouseOver)
        selected = bool(option.state & QStyle.State_Selected)

        bg = CLR_CARD_HOVER if hovered and not selected else CLR_CARD_BG
        border_color = CLR_CARD_SELECTED_BORDER if selected else CLR_CARD_BORDER
        border_width = 3 if selected else 1

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(bg)
        painter.drawRoundedRect(card, CARD_RADIUS, CARD_RADIUS)

        content = card.adjusted(
            CARD_PADDING_H + BORDER_INSET,
            CARD_PADDING_V + BORDER_INSET,
            -(CARD_PADDING_H + BORDER_INSET),
            -(CARD_PADDING_V + BORDER_INSET),
        )

        icon_rect = QRect(content.x(), content.y() + (content.height() - ICON_SIZE) // 2, ICON_SLOT_W, ICON_SIZE)
        if icon is not None:
            pixmap = self._cached_pixmap(icon, jaw_type, spindle_side)
            if pixmap and not pixmap.isNull():
                px = icon_rect.x() + (ICON_SLOT_W - pixmap.width()) // 2
                py = icon_rect.y() + (ICON_SIZE - pixmap.height()) // 2
                painter.drawPixmap(px, py, pixmap)

        if stage == "icon-only":
            painter.restore()
            return

        all_cols = self._columns(jaw)
        if stage == "name-only":
            cols = [c for c in all_cols if c[0] == "jaw_id"]
        elif stage == "reduced":
            cols = [c for c in all_cols if c[0] in ("jaw_id", "jaw_type")]
        else:
            cols = all_cols

        if stage == "name-only":
            if card_width < 300:
                value_font = self._value_font_tight
            else:
                value_font = self._value_font_narrow
        elif stage == "reduced":
            value_font = self._value_font_full
        elif card_width < 500:
            value_font = self._value_font_tight
        elif card_width < 620:
            value_font = self._value_font_narrow
        else:
            value_font = self._value_font_full

        header_font = self._header_font
        header_metrics = QFontMetrics(header_font)
        value_metrics = QFontMetrics(value_font)

        text_left = content.x() + ICON_SLOT_W + COL_SPACING
        gap_budget = COL_SPACING * max(0, len(cols) - 1)
        text_width = content.width() - ICON_SLOT_W - COL_SPACING - gap_budget
        if text_width < 10:
            painter.restore()
            return

        total_weight = sum(col[3] for col in cols) or 1
        col_rects: list[tuple[str, str, str, QRect]] = []
        x = text_left
        for idx, (key, header, value, weight) in enumerate(cols):
            if idx == len(cols) - 1:
                width = text_left + text_width - x
            else:
                width = int(text_width * weight / total_weight)
            col_rects.append((key, header, str(value), QRect(x, content.y(), width, content.height())))
            x += width + (COL_SPACING if idx < len(cols) - 1 else 0)

        single_header_h = header_metrics.height()
        value_line_h = value_metrics.height()

        for key, header, value, rect in col_rects:
            if rect.width() < 8:
                continue
            text_rect = rect.adjusted(1, 0, -3, 0)
            if text_rect.width() < 8:
                continue

            header_lines = header.split("\n") if "\n" in header else [header]
            header_h = single_header_h * len(header_lines)
            line_count = (
                self._description_line_count(value_metrics, value, text_rect.width(), stage)
                if key == "jaw_type" else 1
            )
            wrapped = line_count == 2 and key == "jaw_type"
            header_value_gap = -2 if key in ("diameter", "length") else (-2 if wrapped else 0)
            effective_value_h = int(round(value_line_h * WRAPPED_LINE_STEP_FACTOR)) if wrapped else value_line_h
            value_h = value_line_h + effective_value_h if wrapped else value_line_h * line_count
            block_h = header_h + header_value_gap + value_h
            vertical_bias = 3 if wrapped else (2 if key in ("diameter", "length") else (1 if len(header_lines) > 1 else 0))
            y_offset = max(0, (text_rect.height() - block_h) // 2 - vertical_bias)

            painter.setFont(header_font)
            painter.setPen(CLR_HEADER_TEXT)
            if len(header_lines) > 1:
                for line_index, line_text in enumerate(header_lines):
                    line_rect = QRect(text_rect.x(), text_rect.y() + y_offset + single_header_h * line_index, text_rect.width(), single_header_h)
                    elided_line = header_metrics.elidedText(line_text.strip(), Qt.ElideRight, text_rect.width())
                    painter.drawText(line_rect, Qt.AlignHCenter | Qt.AlignBottom, elided_line)
            else:
                header_rect = QRect(text_rect.x(), text_rect.y() + y_offset, text_rect.width(), header_h)
                elided_header = header_metrics.elidedText(header_lines[0], Qt.ElideRight, text_rect.width())
                painter.drawText(header_rect, Qt.AlignHCenter | Qt.AlignBottom, elided_header)

            value_rect = QRect(
                text_rect.x(),
                text_rect.y() + y_offset + header_h + header_value_gap,
                text_rect.width(),
                text_rect.height() - y_offset - header_h - header_value_gap,
            )
            painter.setFont(value_font)
            painter.setPen(CLR_VALUE_TEXT)

            if key == "jaw_type":
                self._paint_description(painter, value, value_rect, stage)
            else:
                elided = value_metrics.elidedText(value, Qt.ElideRight, value_rect.width())
                painter.drawText(value_rect, Qt.AlignHCenter | Qt.AlignTop, elided)

        painter.restore()

    def _paint_description(self, painter: QPainter, text: str, rect: QRect, stage: str):
        metrics = QFontMetrics(painter.font())
        raw = (text or "").strip()
        if not raw:
            return
        width = rect.width()
        two_lines = self._description_line_count(metrics, raw, width, stage) == 2
        line_h = metrics.height()
        line_step = max(1, int(round(line_h * WRAPPED_LINE_STEP_FACTOR))) if two_lines else line_h

        if not two_lines or metrics.horizontalAdvance(raw) <= width:
            elided = metrics.elidedText(raw, Qt.ElideRight, width)
            painter.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, elided)
            return

        tokens = raw.split()
        first_tokens: list[str] = []
        rest = tokens[:]
        while rest:
            candidate = " ".join(first_tokens + [rest[0]])
            if not first_tokens or metrics.horizontalAdvance(candidate) <= width:
                first_tokens.append(rest.pop(0))
            else:
                break

        line1 = " ".join(first_tokens)
        if not rest:
            painter.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, metrics.elidedText(line1, Qt.ElideRight, width))
            return

        painter.drawText(
            QRect(rect.x(), rect.y(), width, line_h),
            Qt.AlignHCenter | Qt.AlignTop,
            metrics.elidedText(line1, Qt.ElideRight, width),
        )
        line2 = metrics.elidedText(" ".join(rest), Qt.ElideRight, width)
        painter.drawText(QRect(rect.x(), rect.y() + line_step, width, line_h), Qt.AlignHCenter | Qt.AlignTop, line2)

    def _cached_pixmap(self, icon: QIcon, jaw_type: str, spindle_side: str) -> QPixmap | None:
        file_name = _jaw_icon_filename(jaw_type)
        key = (file_name, "sub" if _is_sub_spindle(spindle_side) else "main")
        if key not in self._icon_cache:
            path = TOOL_ICONS_DIR / file_name
            if not path.exists():
                fallback = TOOL_ICONS_DIR / "jaw_icon.png"
                path = fallback if fallback.exists() else path

            pixmap = QPixmap()
            if path.exists():
                img = _clean_icon_image(path, QSize(ICON_SIZE, ICON_SIZE))
                if not img.isNull() and key[1] == "sub":
                    img = img.mirrored(True, False)
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img)

            if pixmap.isNull():
                pixmap = icon.pixmap(QSize(ICON_SIZE, ICON_SIZE))
                if not pixmap.isNull() and key[1] == "sub":
                    pixmap = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
            self._icon_cache[key] = pixmap
        return self._icon_cache.get(key)

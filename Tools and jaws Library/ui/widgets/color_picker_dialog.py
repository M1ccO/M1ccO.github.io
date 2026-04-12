from __future__ import annotations

import json
from typing import Callable

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QIntValidator, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import SETTINGS_PATH, TOOL_ICONS_DIR
from shared.ui.helpers.common_widgets import add_shadow
from shared.ui.helpers.editor_helpers import setup_editor_dialog


def _noop_translate(_key: str, default: str | None = None, **_kwargs) -> str:
    return default or ""


class _ColorSwatchButton(QPushButton):
    clickedColor = Signal(str)

    def __init__(self, color_hex: str = "", parent=None):
        super().__init__(parent)
        self._color_hex = ""
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("colorPickerSwatch", True)
        self.setMinimumSize(20, 20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.clicked.connect(self._emit_color)
        self.set_color(color_hex)

    def color_hex(self) -> str:
        return self._color_hex

    def set_color(self, color_hex: str):
        normalized = QColor(color_hex).name() if color_hex and QColor(color_hex).isValid() else ""
        self._color_hex = normalized
        self.setToolTip(normalized or "")
        self.update()

    def set_selected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        self.update()

    def _emit_color(self):
        if self._color_hex:
            self.clickedColor.emit(self._color_hex)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        if self._color_hex:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self._color_hex))
            painter.drawRect(rect)
        else:
            painter.setPen(QPen(QColor("#c9d3dc"), 1))
            painter.setBrush(QColor("#f7fafc"))
            painter.drawRect(rect)

        if self._selected:
            sel_pen = QPen(QColor("#ffffff"), 2)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
            sel_pen2 = QPen(QColor("#22303c"), 1)
            painter.setPen(sel_pen2)
            painter.drawRect(rect.adjusted(2, 2, -2, -2))


class _HueSlider(QWidget):
    hueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0
        self.setMinimumSize(28, 150)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)

    def hue(self) -> int:
        return self._hue

    def set_hue(self, hue: int):
        hue = max(0, min(359, int(hue)))
        if self._hue == hue:
            return
        self._hue = hue
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._set_from_pos(event.position().toPoint())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._set_from_pos(event.position().toPoint())

    def _set_from_pos(self, pos: QPoint):
        margin = 8
        usable = max(1, self.height() - margin * 2)
        y = max(margin, min(self.height() - margin, pos.y()))
        ratio = 1.0 - ((y - margin) / usable)
        hue = int(round(ratio * 359)) % 360
        if hue != self._hue:
            self._hue = hue
            self.hueChanged.emit(hue)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        frame_rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor("#c8d4e0"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(frame_rect, 6, 6)

        gradient_rect = frame_rect.adjusted(6, 6, -6, -6)
        gradient = QLinearGradient(gradient_rect.topLeft(), gradient_rect.bottomLeft())
        for stop, hue in ((0.0, 359), (0.17, 300), (0.33, 240), (0.5, 180), (0.67, 120), (0.83, 60), (1.0, 0)):
            gradient.setColorAt(stop, QColor.fromHsv(hue, 255, 255))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(gradient_rect, 4, 4)

        marker_y = gradient_rect.top() + int((1.0 - (self._hue / 359.0)) * gradient_rect.height())
        marker_y = max(gradient_rect.top() + 2, min(gradient_rect.bottom() - 2, marker_y))
        marker_rect = QRect(gradient_rect.left() - 2, marker_y - 3, gradient_rect.width() + 4, 6)
        painter.setPen(QPen(QColor("#22303c"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(marker_rect, 3, 3)


class _SaturationValuePicker(QWidget):
    colorChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0
        self._sat = 255
        self._val = 255
        self._cache = QPixmap()
        self.setMinimumSize(150, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)

    def set_hue(self, hue: int):
        hue = max(0, min(359, int(hue)))
        if self._hue == hue:
            return
        self._hue = hue
        self._cache = QPixmap()
        self.update()

    def set_sv(self, saturation: int, value: int):
        saturation = max(0, min(255, int(saturation)))
        value = max(0, min(255, int(value)))
        if self._sat == saturation and self._val == value:
            return
        self._sat = saturation
        self._val = value
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cache = QPixmap()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._set_from_pos(event.position().toPoint())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._set_from_pos(event.position().toPoint())

    def _set_from_pos(self, pos: QPoint):
        inner = self._inner_rect()
        x = max(inner.left(), min(inner.right(), pos.x()))
        y = max(inner.top(), min(inner.bottom(), pos.y()))
        sat = int(round(((x - inner.left()) / max(1, inner.width())) * 255))
        val = int(round((1.0 - ((y - inner.top()) / max(1, inner.height()))) * 255))
        if sat != self._sat or val != self._val:
            self._sat = sat
            self._val = val
            self.colorChanged.emit(sat, val)
            self.update()

    def _inner_rect(self) -> QRect:
        return self.rect().adjusted(8, 8, -8, -8)

    def _build_cache(self) -> QPixmap:
        inner = self._inner_rect()
        image = QImage(inner.size(), QImage.Format_RGB32)
        for y in range(inner.height()):
            value = int(round((1.0 - (y / max(1, inner.height() - 1))) * 255))
            for x in range(inner.width()):
                sat = int(round((x / max(1, inner.width() - 1)) * 255))
                image.setPixelColor(x, y, QColor.fromHsv(self._hue, sat, value))
        return QPixmap.fromImage(image)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        frame_rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor("#c8d4e0"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(frame_rect, 6, 6)

        inner = self._inner_rect()
        if self._cache.isNull() or self._cache.size() != inner.size():
            self._cache = self._build_cache()
        painter.drawPixmap(inner.topLeft(), self._cache)

        cross_x = inner.left() + int((self._sat / 255.0) * inner.width())
        cross_y = inner.top() + int((1.0 - (self._val / 255.0)) * inner.height())
        cross_x = max(inner.left(), min(inner.right(), cross_x))
        cross_y = max(inner.top(), min(inner.bottom(), cross_y))

        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(QPoint(cross_x, cross_y), 7, 7)
        painter.setPen(QPen(QColor("#22303c"), 1))
        painter.drawEllipse(QPoint(cross_x, cross_y), 7, 7)


class _HandleCursorSlider(QSlider):
    """Slider that switches cursor only when hovering the handle."""

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self._groove_height = 6
        self._handle_diameter = 18
        self._active_color = QColor("#2fa1ee")
        self._inactive_color = QColor("#d9eefb")
        self._border_color = QColor("#ffffff")
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    def set_slider_metrics(self, groove_height: int, handle_diameter: int):
        self._groove_height = max(2, int(groove_height))
        self._handle_diameter = max(self._groove_height + 2, int(handle_diameter))
        self.update()

    def handle_rect(self) -> QRect:
        if self.orientation() != Qt.Horizontal:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            return self.style().subControlRect(
                QStyle.CC_Slider,
                option,
                QStyle.SC_SliderHandle,
                self,
            )

        handle_radius = self._handle_diameter / 2.0
        left = handle_radius
        right = max(left, self.width() - handle_radius)
        span = max(1.0, right - left)
        ratio = 0.0
        if self.maximum() > self.minimum():
            ratio = (self.sliderPosition() - self.minimum()) / (self.maximum() - self.minimum())
        center_x = left + (ratio * span)
        center_y = self.rect().center().y()
        return QRect(
            int(round(center_x - handle_radius)),
            int(round(center_y - handle_radius)),
            self._handle_diameter,
            self._handle_diameter,
        )

    def _update_handle_cursor(self, pos):
        handle_rect = self.handle_rect()
        self.setCursor(Qt.PointingHandCursor if handle_rect.contains(pos) else Qt.ArrowCursor)

    def paintEvent(self, event):
        if self.orientation() != Qt.Horizontal:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track_margin = self._handle_diameter // 2
        track_rect = QRect(
            track_margin,
            (self.height() - self._groove_height) // 2,
            max(1, self.width() - (track_margin * 2)),
            self._groove_height,
        )
        handle_rect = self.handle_rect()
        progress_rect = QRect(track_rect)
        progress_rect.setWidth(max(0, handle_rect.center().x() - track_rect.left()))

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._inactive_color)
        painter.drawRoundedRect(track_rect, self._groove_height / 2.0, self._groove_height / 2.0)

        if progress_rect.width() > 0:
            painter.setBrush(self._active_color)
            painter.drawRoundedRect(progress_rect, self._groove_height / 2.0, self._groove_height / 2.0)

        painter.setPen(QPen(self._border_color, 2))
        painter.setBrush(self._active_color)
        painter.drawEllipse(handle_rect)

    def mouseMoveEvent(self, event):
        self._update_handle_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self._update_handle_cursor(event.position().toPoint())
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)


class ColorPickerDialog(QDialog):
    _custom_colors = ["" for _ in range(13)]
    _custom_insert_index = 0
    _custom_colors_loaded = False
    _custom_add_icon = QIcon(str(TOOL_ICONS_DIR / "Plus_icon.svg"))
    _custom_delete_icon = QIcon(str(TOOL_ICONS_DIR / "delete.svg"))

    def __init__(
        self,
        initial_color: str = "#9ea7b3",
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
        self._updating_fields = False
        type(self)._load_custom_colors_from_settings()
        self._selected_color = QColor(initial_color if QColor(initial_color).isValid() else "#9ea7b3")
        self._selected_basic_index = -1
        self._selected_custom_index = -1

        self.setWindowTitle(self._t("tool_editor.dialog.select_part_color", "Select part color"))
        self.resize(400, 500)
        self.setMinimumSize(360, 450)
        setup_editor_dialog(self)
        self.setProperty("colorPickerDialog", True)
        self._build_ui()
        self._apply_color(self._selected_color, preserve_custom=False)

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _dp(self, px: int) -> int:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return max(1, int(px))
        factor = screen.logicalDotsPerInch() / 96.0
        return max(1, int(round(px * factor)))

    def selected_color(self) -> QColor:
        return QColor(self._selected_color)

    @classmethod
    def get_color(
        cls,
        initial_color: str = "#9ea7b3",
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ) -> QColor | None:
        dialog = cls(initial_color=initial_color, parent=parent, translate=translate)
        if dialog.exec():
            return dialog.selected_color()
        return None

    @classmethod
    def _load_custom_colors_from_settings(cls):
        if cls._custom_colors_loaded:
            return

        cls._custom_colors_loaded = True
        try:
            if SETTINGS_PATH.exists():
                payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            else:
                payload = {}
        except Exception:
            payload = {}

        raw_colors = payload.get("color_picker_custom_colors")
        if isinstance(raw_colors, list):
            normalized = []
            for value in raw_colors[: len(cls._custom_colors)]:
                if isinstance(value, str) and QColor(value).isValid():
                    normalized.append(QColor(value).name())
                else:
                    normalized.append("")
            while len(normalized) < len(cls._custom_colors):
                normalized.append("")
            cls._custom_colors = normalized

        try:
            insert_index = int(payload.get("color_picker_custom_insert_index", cls._custom_insert_index))
        except Exception:
            insert_index = 0
        cls._custom_insert_index = insert_index % len(cls._custom_colors)

    @classmethod
    def _save_custom_colors_to_settings(cls):
        try:
            if SETTINGS_PATH.exists():
                payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            else:
                payload = {}
        except Exception:
            payload = {}

        payload["color_picker_custom_colors"] = list(cls._custom_colors)
        payload["color_picker_custom_insert_index"] = int(cls._custom_insert_index)

        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            # Persistence is best-effort; picker should still work without disk writes.
            pass

    @staticmethod
    def _build_grid_palette() -> list[str]:
        # 12 hues left-to-right, 9 brightness bands, plus one grayscale row.
        hues = [205, 220, 240, 265, 290, 315, 0, 25, 45, 58, 82, 105]
        saturations = [96, 92, 90, 86, 78, 66, 48, 30, 14]
        values = [36, 48, 60, 72, 84, 92, 96, 98, 100]
        palette: list[str] = []
        # Extra grayscale row from left (white) to right (black).
        for col in range(12):
            val = int(round((1.0 - (col / 11.0)) * 255))
            palette.append(QColor.fromHsv(0, 0, val).name())
        for row in range(9):
            sat = int(round((saturations[row] / 100.0) * 255))
            val = int(round((values[row] / 100.0) * 255))
            for hue in hues:
                palette.append(QColor.fromHsv(hue, sat, val).name())
        return palette

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Mode tabs: Grid | Spectrum | Sliders
        self._mode_tabs = QTabWidget()
        self._mode_tabs.setObjectName("colorPickerModeTabs")
        self._mode_tabs.currentChanged.connect(self._on_mode_tab_changed)
        root.addWidget(self._mode_tabs, 1)

        # Grid tab
        grid_page = QWidget()
        grid_page.setProperty("colorGridPage", True)
        grid_page_layout = QVBoxLayout(grid_page)
        grid_page_layout.setContentsMargins(8, 8, 8, 8)
        grid_page_layout.setSpacing(6)
        self._mode_tabs.addTab(grid_page, self._t("tool_editor.color.tab.grid", "Grid"))

        basic_colors = self._build_grid_palette()
        basic_grid = QGridLayout()
        basic_grid.setHorizontalSpacing(0)
        basic_grid.setVerticalSpacing(0)
        basic_grid.setContentsMargins(2, 2, 2, 2)
        grid_page_layout.addLayout(basic_grid)

        self._basic_swatches: list[_ColorSwatchButton] = []
        for index, color_hex in enumerate(basic_colors):
            swatch = _ColorSwatchButton(color_hex)
            swatch.clickedColor.connect(self._apply_hex_color)
            basic_grid.addWidget(swatch, index // 12, index % 12)
            self._basic_swatches.append(swatch)
        for row in range(10):
            basic_grid.setRowStretch(row, 1)
        for col in range(12):
            basic_grid.setColumnStretch(col, 1)

        # Spectrum tab
        spectrum_page = QWidget()
        spectrum_page.setProperty("colorPickerSurface", True)
        spectrum_layout = QHBoxLayout(spectrum_page)
        spectrum_layout.setContentsMargins(8, 8, 8, 8)
        spectrum_layout.setSpacing(8)
        self._mode_tabs.addTab(spectrum_page, self._t("tool_editor.color.tab.spectrum", "Spectrum"))

        self.sv_picker = _SaturationValuePicker()
        self.sv_picker.colorChanged.connect(self._on_sv_changed)
        spectrum_layout.addWidget(self.sv_picker, 1)

        self.hue_slider = _HueSlider()
        self.hue_slider.hueChanged.connect(self._on_hue_changed)
        spectrum_layout.addWidget(self.hue_slider, 0)

        # Sliders tab (HSV + RGB sliders)
        sliders_page = QWidget()
        sliders_page.setProperty("colorPickerOutlineSurface", True)
        sliders_layout = QVBoxLayout(sliders_page)
        sliders_layout.setContentsMargins(12, 12, 12, 12)
        sliders_layout.setSpacing(10)
        self._mode_tabs.addTab(sliders_page, self._t("tool_editor.color.tab.sliders", "Sliders"))

        hue_row, self.hue_value_slider, self.hue_value_label = self._build_slider_row(
            self._t("tool_editor.color.hue", "Hue"), 0, 359, self._on_hsv_slider_changed
        )
        sat_row, self.sat_value_slider, self.sat_value_label = self._build_slider_row(
            self._t("tool_editor.color.saturation", "Saturation"), 0, 255, self._on_hsv_slider_changed
        )
        val_row, self.val_value_slider, self.val_value_label = self._build_slider_row(
            self._t("tool_editor.color.value", "Val"), 0, 255, self._on_hsv_slider_changed
        )
        red_row, self.red_value_slider, self.red_value_label = self._build_slider_row(
            self._t("tool_editor.color.red", "Red"), 0, 255, self._on_rgb_slider_changed
        )
        green_row, self.green_value_slider, self.green_value_label = self._build_slider_row(
            self._t("tool_editor.color.green", "Green"), 0, 255, self._on_rgb_slider_changed
        )
        blue_row, self.blue_value_slider, self.blue_value_label = self._build_slider_row(
            self._t("tool_editor.color.blue", "Blue"), 0, 255, self._on_rgb_slider_changed
        )

        sliders_layout.addStretch(1)
        sliders_layout.addWidget(hue_row)
        sliders_layout.addStretch(1)
        sliders_layout.addWidget(sat_row)
        sliders_layout.addStretch(1)
        sliders_layout.addWidget(val_row)
        sliders_layout.addStretch(1)
        sliders_layout.addWidget(red_row)
        sliders_layout.addStretch(1)
        sliders_layout.addWidget(green_row)
        sliders_layout.addStretch(1)
        sliders_layout.addWidget(blue_row)
        sliders_layout.addStretch(1)

        # Shared row below the tabs; content depends on the active tab.
        self.grid_saturation_row, self.grid_opacity_slider, self.grid_opacity_label = self._build_slider_row(
            self._t("tool_editor.color.saturation", "Saturation"), 0, 100, self._on_grid_saturation_changed
        )
        root.addWidget(self.grid_saturation_row)

        self.spectrum_html_row = QWidget()
        self.spectrum_html_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.spectrum_html_row.setStyleSheet("background: transparent; border: none;")
        spectrum_html_layout = QHBoxLayout(self.spectrum_html_row)
        spectrum_html_layout.setContentsMargins(0, 0, 0, 0)
        spectrum_html_layout.setSpacing(self._dp(8))
        spectrum_html_label = QLabel("HTML")
        spectrum_html_label.setProperty("detailFieldKey", True)
        spectrum_html_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        spectrum_html_label.setMinimumWidth(self._dp(72))
        spectrum_html_label.setMaximumWidth(self._dp(72))
        spectrum_html_label.setStyleSheet(
            "background: transparent; border: none; font-size: 11pt; font-weight: 600;"
        )
        spectrum_html_layout.addWidget(spectrum_html_label, 0, Qt.AlignVCenter)

        self.html_edit = QLineEdit()
        self.html_edit.setMaxLength(7)
        self.html_edit.setPlaceholderText("#rrggbb")
        self.html_edit.editingFinished.connect(self._apply_html_field)
        self.html_edit.setFixedWidth(self._dp(120))
        self.html_edit.setFixedHeight(max(self._dp(22), self.grid_opacity_slider.sizeHint().height()))
        self.html_edit.setStyleSheet("font-size: 11pt; padding: 4px 8px;")
        spectrum_html_layout.addWidget(self.html_edit, 0, Qt.AlignVCenter)
        spectrum_html_layout.addStretch(1)
        self.spectrum_html_row.setFixedHeight(self.grid_saturation_row.sizeHint().height())
        root.addWidget(self.spectrum_html_row)

        # Common footer
        footer = QFrame()
        footer.setProperty("colorPickerFooter", True)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        footer_layout.setSpacing(8)
        root.addWidget(footer)

        # Left panel: preview swatch + hex label
        preview_panel = QFrame()
        preview_panel.setProperty("colorPickerFieldsPanel", True)
        preview_panel.setMinimumWidth(self._dp(76))
        preview_col = QVBoxLayout(preview_panel)
        preview_col.setContentsMargins(8, 8, 8, 8)
        preview_col.setSpacing(4)
        footer_layout.addWidget(preview_panel)

        self.preview_swatch = QFrame()
        self.preview_swatch.setProperty("colorPreviewSwatch", True)
        self.preview_swatch.setFixedSize(self._dp(56), self._dp(76))
        preview_col.addWidget(self.preview_swatch)
        preview_col.addStretch(1)

        # Apply the same footer presentation across all tabs.
        self._on_mode_tab_changed(self._mode_tabs.currentIndex())

        # Right panel: custom colour circles beside the preview
        custom_panel = QFrame()
        custom_panel.setProperty("colorPickerFieldsPanel", True)
        custom_grid_layout = QGridLayout(custom_panel)
        custom_grid_layout.setContentsMargins(8, 8, 8, 8)
        custom_grid_layout.setHorizontalSpacing(4)
        custom_grid_layout.setVerticalSpacing(4)
        footer_layout.addWidget(custom_panel, 1)

        self._custom_swatches: list[_ColorSwatchButton] = []
        custom_columns = 7
        for index, color_hex in enumerate(type(self)._custom_colors):
            swatch = _ColorSwatchButton(color_hex)
            swatch.clicked.connect(lambda _checked=False, idx=index: self._select_custom_index(idx))
            swatch.clickedColor.connect(self._apply_hex_color)
            custom_grid_layout.addWidget(swatch, index // custom_columns, index % custom_columns)
            self._custom_swatches.append(swatch)
        for column in range(custom_columns):
            custom_grid_layout.setColumnStretch(column, 1)

        self.add_custom_btn = QPushButton("+")
        self.add_custom_btn.setFixedSize(30, 30)
        self.add_custom_btn.setProperty("colorPickerAddBtn", True)
        self.add_custom_btn.setText("")
        self.add_custom_btn.setIconSize(QSize(20, 20))
        self.add_custom_btn.clicked.connect(self._handle_custom_action)
        custom_grid_layout.addWidget(self.add_custom_btn, 1, custom_columns - 1, alignment=Qt.AlignCenter)
        self._refresh_custom_action_button()

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if ok_btn is not None:
            ok_btn.setProperty("panelActionButton", True)
            ok_btn.setProperty("primaryAction", True)
            ok_btn.setText(self._t("common.ok", "OK"))
            add_shadow(ok_btn)
        if cancel_btn is not None:
            cancel_btn.setProperty("panelActionButton", True)
            cancel_btn.setProperty("secondaryAction", True)
            cancel_btn.setText(self._t("common.cancel", "Cancel"))
            add_shadow(cancel_btn)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailFieldKey", True)
        return label

    def _make_number_edit(self, minimum: int, maximum: int) -> QLineEdit:
        editor = QLineEdit()
        editor.setValidator(QIntValidator(minimum, maximum, self))
        editor.editingFinished.connect(self._apply_numeric_fields)
        return editor

    def _build_slider_row(self, label_text: str, minimum: int, maximum: int, handler) -> tuple[QWidget, QSlider, QLabel]:
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._dp(8))

        label = QLabel(label_text)
        label.setProperty("detailFieldKey", True)
        label.setMinimumWidth(self._dp(72))
        label.setMaximumWidth(self._dp(72))
        label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(label)

        slider = _HandleCursorSlider(Qt.Horizontal)
        slider.setRange(minimum, maximum)
        slider.valueChanged.connect(handler)
        slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        groove_h = self._dp(6)
        handle_d = self._dp(18)
        slider.set_slider_metrics(groove_h, handle_d)
        slider.setFixedHeight(max(self._dp(22), handle_d + self._dp(4)))
        slider.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(slider, 1)

        value_label = QLabel(str(minimum))
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value_label.setMinimumWidth(self._dp(42))
        value_label.setMaximumWidth(self._dp(56))
        value_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(value_label)
        layout.setStretch(0, 0)
        layout.setStretch(1, 1)
        layout.setStretch(2, 0)
        return row, slider, value_label

    def _on_hue_changed(self, hue: int):
        color = QColor.fromHsv(hue, self._selected_color.saturation(), self._selected_color.value())
        self._apply_color(color, preserve_custom=True)

    def _on_sv_changed(self, saturation: int, value: int):
        color = QColor.fromHsv(self._selected_color.hue() if self._selected_color.hue() >= 0 else 0, saturation, value)
        color.setAlpha(self._selected_color.alpha())
        self._apply_color(color, preserve_custom=True)

    def _on_hsv_slider_changed(self, _value: int):
        if self._updating_fields:
            return
        color = QColor.fromHsv(
            self.hue_value_slider.value() % 360,
            self.sat_value_slider.value(),
            self.val_value_slider.value(),
            self._selected_color.alpha(),
        )
        self._apply_color(color, preserve_custom=True)

    def _on_grid_saturation_changed(self, _value: int):
        if self._updating_fields:
            return
        hue = self._selected_color.hue() if self._selected_color.hue() >= 0 else 0
        saturation = int(round((self.grid_opacity_slider.value() / 100.0) * 255))
        color = QColor.fromHsv(hue, saturation, self._selected_color.value(), self._selected_color.alpha())
        self._apply_color(color, preserve_custom=True)

    def _on_rgb_slider_changed(self, _value: int):
        if self._updating_fields:
            return
        color = QColor(
            self.red_value_slider.value(),
            self.green_value_slider.value(),
            self.blue_value_slider.value(),
            self._selected_color.alpha(),
        )
        self._apply_color(color, preserve_custom=True)

    def _on_mode_tab_changed(self, index: int):
        # Spectrum uses an HTML field in the shared row; other tabs use saturation.
        if hasattr(self, "grid_saturation_row"):
            self.grid_saturation_row.setVisible(index != 1)
        if hasattr(self, "spectrum_html_row"):
            self.spectrum_html_row.setVisible(index == 1)

    def _apply_numeric_fields(self):
        if self._updating_fields:
            return
        hue_text = self.hue_edit.text().strip()
        sat_text = self.sat_edit.text().strip()
        val_text = self.val_edit.text().strip()
        red_text = self.red_edit.text().strip()
        green_text = self.green_edit.text().strip()
        blue_text = self.blue_edit.text().strip()

        if all(text for text in (red_text, green_text, blue_text)):
            color = QColor(int(red_text), int(green_text), int(blue_text))
            color.setAlpha(self._selected_color.alpha())
            self._apply_color(color, preserve_custom=True)
            return

        if all(text for text in (hue_text, sat_text, val_text)):
            color = QColor.fromHsv(
                int(hue_text) % 360,
                int(sat_text),
                int(val_text),
                self._selected_color.alpha(),
            )
            self._apply_color(color, preserve_custom=True)

    def _apply_html_field(self):
        if self._updating_fields:
            return
        text = self.html_edit.text().strip()
        if not text:
            return
        if not text.startswith("#"):
            text = f"#{text}"
        color = QColor(text)
        if color.isValid():
            self._apply_color(color, preserve_custom=True)

    def _apply_hex_color(self, color_hex: str):
        sender = self.sender()
        if sender in getattr(self, "_basic_swatches", []):
            self._selected_basic_index = self._basic_swatches.index(sender)
            self._selected_custom_index = -1
        elif sender in getattr(self, "_custom_swatches", []):
            self._selected_custom_index = self._custom_swatches.index(sender)
            self._selected_basic_index = -1
        color = QColor(color_hex)
        if color.isValid():
            self._apply_color(color, preserve_custom=False)

    def _apply_color(self, color: QColor, preserve_custom: bool):
        if not color.isValid():
            return
        hue = color.hue() if color.hue() >= 0 else 0
        alpha = color.alpha() if color.alpha() >= 0 else 255
        self._selected_color = QColor.fromHsv(hue, color.saturation(), color.value(), alpha)
        self._updating_fields = True
        self.hue_slider.set_hue(hue)
        self.sv_picker.set_hue(hue)
        self.sv_picker.set_sv(color.saturation(), color.value())
        self.hue_value_slider.setValue(hue)
        self.sat_value_slider.setValue(color.saturation())
        self.val_value_slider.setValue(color.value())
        saturation_pct = int(round((color.saturation() / 255.0) * 100))
        self.grid_opacity_slider.setValue(saturation_pct)
        self.hue_value_label.setText(str(hue))
        self.sat_value_label.setText(str(color.saturation()))
        self.val_value_label.setText(str(color.value()))
        self.grid_opacity_label.setText(f"{saturation_pct}%")
        self.red_value_slider.setValue(color.red())
        self.green_value_slider.setValue(color.green())
        self.blue_value_slider.setValue(color.blue())
        self.red_value_label.setText(str(color.red()))
        self.green_value_label.setText(str(color.green()))
        self.blue_value_label.setText(str(color.blue()))
        self.html_edit.setText(color.name())
        self.preview_swatch.setStyleSheet(f"background-color: {color.name()};")
        self._updating_fields = False
        self._update_swatch_selection(color.name(), preserve_custom=preserve_custom)

    def _update_swatch_selection(self, color_hex: str, preserve_custom: bool):
        normalized = QColor(color_hex).name()

        if not preserve_custom:
            self._selected_basic_index = -1
            self._selected_custom_index = -1

            for index, swatch in enumerate(self._basic_swatches):
                if swatch.color_hex() == normalized:
                    self._selected_basic_index = index
                    break

            for index, swatch in enumerate(self._custom_swatches):
                if swatch.color_hex() == normalized:
                    self._selected_custom_index = index
                    break

        for index, swatch in enumerate(self._basic_swatches):
            swatch.set_selected(index == self._selected_basic_index)

        for index, swatch in enumerate(self._custom_swatches):
            swatch.set_selected(index == self._selected_custom_index)

        self._refresh_custom_action_button()

    def _select_custom_index(self, index: int):
        self._selected_custom_index = index
        self._selected_basic_index = -1
        self._update_swatch_selection(self._selected_color.name(), preserve_custom=True)

    def _refresh_custom_action_button(self):
        index = self._selected_custom_index
        has_selected_color = (
            0 <= index < len(self._custom_swatches)
            and bool(self._custom_swatches[index].color_hex())
        )
        if has_selected_color:
            self.add_custom_btn.setIcon(self._custom_delete_icon)
            self.add_custom_btn.setToolTip(self._t("tool_editor.color.delete_custom", "Delete custom color"))
        else:
            self.add_custom_btn.setIcon(self._custom_add_icon)
            self.add_custom_btn.setToolTip(self._t("tool_editor.color.add_custom", "Add To Custom Colors"))

    def _handle_custom_action(self):
        index = self._selected_custom_index
        has_selected_color = (
            0 <= index < len(type(self)._custom_colors)
            and bool(type(self)._custom_colors[index])
        )
        if has_selected_color:
            self._delete_selected_custom_color()
        else:
            self._add_to_custom_colors()

    def _delete_selected_custom_color(self):
        index = self._selected_custom_index
        if not (0 <= index < len(type(self)._custom_colors)):
            return
        type(self)._custom_colors[index] = ""
        # Reuse the just-freed slot on the next add.
        type(self)._custom_insert_index = index
        type(self)._save_custom_colors_to_settings()
        self._custom_swatches[index].set_color("")
        self._selected_custom_index = -1
        self._update_swatch_selection(self._selected_color.name(), preserve_custom=True)

    def _add_to_custom_colors(self):
        color_hex = self._selected_color.name()
        current_colors = type(self)._custom_colors
        if color_hex in current_colors:
            index = current_colors.index(color_hex)
        else:
            # Prefer empty slots first, starting from the rolling insert cursor.
            start = type(self)._custom_insert_index % len(current_colors)
            index = -1
            for offset in range(len(current_colors)):
                candidate = (start + offset) % len(current_colors)
                if not current_colors[candidate]:
                    index = candidate
                    break
            if index < 0:
                index = start
            current_colors[index] = color_hex
            type(self)._custom_insert_index = (index + 1) % len(current_colors)
            self._custom_swatches[index].set_color(color_hex)
            type(self)._save_custom_colors_to_settings()
        self._selected_custom_index = index
        self._update_swatch_selection(color_hex, preserve_custom=True)



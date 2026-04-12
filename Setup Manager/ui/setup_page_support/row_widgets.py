"""Row widget classes for the Setup page catalog list."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QTransform
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import (
    DEFAULT_TOOL_ICON,
    TOOL_ICONS_DIR,
    TOOL_LIBRARY_TOOL_ICONS_DIR,
    TOOL_TYPE_TO_ICON,
)
from ui.widgets.common import AutoShrinkLabel, repolish_widget


class ToolNameCardWidget(QFrame):
    """Compact read-only tool card: icon + tool name only."""

    _TURNING_TOOL_TYPES = {
        "O.D Turning",
        "I.D Turning",
        "O.D Groove",
        "I.D Groove",
        "Face Groove",
        "O.D Thread",
        "I.D Thread",
        "Turn Thread",
        "Turn Drill",
        "Turn Spot Drill",
    }

    def __init__(self, tool: dict, parent=None):
        super().__init__(parent)
        self.tool = tool or {}
        self.setProperty("toolListCard", True)
        self.setProperty("detailToolCard", True)
        self.setProperty("selected", False)
        self.setMinimumHeight(58)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setStyleSheet("background-color: transparent;")
        icon_name = self._pick_icon_name((self.tool.get("tool_type") or "").strip())
        icon_path = self._resolve_tool_icon(icon_name)
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(QSize(34, 34))
            if self._should_mirror_icon():
                pixmap = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
            icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(40, 40)
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        tool_id = (self.tool.get("id") or "").strip()
        desc = (self.tool.get("description") or "").strip() or "No description"
        text = f"{tool_id} - {desc}" if tool_id else desc

        value = QLabel(text)
        value.setProperty("toolCardValue", True)
        value.setProperty("detailToolText", True)
        value.setWordWrap(True)
        value.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(value, 1)

    @staticmethod
    def _pick_icon_name(tool_type: str) -> str:
        mapped = TOOL_TYPE_TO_ICON.get(tool_type)
        return mapped if mapped else DEFAULT_TOOL_ICON

    def _should_mirror_icon(self) -> bool:
        spindle = str(self.tool.get("spindle") or "").strip().lower()
        tool_type = str(self.tool.get("tool_type") or "").strip()
        return spindle == "sub" and tool_type in self._TURNING_TOOL_TYPES

    @staticmethod
    def _resolve_tool_icon(icon_name: str) -> Path:
        local_path = TOOL_ICONS_DIR / icon_name
        if local_path.exists():
            return local_path
        shared_path = TOOL_LIBRARY_TOOL_ICONS_DIR / icon_name
        if shared_path.exists():
            return shared_path
        fallback_local = TOOL_ICONS_DIR / "tools_icon.svg"
        if fallback_local.exists():
            return fallback_local
        fallback_shared = TOOL_LIBRARY_TOOL_ICONS_DIR / DEFAULT_TOOL_ICON
        if fallback_shared.exists():
            return fallback_shared
        return local_path


class WorkRowWidget(QFrame):
    """Styled card widget for a single work entry in the list."""

    clicked = Signal()
    doubleClicked = Signal()

    def __init__(
        self,
        work_id: str,
        drawing_id: str,
        description: str,
        latest_text: str,
        headers: dict | None = None,
        no_runs_text: str = "No runs yet",
        parent=None,
    ):
        super().__init__(parent)
        self.setProperty("toolListCard", True)
        self.setProperty("workRowCard", True)
        self.setProperty("selected", False)
        self.setProperty("compactMode", False)
        self.setProperty("descriptionWrapped", False)
        self.setProperty("singleColumnMode", False)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(240)
        self._val_labels: list = []
        self._head_labels: list = []
        self._col_layouts: list = []
        self._column_wraps: dict = {}
        self._column_values: dict = {}
        self._column_texts: dict = {}
        self._compact_mode = False
        self._description_wrap_breakpoint = 430
        self._single_column_breakpoint = 350
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)
        self._root_layout = layout

        headers = headers or {}
        columns = [
            ("work_id", headers.get("work_id", "Work ID"), work_id or "-", 140),
            ("drawing", headers.get("drawing", "Drawing"), drawing_id or "-", 150),
            ("description", headers.get("description", "Description"), description or "-", 330),
            ("last_run", headers.get("last_run", "Last run"), latest_text or no_runs_text, 280),
        ]

        for key, title, value, stretch in columns:
            wrap = QWidget()
            wrap.setProperty("toolCardColumn", True)
            wrap.setStyleSheet("background: transparent;")
            wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            col = QVBoxLayout(wrap)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            self._col_layouts.append(col)

            header = QLabel(title)
            header.setProperty("toolCardHeader", True)
            header.setProperty("catalogRowHeader", True)
            header.setAlignment(Qt.AlignCenter)
            header.setWordWrap(True)
            self._head_labels.append(header)

            body = AutoShrinkLabel(value)
            body.setProperty("toolCardValue", True)
            body.setProperty("catalogRowValue", True)
            if key == "description":
                body.setProperty("catalogRowDescription", True)
            if key == "work_id":
                body.setProperty("catalogRowLead", True)
            body.setAlignment(Qt.AlignCenter)
            body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._val_labels.append(body)
            self._column_wraps[key] = wrap
            self._column_values[key] = body
            self._column_texts[key] = value

            col.addWidget(header)
            col.addWidget(body)
            layout.addWidget(wrap, stretch, Qt.AlignVCenter)

        layout.addStretch(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _set_responsive_property(self, name: str, value: bool) -> bool:
        value = bool(value)
        if bool(self.property(name)) == value:
            return False
        self.setProperty(name, value)
        return True

    @staticmethod
    def _split_responsive_token(text: str) -> str:
        value = (text or "").strip()
        if not value or len(value) <= 8:
            return value
        if "-" in value:
            pivot = value.find("-") + 1
            if 1 < pivot < len(value):
                return f"{value[:pivot]}\n{value[pivot:]}"
        pivot = max(4, len(value) // 2)
        return f"{value[:pivot]}\n{value[pivot:]}"

    @staticmethod
    def _set_label_point_size(label: QLabel, point_size: float):
        if isinstance(label, AutoShrinkLabel):
            label.set_target_point_size(point_size)
            return
        font = label.font()
        font.setPointSizeF(point_size)
        label.setFont(font)

    def _apply_responsive_layout(self, width: int):
        lay = self.layout()
        if lay is None:
            return

        description_wrap = self._column_wraps.get("description")
        description = self._column_values.get("description")
        work_id = self._column_values.get("work_id")
        state_changed = False
        single_column_mode = False
        description_wrapped = False

        if self._compact_mode:
            single_column_mode = width < self._single_column_breakpoint
            description_wrapped = not single_column_mode and width < self._description_wrap_breakpoint

            if single_column_mode:
                lay.setContentsMargins(10, 2, 10, 2)
                lay.setSpacing(6)
                v_size, h_size, col_spacing = 9.2, 8.2, 0
            elif description_wrapped:
                lay.setContentsMargins(10, 2, 10, 2)
                lay.setSpacing(7)
                v_size, h_size, col_spacing = 8.8, 8.4, 0
            elif width < 560:
                lay.setContentsMargins(11, 2, 9, 2)
                lay.setSpacing(8)
                v_size, h_size, col_spacing = 10.8, 9.0, 0
            else:
                lay.setContentsMargins(12, 2, 10, 2)
                lay.setSpacing(10)
                v_size, h_size, col_spacing = 11.2, 9.2, 0

            if description_wrap is not None:
                description_wrap.setVisible(not single_column_mode)
            if description is not None:
                description.setText(self._column_texts.get("description", ""))
                description.setWordWrap(description_wrapped)
                description.setMargin(0)
                description.setAlignment(Qt.AlignCenter)
                description.setMinimumHeight(38 if description_wrapped else 30)
                description.setMaximumHeight(38 if description_wrapped else 30)
                if isinstance(description, AutoShrinkLabel):
                    description.refresh_fit()
            if work_id is not None:
                work_id.setText(self._column_texts.get("work_id", ""))
                work_id.setWordWrap(False)
                work_id.setMargin(0)
                work_id.setAlignment(Qt.AlignCenter)
                work_id.setMinimumHeight(30)
                work_id.setMaximumHeight(30)
                if isinstance(work_id, AutoShrinkLabel):
                    work_id.refresh_fit()

            state_changed |= self._set_responsive_property("descriptionWrapped", description_wrapped)
            state_changed |= self._set_responsive_property("singleColumnMode", single_column_mode)
        elif width < 560:
            lay.setContentsMargins(7, 2, 7, 2)
            lay.setSpacing(7)
            v_size, h_size, col_spacing = 11.5, 8.6, 0
            if description_wrap is not None:
                description_wrap.setVisible(True)
            if description is not None:
                description.setText(self._column_texts.get("description", ""))
                description.setWordWrap(False)
                description.setMargin(0)
                description.setAlignment(Qt.AlignCenter)
                description.setMinimumHeight(30)
                description.setMaximumHeight(30)
                if isinstance(description, AutoShrinkLabel):
                    description.refresh_fit()
            if work_id is not None:
                work_id.setText(self._column_texts.get("work_id", ""))
                work_id.setWordWrap(False)
                work_id.setMargin(0)
                work_id.setAlignment(Qt.AlignCenter)
                work_id.setMinimumHeight(30)
                work_id.setMaximumHeight(30)
                if isinstance(work_id, AutoShrinkLabel):
                    work_id.refresh_fit()
            state_changed |= self._set_responsive_property("descriptionWrapped", False)
            state_changed |= self._set_responsive_property("singleColumnMode", False)
        else:
            lay.setContentsMargins(10, 2, 10, 2)
            lay.setSpacing(10)
            v_size, h_size, col_spacing = 12.8, 9.4, 0
            if description_wrap is not None:
                description_wrap.setVisible(True)
            if description is not None:
                description.setText(self._column_texts.get("description", ""))
                description.setWordWrap(False)
                description.setMargin(0)
                description.setAlignment(Qt.AlignCenter)
                description.setMinimumHeight(30)
                description.setMaximumHeight(30)
                if isinstance(description, AutoShrinkLabel):
                    description.refresh_fit()
            if work_id is not None:
                work_id.setText(self._column_texts.get("work_id", ""))
                work_id.setWordWrap(False)
                work_id.setMargin(0)
                work_id.setAlignment(Qt.AlignCenter)
                work_id.setMinimumHeight(30)
                work_id.setMaximumHeight(30)
                if isinstance(work_id, AutoShrinkLabel):
                    work_id.refresh_fit()
            state_changed |= self._set_responsive_property("descriptionWrapped", False)
            state_changed |= self._set_responsive_property("singleColumnMode", False)

        if state_changed:
            repolish_widget(self)
            for lbl in self._val_labels + self._head_labels:
                repolish_widget(lbl)

        for col in self._col_layouts:
            col.setSpacing(col_spacing)
        for lbl in self._val_labels:
            if isinstance(lbl, AutoShrinkLabel):
                lbl.set_target_point_size(v_size)
            else:
                f = lbl.font()
                f.setPointSizeF(v_size)
                lbl.setFont(f)
        for lbl in self._head_labels:
            f = lbl.font()
            f.setPointSizeF(h_size)
            lbl.setFont(f)

        if description is not None and isinstance(description, AutoShrinkLabel):
            self._set_label_point_size(description, 8.6 if self._compact_mode and description_wrapped else v_size)
        if work_id is not None and isinstance(work_id, AutoShrinkLabel):
            self._set_label_point_size(work_id, 8.8 if self._compact_mode and single_column_mode else v_size)

    def set_compact_mode(self, compact: bool):
        self._compact_mode = bool(compact)
        self.setProperty("compactMode", self._compact_mode)
        for key in ("drawing", "last_run"):
            wrap = self._column_wraps.get(key)
            if wrap is not None:
                wrap.setVisible(not self._compact_mode)
        description = self._column_values.get("description")
        if description is not None:
            description.setMargin(0)
            description.setAlignment(Qt.AlignCenter)
        work_id = self._column_values.get("work_id")
        if work_id is not None:
            work_id.setAlignment(Qt.AlignCenter)
            work_id.setMargin(0)
        repolish_widget(self)
        for lbl in self._val_labels + self._head_labels:
            repolish_widget(lbl)
        self._apply_responsive_layout(max(1, self.width()))
        self.updateGeometry()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


__all__ = ["ToolNameCardWidget", "WorkRowWidget"]

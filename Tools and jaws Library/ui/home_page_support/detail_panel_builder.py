"""DetailPanelBuilder: Coordinator for HomePage detail panel rendering.

Responsibilities:
- Receives a Tool dict and renders all details to existing detail_layout widgets
- Manages the full detail panel including header, info grid, components, and preview
- Preserves exact HomePage rendering logic (no behavior changes)
- Delegates formatting/layout rules to shared modules

HomePage retains:
- detail_layout ownership and clearing logic
- detail_panel and detail_scroll widget references
- Signal connections for list selection
- _get_selected_tool() and other selection queries
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shared.ui.helpers.editor_helpers import create_titled_section
from config import MILLING_TOOL_TYPES, TURNING_TOOL_TYPES

if TYPE_CHECKING:
    from home_page import HomePage


class DetailPanelBuilder:
    """Coordinator for rendering Tool details into HomePage detail panel.
    
    Usage:
        builder = DetailPanelBuilder(page)
        builder.populate_details(selected_tool)
    """

    def __init__(self, page: HomePage):
        """Initialize builder with reference to HomePage for rendering context.
        
        Args:
            page: HomePage instance (provides detail_layout, _t, _load_preview_content, etc.)
        """
        self.page = page

    def populate_details(self, tool: dict | None) -> None:
        """Main entry point: render all tool details to detail panel.
        
        Args:
            tool: Tool dict or None to show placeholder
        """
        self._clear_details()
        if not tool:
            self.page.detail_layout.addWidget(self._build_placeholder_details())
            return

        support_parts = (
            tool.get("support_parts", [])
            if isinstance(tool.get("support_parts"), list)
            else json.loads(tool.get("support_parts", "[]") or "[]")
        )

        card = QFrame()
        card.setProperty("subCard", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Build detail header (title + metadata row)
        header = self._build_detail_header(tool)
        layout.addWidget(header)

        # Build info grid (tool specs: dimensions, angles, etc.)
        info_grid = self._build_info_grid(tool)
        layout.addLayout(info_grid)

        # Build components panel (holder, cutting part, spares)
        components_panel = self._build_components_panel(tool, support_parts)
        layout.addWidget(components_panel)

        # Inline 3D preview section intentionally removed.

        layout.addStretch(1)
        self.page.detail_layout.addWidget(card)

    def _build_detail_header(self, tool: dict) -> QFrame:
        """Build header frame with title, ID, type badge, and head badge."""
        header = QFrame()
        header.setProperty("detailHeader", True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 12)
        header_layout.setSpacing(4)

        # Title row: description + tool ID
        name_label = QLabel(
            tool.get("description", "").strip()
            or self.page._t(
                "tool_library.common.no_description", "No description"
            )
        )
        name_label.setProperty("detailHeroTitle", True)
        name_label.setWordWrap(True)
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        tool_id_text = self.page._tool_id_display_value(tool.get("id", "")) or "-"
        id_label = QLabel(tool_id_text)
        id_label.setProperty("detailHeroTitle", True)
        id_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title_row.addWidget(name_label, 1)
        title_row.addWidget(id_label, 0, Qt.AlignRight)

        # Metadata row: tool type badge + head badge
        meta_row = QHBoxLayout()
        badge = QLabel(self.page._localized_tool_type(tool.get("tool_type", "")))
        badge.setProperty("toolBadge", True)
        meta_row.addWidget(badge, 0, Qt.AlignLeft)

        tool_head = (tool.get("tool_head", "HEAD1") or "HEAD1").strip().upper()
        head_badge = QLabel(tool_head)
        head_badge.setProperty("toolBadge", True)
        meta_row.addStretch(1)
        meta_row.addWidget(head_badge, 0, Qt.AlignRight)

        header_layout.addLayout(title_row)
        header_layout.addLayout(meta_row)
        return header

    def _build_info_grid(self, tool: dict) -> QGridLayout:
        """Build the info grid with tool specifications.
        
        Uses shared apply_tool_detail_layout_rules to determine field layout.
        Returns layout (not widget) for direct insertion into parent.
        """
        from ui.home_page_support.detail_layout_rules import apply_tool_detail_layout_rules

        raw_cutting_type = tool.get("cutting_type", "Insert")
        raw_tool_type = tool.get("tool_type", "")
        turning_drill_type = self.page._is_turning_drill_tool_type(raw_tool_type)

        # Build 6-column grid (2-box rows: 3+3, 3-box rows: 2+2+2)
        info = QGridLayout()
        info.setHorizontalSpacing(6)
        info.setVerticalSpacing(8)
        for col in range(6):
            info.setColumnStretch(col, 1)

        # Handle angle value with backward compatibility
        angle_value = str(tool.get("drill_nose_angle", ""))
        if not angle_value.strip():
            angle_value = str(tool.get("nose_corner_radius", ""))

        def _fallback_pair_row(
            left_label: str, left_value: str, right_label: str, right_value: str
        ) -> None:
            from ui.home_page_support.detail_fields_builder import build_detail_field
            info.addWidget(
                build_detail_field(
                    page=self.page,
                    label_text=left_label,
                    value_text=left_value,
                ),
                1,
                0,
                1,
                3,
                Qt.AlignTop,
            )
            info.addWidget(
                build_detail_field(
                    page=self.page,
                    label_text=right_label,
                    value_text=right_value,
                ),
                1,
                3,
                1,
                3,
                Qt.AlignTop,
            )

        # Let apply_tool_detail_layout_rules determine the grid layout
        full_row = apply_tool_detail_layout_rules(
            tool=tool,
            tool_head=(tool.get("tool_head", "HEAD1") or "HEAD1").strip().upper(),
            raw_tool_type=raw_tool_type,
            raw_cutting_type=raw_cutting_type,
            turning_drill_type=turning_drill_type,
            angle_value=angle_value,
            milling_tool_types=MILLING_TOOL_TYPES,
            turning_tool_types=TURNING_TOOL_TYPES,
            add_two_box_row=lambda row, ll, lv, rl, rv: self._add_two_box_row(
                info, row, ll, lv, rl, rv
            ),
            add_three_box_row=lambda row, l1, v1, l2, v2, l3, v3: (
                self._add_three_box_row(info, row, l1, v1, l2, v2, l3, v3)
            ),
            add_fallback_pair_row=_fallback_pair_row,
            translate=self.page._t,
        )

        # Add notes field (spans full width)
        notes_text = tool.get("notes", tool.get("spare_parts", ""))
        if notes_text:
            from ui.home_page_support.detail_fields_builder import build_detail_field
            notes_field = build_detail_field(
                page=self.page,
                label_text=self.page._t("tool_library.field.notes", "Notes"),
                value_text=notes_text,
                multiline=True,
            )
            info.addWidget(notes_field, full_row, 0, 1, 6)

        return info

    def _add_two_box_row(
        self, info: QGridLayout, row: int, left_label: str, left_value: str,
        right_label: str, right_value: str,
    ) -> None:
        """Add a two-column detail field row to the grid."""
        from ui.home_page_support.detail_fields_builder import build_detail_field

        info.addWidget(
            build_detail_field(
                page=self.page, label_text=left_label, value_text=left_value
            ),
            row,
            0,
            1,
            3,
            Qt.AlignTop,
        )
        info.addWidget(
            build_detail_field(
                page=self.page, label_text=right_label, value_text=right_value
            ),
            row,
            3,
            1,
            3,
            Qt.AlignTop,
        )

    def _add_three_box_row(
        self, info: QGridLayout, row: int, first_label: str, first_value: str,
        second_label: str, second_value: str, third_label: str, third_value: str,
    ) -> None:
        """Add a three-column detail field row to the grid."""
        from ui.home_page_support.detail_fields_builder import build_detail_field

        info.addWidget(
            build_detail_field(
                page=self.page, label_text=first_label, value_text=first_value
            ),
            row,
            0,
            1,
            2,
            Qt.AlignTop,
        )
        info.addWidget(
            build_detail_field(
                page=self.page, label_text=second_label, value_text=second_value
            ),
            row,
            2,
            1,
            2,
            Qt.AlignTop,
        )
        info.addWidget(
            build_detail_field(
                page=self.page, label_text=third_label, value_text=third_value
            ),
            row,
            4,
            1,
            2,
            Qt.AlignTop,
        )

    def _build_components_panel(
        self, tool: dict, support_parts: list
    ) -> QFrame:
        """Build the Tool Components section.
        
        Displays holder, cutting part, and spare parts with collapsible spares.
        """
        frame = create_titled_section(
            self.page._t(
                "tool_library.section.tool_components", "Tool components"
            )
        )
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(6)

        body_host = QFrame()
        body_host.setObjectName("toolComponentsBodyHost")
        body_host.setStyleSheet(
            "QFrame#toolComponentsBodyHost {"
            "  background-color: #ffffff;"
            "  border: none;"
            "  border-radius: 4px;"
            "}"
        )
        body_layout = QVBoxLayout(body_host)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(6)

        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(4)

        normalized = self._normalized_component_items(tool)
        spare_index = self._spare_index_by_component(support_parts)

        last_group = None
        for idx, item in enumerate(normalized):
            group = (item.get("group") or "").strip()
            if group != last_group:
                last_group = group
                if group:
                    group_label = QLabel(group)
                    group_label.setProperty("detailFieldKey", True)
                    group_label.setStyleSheet(
                        "background: transparent;"
                        "font-weight: 600; font-size: 9pt; color: #5a6a7a;"
                        "border-bottom: 1px solid #d0d8e0; padding: 4px 0 2px 0;"
                    )
                    list_layout.addWidget(group_label)

            display_name = item.get(
                "label", self.page._t("tool_library.field.part", "Part")
            )
            component_key = self._component_key(item, idx)
            linked_spares = spare_index.get(component_key, [])

            row_card, code_lbl, code_style_default, code_style_hover = (
                self._build_component_row_widget(item, display_name)
            )
            row_layout = row_card.layout()

            if linked_spares:
                arrow_style_default = (
                    "background: transparent; border: none; padding: 0 4px;"
                )
                arrow_left, arrow_up = self._component_toggle_arrow_pixmaps()
                arrow_lbl = QLabel()
                arrow_lbl.setPixmap(arrow_left)
                arrow_lbl.setStyleSheet(arrow_style_default)
                arrow_lbl.setAlignment(Qt.AlignCenter)
                arrow_lbl.setFixedWidth(24)
                arrow_lbl.setCursor(Qt.PointingHandCursor)
                arrow_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
                row_layout.addWidget(arrow_lbl, 0)
                code_lbl.setCursor(Qt.PointingHandCursor)

            list_layout.addWidget(row_card)

            if linked_spares:
                spare_host = self._build_component_spare_host(linked_spares)
                self._wire_spare_toggle(
                    frame=frame,
                    spare_host=spare_host,
                    code_lbl=code_lbl,
                    arrow_lbl=arrow_lbl,
                    arrow_up=arrow_up,
                    arrow_left=arrow_left,
                    code_style_default=code_style_default,
                    code_style_hover=code_style_hover,
                )
                list_layout.addWidget(spare_host)

        if not normalized:
            empty_row = QFrame()
            empty_row.setProperty("editorFieldCard", True)
            empty_row_layout = QVBoxLayout(empty_row)
            empty_row_layout.setContentsMargins(0, 0, 0, 0)
            empty_row_layout.setSpacing(0)

            empty_edit = QLineEdit("-")
            empty_edit.setReadOnly(True)
            empty_edit.setFocusPolicy(Qt.NoFocus)
            empty_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            empty_row_layout.addWidget(empty_edit)
            list_layout.addWidget(empty_row)

        body_layout.addLayout(list_layout)
        layout.addWidget(body_host)
        return frame

    def _build_placeholder_details(self) -> QFrame:
        """Build empty state when no tool is selected."""
        card = QFrame()
        card.setProperty("subCard", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel(
            self.page._t(
                "tool_library.section.tool_details", "Tool details"
            )
        )
        title.setProperty("detailSectionTitle", True)
        layout.addWidget(title)
        info = QLabel(
            self.page._t(
                "tool_library.message.select_tool_for_details",
                "Select a tool to view details.",
            )
        )
        info.setProperty("detailHint", True)
        info.setWordWrap(True)
        layout.addWidget(info)

        preview = QFrame()
        preview.setProperty("diagramPanel", True)
        p = QVBoxLayout(preview)
        p.setContentsMargins(12, 12, 12, 12)
        p.addStretch(1)
        layout.addWidget(preview, 1)
        return card

    # ========== Helper Methods (Component Rendering) ==========

    def _component_toggle_arrow_pixmaps(self) -> tuple[QPixmap, QPixmap]:
        """Get cached arrow pixmaps (left/up) or create them."""
        cached = getattr(self.page, "_component_toggle_arrows", None)
        if cached is not None:
            return cached

        canvas_size = 20
        font = self.page.font()
        font.setPixelSize(16)
        font.setBold(True)

        up_arrow = QPixmap(canvas_size, canvas_size)
        up_arrow.fill(Qt.transparent)

        painter = QPainter(up_arrow)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setFont(font)
        painter.setPen(QColor("#2b3640"))
        painter.drawText(up_arrow.rect(), Qt.AlignCenter, "\u25b2")
        painter.end()

        left_arrow = up_arrow.transformed(
            QTransform().rotate(-90), Qt.SmoothTransformation
        )
        self.page._component_toggle_arrows = (left_arrow, up_arrow)
        return (left_arrow, up_arrow)

    @staticmethod
    def _component_key(item: dict, fallback_idx: int) -> str:
        """Generate unique key for a component item."""
        explicit = (item.get("component_key") or "").strip()
        if explicit:
            return explicit
        role = (item.get("role") or "component").strip().lower()
        code = (item.get("code") or "").strip()
        if code:
            return f"{role}:{code}"
        return f"{role}:idx:{fallback_idx}"

    def _normalized_component_items(self, tool: dict) -> list[dict]:
        """Normalize component items from tool dict."""
        component_items = tool.get("component_items", [])
        if isinstance(component_items, str):
            try:
                component_items = json.loads(component_items or "[]")
            except Exception:
                component_items = []

        normalized: list[dict] = []
        if isinstance(component_items, list):
            for idx, item in enumerate(component_items):
                if not isinstance(item, dict):
                    continue
                role = (item.get("role") or "").strip().lower()
                if role not in {"holder", "cutting", "support"}:
                    continue
                code = (item.get("code") or "").strip()
                if not code:
                    continue
                try:
                    order = int(item.get("order", idx))
                except Exception:
                    order = idx
                normalized.append(
                    {
                        "role": role,
                        "label": (item.get("label") or "").strip(),
                        "code": code,
                        "link": (item.get("link") or "").strip(),
                        "group": (item.get("group") or "").strip(),
                        "component_key": (item.get("component_key") or "").strip(),
                        "order": order,
                    }
                )

        normalized.sort(key=lambda entry: int(entry.get("order", 0)))
        return normalized

    @staticmethod
    def _spare_index_by_component(support_parts: list | None) -> dict[str, list[dict]]:
        """Index spare parts by component key."""
        index: dict[str, list[dict]] = {}
        for part in support_parts or []:
            if isinstance(part, str):
                try:
                    part = json.loads(part)
                except Exception:
                    part = {"name": part, "code": "", "link": "", "component_key": ""}
            if not isinstance(part, dict):
                continue
            part_key = (
                (part.get("component_key") or "").strip()
                or (part.get("component") or "").strip()
                or (part.get("component_code") or "").strip()
            )
            if not part_key:
                continue
            index.setdefault(part_key, []).append(part)
        return index

    def _build_component_row_widget(
        self, item: dict, display_name: str
    ) -> tuple[QFrame, QLabel, str, str]:
        """Build a single component row (button + code label)."""
        row_card = QFrame()
        row_card.setProperty("editorFieldCard", True)
        row_layout = QHBoxLayout(row_card)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        button_text = (display_name or "").strip()
        btn = QPushButton(button_text)
        btn.setProperty("panelActionButton", True)
        btn.setProperty("componentCompact", True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(
            (item.get("link") or "").strip()
            or self.page._t(
                "tool_library.part.no_link",
                "No link set for: {name}",
                name=display_name,
            )
        )
        btn.setMinimumWidth(100)
        fm = QFontMetrics(btn.font())
        required_width = fm.horizontalAdvance(button_text) + 34
        btn.setFixedWidth(max(88, min(360, required_width)))
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        btn.clicked.connect(lambda _=False, p=item: self.page.part_clicked(p))
        row_layout.addWidget(btn, 0)

        raw_code = (item.get("code", "") or "").strip()
        code_lbl = QLabel(raw_code if raw_code else "-")
        code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        code_style_default = (
            "background: transparent;"
            "border: none;"
            "padding: 0 2px;"
            "font-size: 11pt;"
            "color: #22303c;"
            "font-weight: 400;"
            "border-bottom: 1px solid transparent;"
        )
        code_style_hover = (
            "background: transparent;"
            "border: none;"
            "padding: 0 2px;"
            "font-size: 11pt;"
            "color: #1f5f9a;"
            "font-weight: 400;"
            "border-bottom: 1px solid #1f5f9a;"
        )
        code_lbl.setStyleSheet(code_style_default)
        row_layout.addWidget(code_lbl, 1)
        return row_card, code_lbl, code_style_default, code_style_hover

    def _build_component_spare_host(
        self, linked_spares: list[dict]
    ) -> QFrame:
        """Build container for spare parts (initially hidden, collapsible)."""
        spare_host = QFrame()
        spare_host.setProperty("editorFieldGroup", True)
        spare_host_layout = QVBoxLayout(spare_host)
        spare_host_layout.setContentsMargins(12, 4, 0, 2)
        spare_host_layout.setSpacing(4)
        spare_host.setVisible(False)

        for spare in linked_spares:
            spare_row = QFrame()
            spare_row.setProperty("editorFieldCard", True)
            spare_row_layout = QHBoxLayout(spare_row)
            spare_row_layout.setContentsMargins(0, 0, 0, 0)
            spare_row_layout.setSpacing(8)

            spare_name = (
                spare.get("name")
                or self.page._t("tool_library.field.part", "Part")
            ).strip()
            spare_btn = QPushButton(spare_name)
            spare_btn.setProperty("panelActionButton", True)
            spare_btn.setProperty("componentCompact", True)
            spare_btn.setCursor(Qt.PointingHandCursor)
            spare_btn.setToolTip(
                (spare.get("link") or "").strip()
                or self.page._t(
                    "tool_library.part.no_link",
                    "No link set for: {name}",
                    name=spare_name,
                )
            )
            spare_btn_fm = QFontMetrics(spare_btn.font())
            spare_required_width = spare_btn_fm.horizontalAdvance(spare_name) + 48
            spare_btn.setFixedWidth(max(110, min(360, spare_required_width)))
            spare_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            spare_btn.clicked.connect(lambda _=False, p=spare: self.page.part_clicked(p))

            spare_code = (spare.get("code") or "").strip()
            spare_code_lbl = QLabel(spare_code if spare_code else "-")
            spare_code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            spare_code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            spare_code_lbl.setStyleSheet(
                "background: transparent;"
                "border: none;"
                "padding: 0 2px;"
                "font-size: 10.5pt;"
                "color: #22303c;"
            )

            spare_row_layout.addWidget(spare_btn, 0)
            spare_row_layout.addWidget(spare_code_lbl, 1)
            spare_host_layout.addWidget(spare_row)

        return spare_host

    def _wire_spare_toggle(
        self,
        *,
        frame: QFrame,
        spare_host: QFrame,
        code_lbl: QLabel,
        arrow_lbl: QLabel,
        arrow_up: QPixmap,
        arrow_left: QPixmap,
        code_style_default: str,
        code_style_hover: str,
    ) -> None:
        """Wire spare parts toggle on component rows."""

        def _set_code_hover(hovered: bool):
            code_lbl.setStyleSheet(
                code_style_hover if hovered else code_style_default
            )

        def _toggle_spares(_e):
            visible = not spare_host.isVisible()
            spare_host.setVisible(visible)
            arrow_lbl.setPixmap(arrow_up if visible else arrow_left)
            _set_code_hover(False)
            frame.updateGeometry()
            frame.update()

        def _hover_enter(_e):
            _set_code_hover(True)

        def _hover_leave(_e):
            _set_code_hover(False)

        code_lbl.mousePressEvent = _toggle_spares
        arrow_lbl.mousePressEvent = _toggle_spares
        code_lbl.enterEvent = _hover_enter
        code_lbl.leaveEvent = _hover_leave
        arrow_lbl.enterEvent = _hover_enter
        arrow_lbl.leaveEvent = _hover_leave

    def _clear_details(self) -> None:
        """Clear all widgets from detail_layout."""
        while self.page.detail_layout.count():
            item = self.page.detail_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()


def populate_detail_panel(page, tool: dict | None) -> None:
    """Compatibility wrapper used by HomePage.populate_details."""
    DetailPanelBuilder(page).populate_details(tool)

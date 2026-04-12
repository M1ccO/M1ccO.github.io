"""Component panel builders for HomePage detail cards.

HomePage remains the widget/state owner. This module centralizes repetitive
component/spare rendering and compatibility normalization for legacy tool rows.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from shared.ui.helpers.editor_helpers import create_titled_section


def _component_toggle_arrow_pixmaps(page) -> tuple[QPixmap, QPixmap]:
    cached = getattr(page, "_component_toggle_arrows", None)
    if cached is not None:
        return cached

    canvas_size = 20
    font = page.font()
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

    left_arrow = up_arrow.transformed(QTransform().rotate(-90), Qt.SmoothTransformation)
    page._component_toggle_arrows = (left_arrow, up_arrow)
    return page._component_toggle_arrows


def _component_key(item: dict, fallback_idx: int) -> str:
    explicit = (item.get("component_key") or "").strip()
    if explicit:
        return explicit
    role = (item.get("role") or "component").strip().lower()
    code = (item.get("code") or "").strip()
    if code:
        return f"{role}:{code}"
    return f"{role}:idx:{fallback_idx}"


def _legacy_component_candidates(page, tool: dict) -> list[dict]:
    """Build compatibility rows when tool data predates `component_items`."""
    raw_cutting_name = tool.get("cutting_type", "")
    cutting_name = page._localized_cutting_type(raw_cutting_name) if raw_cutting_name else page._t(
        "tool_library.field.cutting_part",
        "Cutting part",
    )
    candidates = [
        {
            "role": "holder",
            "label": page._t("tool_library.field.holder", "Holder"),
            "code": tool.get("holder_code", ""),
            "link": (tool.get("holder_link", "") or "").strip(),
            "group": "",
            "component_key": "holder:" + (tool.get("holder_code", "") or "").strip(),
            "order": 0,
        },
        {
            "role": "holder",
            "label": page._t("tool_library.field.add_element", "Add. Element"),
            "code": tool.get("holder_add_element", ""),
            "link": (tool.get("holder_add_element_link", "") or "").strip(),
            "group": "",
            "component_key": "holder:" + (tool.get("holder_add_element", "") or "").strip(),
            "order": 1,
        },
        {
            "role": "cutting",
            "label": cutting_name,
            "code": tool.get("cutting_code", ""),
            "link": (tool.get("cutting_link", "") or "").strip(),
            "group": "",
            "component_key": "cutting:" + (tool.get("cutting_code", "") or "").strip(),
            "order": 2,
        },
        {
            "role": "cutting",
            "label": page._t("tool_library.field.add_cutting", "Add. {cutting_type}", cutting_type=cutting_name),
            "code": tool.get("cutting_add_element", ""),
            "link": (tool.get("cutting_add_element_link", "") or "").strip(),
            "group": "",
            "component_key": "cutting:" + (tool.get("cutting_add_element", "") or "").strip(),
            "order": 3,
        },
    ]
    return [item for item in candidates if (item.get("code") or "").strip()]


def _normalized_component_items(page, tool: dict) -> list[dict]:
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

    if not normalized:
        normalized.extend(_legacy_component_candidates(page, tool))

    normalized.sort(key=lambda entry: int(entry.get("order", 0)))
    return normalized


def _spare_index_by_component(support_parts: list | None) -> dict[str, list[dict]]:
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


def _build_component_row_widget(page, item: dict, display_name: str) -> tuple[QFrame, QLabel, str, str]:
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
        or page._t("tool_library.part.no_link", "No link set for: {name}", name=display_name)
    )
    btn.setMinimumWidth(100)
    fm = QFontMetrics(btn.font())
    required_width = fm.horizontalAdvance(button_text) + 34
    btn.setFixedWidth(max(88, min(360, required_width)))
    btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    btn.clicked.connect(lambda _=False, p=item: page.part_clicked(p))
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


def _build_component_spare_host(page, linked_spares: list[dict]) -> QFrame:
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

        spare_name = (spare.get("name") or page._t("tool_library.field.part", "Part")).strip()
        spare_btn = QPushButton(spare_name)
        spare_btn.setProperty("panelActionButton", True)
        spare_btn.setProperty("componentCompact", True)
        spare_btn.setCursor(Qt.PointingHandCursor)
        spare_btn.setToolTip(
            (spare.get("link") or "").strip()
            or page._t("tool_library.part.no_link", "No link set for: {name}", name=spare_name)
        )
        spare_btn_fm = QFontMetrics(spare_btn.font())
        spare_required_width = spare_btn_fm.horizontalAdvance(spare_name) + 48
        spare_btn.setFixedWidth(max(110, min(360, spare_required_width)))
        spare_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        spare_btn.clicked.connect(lambda _=False, p=spare: page.part_clicked(p))

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
    def _set_code_hover(hovered: bool):
        code_lbl.setStyleSheet(code_style_hover if hovered else code_style_default)

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


def build_components_panel(page, tool: dict, support_parts: list | None):
    frame = create_titled_section(page._t("tool_library.section.tool_components", "Tool components"))
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
    normalized = _normalized_component_items(page, tool)
    spare_index = _spare_index_by_component(support_parts)

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

        display_name = item.get("label", page._t("tool_library.field.part", "Part"))
        component_key = _component_key(item, idx)
        linked_spares = spare_index.get(component_key, [])
        row_card, code_lbl, code_style_default, code_style_hover = _build_component_row_widget(
            page, item, display_name
        )
        row_layout = row_card.layout()

        if linked_spares:
            arrow_style_default = "background: transparent; border: none; padding: 0 4px;"
            arrow_left, arrow_up = _component_toggle_arrow_pixmaps(page)
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
            spare_host = _build_component_spare_host(page, linked_spares)
            _wire_spare_toggle(
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


from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .detail_fields import clear_section, make_detail_field


class AdaptiveColumnsWidget(QWidget):
    """Lay out child cards in two columns when space allows, else stack vertically."""

    def __init__(self, switch_width: int = 640, parent=None):
        super().__init__(parent)
        self._switch_width = switch_width
        self.setProperty("adaptiveColumnsHost", True)
        self._layout = QBoxLayout(QBoxLayout.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

    def add_widget(self, widget: QWidget):
        self._layout.addWidget(widget, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        direction = QBoxLayout.TopToBottom if event.size().width() < self._switch_width else QBoxLayout.LeftToRight
        if self._layout.direction() != direction:
            self._layout.setDirection(direction)


def set_jaw_overview(
    detail_sections: dict,
    draw_service,
    translate_fn: Callable,
    main_jaw_id: str,
    sub_jaw_id: str,
    main_stop_screws: str = "",
    sub_stop_screws: str = "",
):
    """Build the jaw overview detail section from work jaw data."""
    clear_section(detail_sections, "jaws")
    layout = detail_sections["jaws"]
    layout.setSpacing(4)

    row_host = AdaptiveColumnsWidget()

    def _jaw_box(label: str, jaw_id: str, stop_screws: str):
        jaw = draw_service.get_full_jaw(jaw_id) if jaw_id else None
        box = QFrame()
        box.setProperty("jawGroupHost", True)
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        box_l = QVBoxLayout(box)
        box_l.setContentsMargins(0, 0, 0, 0)
        box_l.setSpacing(2)
        head = QLabel(label)
        head.setProperty("jawGroupTitle", True)
        box_l.addWidget(head)
        if not jaw:
            missing = QLabel(translate_fn("setup_page.field.not_specified", "Not specified"))
            missing.setProperty("detailHint", True)
            box_l.addWidget(missing)
            return box
        box_l.addWidget(make_detail_field(translate_fn("setup_page.field.jaw_id", "Jaw ID"), jaw.get("jaw_id", "") or "-"))
        box_l.addWidget(make_detail_field(translate_fn("setup_page.field.type", "Type"), jaw.get("jaw_type", "") or "-"))
        clamping = (jaw.get("clamping_diameter_text") or "").strip() or "-"
        box_l.addWidget(make_detail_field(translate_fn("setup_page.field.clamping", "Clamping"), clamping))
        stop_screws = (stop_screws or "").strip()
        if stop_screws:
            box_l.addWidget(make_detail_field(translate_fn("setup_page.field.stop_screws", "Stop Screws"), stop_screws))
        return box

    row_host.add_widget(_jaw_box(translate_fn("setup_page.field.sp1", "SP1"), main_jaw_id, main_stop_screws))
    row_host.add_widget(_jaw_box(translate_fn("setup_page.field.sp2", "SP2"), sub_jaw_id, sub_stop_screws))
    layout.addWidget(row_host)


def set_tool_cards(
    detail_sections: dict,
    draw_service,
    translate_fn: Callable,
    key: str,
    tool_assignments: list,
):
    """Build tool assignment cards in the given detail section."""
    clear_section(detail_sections, key)
    layout = detail_sections[key]
    normalized = []
    for entry in (tool_assignments or []):
        if isinstance(entry, dict):
            tool_id = str(entry.get("tool_id") or entry.get("id") or "").strip()
            raw_uid = entry.get("tool_uid", entry.get("uid"))
            try:
                tool_uid = int(raw_uid) if raw_uid is not None and str(raw_uid).strip() else None
            except Exception:
                tool_uid = None
            override_id = str(entry.get("override_id") or "").strip()
            override_description = str(entry.get("override_description") or "").strip()
            pot = str(entry.get("pot") or "").strip()
        else:
            tool_id = str(entry or "").strip()
            tool_uid = None
            override_id = ""
            override_description = ""
            pot = ""
        if tool_id:
            normalized.append((tool_id, tool_uid, override_id, override_description, pot))

    if not normalized:
        placeholder = QLabel(translate_fn("setup_page.message.no_tools_assigned", "No tools assigned"))
        placeholder.setProperty("detailHint", True)
        layout.addWidget(placeholder)
        return

    for tool_id, tool_uid, override_id, override_description, pot in normalized:
        tool = None
        if tool_uid is not None:
            tool = draw_service.get_tool_ref_by_uid(tool_uid)
        if not tool:
            tool = draw_service.get_tool_ref(tool_id)
        if not tool:
            deleted_label = translate_fn("work_editor.tools.deleted_tool", "DELETED TOOL")
            display_id = override_id or tool_id
            text = f"{display_id} - {deleted_label}" if display_id else deleted_label
        else:
            display_id = override_id or tool_id
            desc = override_description or (tool.get("description") or "").strip()
            text = f"{display_id} - {desc}" if desc else display_id

        row = QFrame()
        row.setProperty("toolCardRow", True)
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 4, 6, 4)
        row_layout.setSpacing(8)

        text_lbl = QLabel(text)
        text_lbl.setWordWrap(False)
        text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_lbl.setStyleSheet("background: transparent; font-size: 14pt; font-weight: 600; color: #171a1d;")
        row_layout.addWidget(text_lbl, 1)

        if pot:
            pot_lbl = QLabel(pot)
            pot_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pot_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            pot_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            pot_lbl.setStyleSheet("background: transparent; font-size: 14pt; font-weight: 700; color: #171a1d;")
            row_layout.addWidget(pot_lbl, 0)

        layout.addWidget(row)

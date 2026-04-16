from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
    from shared.ui.helpers.editor_helpers import create_titled_section, setup_editor_dialog
except ModuleNotFoundError:
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
    from editor_helpers import create_titled_section, setup_editor_dialog

from .tool_actions import populate_default_pots


def _collect_pot_editor_items(dialog: Any) -> dict[str, dict[str, list[tuple[Any, dict, str]]]]:
    grouped: dict[str, dict[str, list[tuple[Any, dict, str]]]] = {}
    for head_name, ordered_list in dialog._ordered_tool_lists.items():
        head_bucket = grouped.setdefault(head_name, {})
        for spindle in dialog._spindle_profiles.keys():
            spindle_bucket = head_bucket.setdefault(spindle, [])
            for item in ordered_list._assignments_by_spindle.get(spindle, []):
                tool_id = str(item.get("tool_id") or "").strip()
                if not tool_id:
                    continue
                label = ordered_list._tool_label(item)
                spindle_bucket.append((ordered_list, item, label))
    return grouped


def _build_assignment_row(
    dialog: Any,
    ordered_list,
    item: dict,
    label: str,
    spindle: str,
) -> tuple[QWidget, QLineEdit]:
    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 6)
    row_layout.setSpacing(8)

    icon = QIcon()
    ref = ordered_list._tool_ref_for_assignment(item)
    if isinstance(ref, dict):
        icon = ordered_list._tool_icon_for_spindle_resolver(ref.get("tool_type", ""), spindle)

    card = MiniAssignmentCard(
        icon=icon,
        title=label,
        subtitle="",
        badges=[],
        editable=False,
        compact=True,
        parent=row,
    )
    card.setProperty("miniAssignmentCard", True)
    row_layout.addWidget(card, 1)

    pot_input = QLineEdit()
    pot_input.setPlaceholderText(dialog._t("work_editor.tools.pot_placeholder", "Pot #"))
    pot_input.setFixedWidth(96)
    pot_input.setText(item.get("pot") or "")
    row_layout.addWidget(pot_input, 0, Qt.AlignVCenter)

    return row, pot_input


def open_pot_editor_dialog(dialog: Any) -> None:
    """Open/edit pot overrides while preserving in-place assignment references."""
    populate_default_pots(dialog)
    grouped_items = _collect_pot_editor_items(dialog)

    dlg = QDialog(dialog)
    setup_editor_dialog(dlg)
    dlg.setWindowTitle(dialog._t("work_editor.tools.pot_editor_title", "Pot Editor"))
    dlg.setMinimumWidth(860)
    dlg.setMinimumHeight(560)
    dlg_layout = QVBoxLayout(dlg)
    dlg_layout.setContentsMargins(16, 16, 16, 16)
    dlg_layout.setSpacing(10)

    scroll = QScrollArea()
    scroll.setProperty("toolIdsScrollArea", True)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.viewport().setAutoFillBackground(False)
    container = QWidget()
    container.setObjectName("potEditorScrollContent")
    container.setAttribute(Qt.WA_StyledBackground, False)
    content = QVBoxLayout(container)
    content.setContentsMargins(4, 4, 4, 4)
    content.setSpacing(10)

    pot_inputs: list[tuple[dict, QLineEdit]] = []
    for head_name in dialog._head_profiles.keys():
        head_sections = grouped_items.get(head_name, {})
        if not head_sections:
            continue

        head_title = QLabel(dialog._head_label(head_name, head_name))
        head_title.setStyleSheet("font-size: 18px; font-weight: 700; padding-left: 2px;")
        content.addWidget(head_title)

        for spindle in dialog._spindle_profiles.keys():
            spindle_entries = head_sections.get(spindle, [])
            section = create_titled_section(dialog._spindle_label(spindle, spindle))
            section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(8, 8, 8, 8)
            section_layout.setSpacing(0)

            if spindle_entries:
                for ordered_list, item, label in spindle_entries:
                    row_widget, pot_input = _build_assignment_row(
                        dialog,
                        ordered_list,
                        item,
                        label,
                        spindle,
                    )
                    section_layout.addWidget(row_widget)
                    pot_inputs.append((item, pot_input))
            else:
                empty = QLabel(dialog._t("work_editor.tools.none", "No tools"))
                empty.setStyleSheet("color: #6f8090; padding: 6px;")
                section_layout.addWidget(empty)

            content.addWidget(section)

    content.addStretch(1)

    scroll.setWidget(container)
    dlg_layout.addWidget(scroll, 1)

    btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    ok_btn = btn_box.button(QDialogButtonBox.Ok)
    cancel_btn = btn_box.button(QDialogButtonBox.Cancel)
    if isinstance(ok_btn, QPushButton):
        ok_btn.setProperty("panelActionButton", True)
        ok_btn.setProperty("primaryAction", True)
    if isinstance(cancel_btn, QPushButton):
        cancel_btn.setProperty("panelActionButton", True)
        cancel_btn.setProperty("secondaryAction", True)
    btn_box.accepted.connect(dlg.accept)
    btn_box.rejected.connect(dlg.reject)
    dlg_layout.addWidget(btn_box)

    if dlg.exec() != QDialog.Accepted:
        return

    # Apply directly to existing assignment dict objects so every visible
    # ordered list reflects updates without rebuilding assignments.
    for item, inp in pot_inputs:
        item["pot"] = inp.text().strip()
    for ordered_list in dialog._all_tool_list_widgets:
        ordered_list._render_current_spindle()

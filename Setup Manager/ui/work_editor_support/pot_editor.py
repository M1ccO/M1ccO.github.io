from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget
from .tool_actions import populate_default_pots


def _collect_pot_editor_items(dialog: Any) -> list[tuple[dict, str, str, str]]:
    items: list[tuple[dict, str, str, str]] = []
    for head_name, ordered_list in dialog._ordered_tool_lists.items():
        for spindle in dialog._spindle_profiles.keys():
            for item in ordered_list._assignments_by_spindle.get(spindle, []):
                tool_id = str(item.get("tool_id") or "").strip()
                if not tool_id:
                    continue
                label = ordered_list._tool_label(item)
                items.append((item, label, head_name, spindle))
    return items


def open_pot_editor_dialog(dialog: Any) -> None:
    """Open/edit pot overrides while preserving in-place assignment references."""
    populate_default_pots(dialog)
    all_items = _collect_pot_editor_items(dialog)

    dlg = QDialog(dialog)
    dlg.setWindowTitle(dialog._t("work_editor.tools.pot_editor_title", "Pot Editor"))
    dlg.setMinimumWidth(420)
    dlg_layout = QVBoxLayout(dlg)
    dlg_layout.setContentsMargins(16, 16, 16, 16)
    dlg_layout.setSpacing(10)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    container = QWidget()
    form = QFormLayout(container)
    form.setContentsMargins(4, 4, 4, 4)
    form.setSpacing(8)

    pot_inputs: list[tuple[dict, QLineEdit]] = []
    for item, label, head_name, spindle in all_items:
        inp = QLineEdit()
        inp.setPlaceholderText(dialog._t("work_editor.tools.pot_placeholder", "Pot #"))
        inp.setMaximumWidth(100)
        inp.setText(item.get("pot") or "")
        form.addRow(QLabel(f"[{head_name}/{spindle.upper()}]  {label}"), inp)
        pot_inputs.append((item, inp))

    scroll.setWidget(container)
    dlg_layout.addWidget(scroll, 1)

    btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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

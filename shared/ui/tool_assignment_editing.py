from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard

try:
    from shared.ui.helpers.editor_helpers import create_titled_section, setup_editor_dialog
except ModuleNotFoundError:
    from editor_helpers import create_titled_section, setup_editor_dialog


def _translate_noop(_key: str, default: str | None = None, **_kwargs) -> str:
    return default or ""


def edit_tool_assignment_dialog(
    parent,
    *,
    translate: Callable[[str, str | None], str] | None = None,
    library_tool_id: str = "",
    library_description: str = "",
    override_id: str = "",
    override_description: str = "",
    comment_value: str = "",
    pot_value: str = "",
    default_pot: str = "",
) -> dict | None:
    t = translate or _translate_noop
    dlg = QDialog(parent)
    setup_editor_dialog(dlg)
    dlg.setWindowTitle(t("work_editor.tools.edit_row_title", "Edit Tool Row"))
    dlg.setModal(True)
    dlg.resize(420, 0)

    form = QFormLayout(dlg)
    form.setContentsMargins(14, 14, 14, 14)
    form.setSpacing(8)

    id_input = QLineEdit(dlg)
    id_input.setPlaceholderText(str(library_tool_id or "").strip())
    id_input.setText(str(override_id or "").strip())
    form.addRow(t("work_editor.tools.override_id", "T-code"), id_input)

    desc_input = QLineEdit(dlg)
    desc_input.setPlaceholderText(str(library_description or "").strip())
    desc_input.setText(str(override_description or "").strip())
    form.addRow(t("work_editor.tools.override_description", "Description"), desc_input)

    comment_input = QLineEdit(dlg)
    comment_input.setPlaceholderText(t("tool_library.selector.comment_prompt", "Comment"))
    comment_input.setText(str(comment_value or "").strip())
    form.addRow(t("work_editor.tools.comment_title", "Comment"), comment_input)

    pot_input = QLineEdit(dlg)
    pot_input.setPlaceholderText(
        str(default_pot or "").strip() or t("work_editor.tools.pot_placeholder", "e.g. P1")
    )
    pot_input.setText(str(pot_value or "").strip())
    form.addRow(t("work_editor.tools.pot_number", "Pot"), pot_input)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    ok_btn = buttons.button(QDialogButtonBox.Ok)
    cancel_btn = buttons.button(QDialogButtonBox.Cancel)
    if isinstance(ok_btn, QPushButton):
        ok_btn.setProperty("panelActionButton", True)
        ok_btn.setProperty("primaryAction", True)
    if isinstance(cancel_btn, QPushButton):
        cancel_btn.setProperty("panelActionButton", True)
        cancel_btn.setProperty("secondaryAction", True)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    form.addRow(buttons)

    if dlg.exec() != QDialog.Accepted:
        return None

    new_id = id_input.text().strip()
    new_desc = desc_input.text().strip()
    return {
        "override_id": new_id if new_id and new_id != str(library_tool_id or "").strip() else "",
        "override_description": (
            new_desc if new_desc and new_desc != str(library_description or "").strip() else ""
        ),
        "comment": comment_input.text().strip(),
        "pot": pot_input.text().strip(),
    }


def open_tool_pot_editor_dialog(
    parent,
    *,
    sections: list[dict],
    translate: Callable[[str, str | None], str] | None = None,
    title: str | None = None,
) -> bool:
    t = translate or _translate_noop
    dlg = QDialog(parent)
    setup_editor_dialog(dlg)
    dlg.setWindowTitle(title or t("work_editor.tools.pot_editor_title", "Pot Editor"))
    dlg.setMinimumWidth(860)
    dlg.setMinimumHeight(560)

    dlg_layout = QVBoxLayout(dlg)
    dlg_layout.setContentsMargins(16, 16, 16, 16)
    dlg_layout.setSpacing(10)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.viewport().setAutoFillBackground(False)

    container = QWidget()
    content = QVBoxLayout(container)
    content.setContentsMargins(4, 4, 4, 4)
    content.setSpacing(10)

    pot_inputs: list[tuple[dict, QLineEdit]] = []
    for section in sections or []:
        section_groups = list(section.get("groups") or [])
        rows = list(section.get("rows") or [])
        has_content = bool(rows) or any(list(group.get("rows") or []) for group in section_groups)
        if not has_content:
            continue
        if not rows:
            rows = []

        header_text = str(section.get("title") or "").strip()
        if header_text:
            header = QLabel(header_text, container)
            header.setStyleSheet("font-size: 18px; font-weight: 700; padding-left: 2px;")
            content.addWidget(header)

        if rows:
            section_groups = [{"title": "", "rows": rows}]

        for group in section_groups:
            group_title = str(group.get("title") or "").strip()
            group_rows = list(group.get("rows") or [])
            group_box = create_titled_section(group_title or t("work_editor.tools.none", "Tools"), parent=container)
            group_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            group_layout = QVBoxLayout(group_box)
            group_layout.setContentsMargins(8, 8, 8, 8)
            group_layout.setSpacing(0)

            if group_rows:
                for row in group_rows:
                    assignment = row.get("assignment")
                    if not isinstance(assignment, dict):
                        continue
                    row_widget = QWidget(group_box)
                    row_layout = QHBoxLayout(row_widget)
                    row_layout.setContentsMargins(0, 0, 0, 6)
                    row_layout.setSpacing(8)

                    card = MiniAssignmentCard(
                        icon=row.get("icon") if isinstance(row.get("icon"), QIcon) else QIcon(),
                        title=str(row.get("label") or "").strip(),
                        subtitle="",
                        badges=[],
                        editable=False,
                        compact=True,
                        flip_vertical=bool(row.get("flip_vertical")),
                        parent=row_widget,
                    )
                    row_layout.addWidget(card, 1)

                    pot_input = QLineEdit(row_widget)
                    pot_input.setPlaceholderText(
                        str(row.get("placeholder") or "").strip()
                        or t("work_editor.tools.pot_placeholder", "Pot #")
                    )
                    pot_input.setFixedWidth(96)
                    pot_input.setText(str(row.get("pot") or "").strip())
                    row_layout.addWidget(pot_input, 0, Qt.AlignVCenter)

                    group_layout.addWidget(row_widget)
                    pot_inputs.append((assignment, pot_input))
            else:
                empty = QLabel(t("work_editor.tools.none", "No tools"), group_box)
                empty.setStyleSheet("color: #6f8090; padding: 6px;")
                group_layout.addWidget(empty)

            content.addWidget(group_box)

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
        return False

    for assignment, pot_input in pot_inputs:
        assignment["pot"] = pot_input.text().strip()
    return True

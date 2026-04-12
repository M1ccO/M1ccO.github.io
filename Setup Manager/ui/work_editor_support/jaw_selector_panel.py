from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget

from config import ICONS_DIR, TOOL_ICONS_DIR, TOOL_LIBRARY_TOOL_ICONS_DIR

try:
    from shared.ui.helpers.editor_helpers import create_titled_section
except ModuleNotFoundError:
    from editor_helpers import create_titled_section

try:
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
except ModuleNotFoundError:
    _workspace_root = Path(__file__).resolve().parents[3]
    if str(_workspace_root) not in sys.path:
        sys.path.insert(0, str(_workspace_root))
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard


def _noop_translate(_key: str, default: str | None = None, **_kwargs) -> str:
    return default or ""


class WorkEditorJawSelectorPanel(QWidget):
    """Compact single-jaw panel used by the work editor spindles tab."""

    selectionChanged = Signal(str)

    def __init__(
        self,
        title: str,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
        filter_placeholder_key: str = "work_editor.jaw.filter_placeholder",
        filter_placeholder_default: str = "Filter jaws...",
        spindle_side_filter: str | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or _noop_translate
        self._filter_placeholder_key = filter_placeholder_key
        self._filter_placeholder_default = filter_placeholder_default
        self._spindle_side_filter = spindle_side_filter
        self._title = title
        self._all_jaws: list[dict] = []
        self._selected_jaw_id = ""
        self._stop_screws_value = ""
        self._is_stop_screws_mode = False
        self._assignment_card: MiniAssignmentCard | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        selection_group = create_titled_section(title)
        selection_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        selection_layout = QVBoxLayout(selection_group)
        self._selection_layout = selection_layout
        selection_layout.setContentsMargins(8, 10, 8, 8)
        selection_layout.setSpacing(6)

        self.assignment_placeholder = QLabel(self._t("work_editor.jaw.none_selected", "No jaw selected"))
        self.assignment_placeholder.setProperty("detailHint", True)
        self.assignment_placeholder.setStyleSheet("font-style: italic; font-weight: 400;")
        self.assignment_placeholder.setWordWrap(False)
        self.assignment_placeholder.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.assignment_placeholder.setFixedHeight(38)
        selection_layout.addWidget(self.assignment_placeholder)
        layout.addWidget(selection_group, 0)

        self.stop_screws_group = create_titled_section(self._t("setup_page.field.stop_screws", "Stop Screws"))
        self.stop_screws_group.setProperty("jawInputGroup", True)
        self.stop_screws_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        stop_layout = QVBoxLayout(self.stop_screws_group)
        stop_layout.setContentsMargins(10, 8, 10, 8)
        stop_layout.setSpacing(0)

        self.stop_screws_input = QLineEdit()
        self.stop_screws_input.setPlaceholderText(
            self._t("work_editor.jaw.stop_screws_placeholder", "e.g. 10mm")
        )
        self.stop_screws_input.textChanged.connect(self._on_stop_screws_changed)
        stop_layout.addWidget(self.stop_screws_input)
        layout.addWidget(self.stop_screws_group, 0)
        layout.addStretch(1)

        self._refresh_assignment_view()
        self._update_stop_screws_visibility()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _is_spiked_jaw(jaw: dict | None) -> bool:
        if not jaw:
            return False
        jaw_type = (jaw.get("jaw_type") or "").strip().lower()
        if jaw_type:
            return "spiked" in jaw_type
        description = (jaw.get("description") or "").strip().lower()
        return "spiked" in description

    def _selected_jaw(self) -> dict | None:
        if not self._selected_jaw_id:
            return None
        for jaw in self._all_jaws or []:
            jaw_id = str(jaw.get("id") or jaw.get("jaw_id") or "").strip()
            if jaw_id == self._selected_jaw_id:
                return jaw
        return None

    def _jaw_icon(self) -> QIcon:
        # Prefer spindle-specific jaw icons: sub uses jaw_sub, main uses jaw_main.
        # Fall back to jaw/hard_jaw icons if chuck images are missing.
        side = (self._spindle_side_filter or "").strip().lower()
        is_sub = side in {"sub", "sub spindle", "subspindle", "counter spindle"}

        lookup = []
        if is_sub:
            lookup += [
                Path(TOOL_ICONS_DIR) / "jaw_sub.png",
                Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_sub.png",
                Path(ICONS_DIR) / "tools" / "jaw_sub.png",
                Path(TOOL_ICONS_DIR) / "jaw_main.png",
                Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_main.png",
                Path(ICONS_DIR) / "tools" / "jaw_main.png",
            ]
        else:
            lookup += [
                Path(TOOL_ICONS_DIR) / "jaw_main.png",
                Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_main.png",
                Path(ICONS_DIR) / "tools" / "jaw_main.png",
                Path(TOOL_ICONS_DIR) / "jaw_sub.png",
                Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_sub.png",
                Path(ICONS_DIR) / "tools" / "jaw_sub.png",
            ]

        lookup += [
            Path(TOOL_ICONS_DIR) / "jaw_icon.png",
            Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "jaw_icon.png",
            Path(TOOL_ICONS_DIR) / "hard_jaw.png",
            Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / "hard_jaw.png",
            Path(ICONS_DIR) / "tools" / "hard_jaw.png",
        ]

        for candidate in lookup:
            if candidate.exists():
                icon = QIcon(str(candidate))
                if not icon.isNull():
                    return icon
        return QIcon()

    def _refresh_assignment_view(self):
        jaw = self._selected_jaw()
        has_selection = bool(self._selected_jaw_id)

        if not has_selection:
            self.assignment_placeholder.setText(self._t("work_editor.jaw.none_selected", "No jaw selected"))
            self.assignment_placeholder.setVisible(True)
            if self._assignment_card is not None:
                self._assignment_card.setVisible(False)
            return

        jaw_id = self._selected_jaw_id
        description = (jaw.get("description") or "").strip() if isinstance(jaw, dict) else ""
        if not description and isinstance(jaw, dict):
            description = str(jaw.get("jaw_type") or "").strip()
        label = f"{jaw_id}  -  {description}" if description else jaw_id
        if self._assignment_card is None:
            icon = self._jaw_icon()
            self._assignment_card = MiniAssignmentCard(
                icon=icon,
                title=label,
                subtitle="",
                badges=[],
                editable=False,
                compact=True,
                parent=self,
            )
            self._assignment_card.subtitle_label.setVisible(False)
            self._assignment_card.setMaximumWidth(420)
            self._assignment_card.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            if not icon.isNull():
                self._assignment_card.icon_label.setPixmap(icon.pixmap(QSize(32, 32)))
            self._selection_layout.insertWidget(0, self._assignment_card)
        else:
            self._assignment_card.title_label.setText(label)
            icon = self._jaw_icon()
            if not icon.isNull():
                self._assignment_card.icon_label.setPixmap(icon.pixmap(QSize(32, 32)))
            self._assignment_card.setMaximumWidth(420)
            self._assignment_card.setVisible(True)
        self._assignment_card.set_selected(False)
        self.assignment_placeholder.setVisible(False)

    def _update_stop_screws_visibility(self):
        stop_screws_mode = self._is_spiked_jaw(self._selected_jaw())
        self._is_stop_screws_mode = stop_screws_mode
        self.stop_screws_group.setVisible(stop_screws_mode)
        if stop_screws_mode:
            self.stop_screws_input.blockSignals(True)
            self.stop_screws_input.setText(self._stop_screws_value)
            self.stop_screws_input.blockSignals(False)

    def populate(self, jaws: list):
        self._all_jaws = [dict(item) for item in (jaws or []) if isinstance(item, dict)]
        self._refresh_assignment_view()
        self._update_stop_screws_visibility()

    def _on_stop_screws_changed(self, text: str):
        self._stop_screws_value = (text or "").strip()

    def get_value(self) -> str:
        return self._selected_jaw_id

    def set_value(self, jaw_id: str):
        self._selected_jaw_id = (jaw_id or "").strip()
        self._refresh_assignment_view()
        self._update_stop_screws_visibility()
        self.selectionChanged.emit(self.get_value())

    def set_stop_screws(self, value: str):
        self._stop_screws_value = (value or "").strip()
        if self._is_stop_screws_mode:
            self.stop_screws_input.blockSignals(True)
            self.stop_screws_input.setText(self._stop_screws_value)
            self.stop_screws_input.blockSignals(False)

    def get_stop_screws(self) -> str:
        if not self._is_spiked_jaw(self._selected_jaw()):
            return ""
        return self._stop_screws_value

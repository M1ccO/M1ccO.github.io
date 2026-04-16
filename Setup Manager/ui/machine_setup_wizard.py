"""Machine Setup Wizard — shown when a fresh database has no profile bound yet.

The wizard guides the user through:
  1. Machine type (Lathe only for now; Machining Center is future-reserved)
  2. Spindle count (1 or 2)
  3. Head count (1, 2, or 3)
  4. Per-head type (Turret / Milling) and capability toggles (B-axis, rotating tools)
  5. Summary — shows the matching preset name and confirms

Design constraints:
- No direct cross-app imports.
- The dialog returns a profile key string; the caller (main.py) writes it to
  both the database (WorkService) and shared_ui_preferences.json
  (UiPreferencesService).
- All 5 presets are hard-coded; the wizard validates that the chosen
  combination maps to one of them, falling back to the closest match.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from machine_profiles import (
    DEFAULT_PROFILE_KEY,
    LATHE_1SP_1H,
    LATHE_1SP_1MILL,
    LATHE_2SP_1MILL,
    LATHE_2SP_3H,
    NTX_MACHINE_PROFILE,
    PROFILE_DISPLAY_ORDER,
    PROFILE_REGISTRY,
    load_profile,
)
from shared.ui.helpers.editor_helpers import create_titled_section
from ui.widgets.common import apply_tool_library_combo_style, repolish_widget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(key: str, default: str | None = None, **_kw) -> str:
    return default or ""


def _card(contents: QWidget | QLayout | None = None) -> QFrame:  # type: ignore[name-defined]
    frame = QFrame()
    frame.setProperty("card", True)
    return frame


# ---------------------------------------------------------------------------
# Wizard state
# ---------------------------------------------------------------------------

class _WizardState:
    """Pure-Python state bag — no Qt dependency."""
    machine_type: str = "lathe"        # "lathe" | "machining_center"
    spindle_count: int = 2             # 1 | 2
    head_count: int = 2                # 1 | 2 | 3
    # Per-head settings (list indexed 0 = HEAD1, 1 = HEAD2, 2 = HEAD3)
    head_types: list[str]              # "turret" | "milling"
    head_rotating: list[bool]          # allow rotating tools
    head_b_axis: list[bool]            # allow b_axis_angle

    # Machining center state (only meaningful when machine_type == machining_center)
    mc_axis_count: int = 3             # 3 | 4 | 5
    mc_fourth_axis_letter: str = "C"
    mc_fifth_axis_letter: str = "B"
    mc_has_turning_option: bool = False

    def __init__(self) -> None:
        self.machine_type = "lathe"
        self.spindle_count = 2
        self.head_count = 2
        self.head_types = ["turret", "turret", "turret"]
        self.head_rotating = [False, False, False]
        self.head_b_axis = [False, False, False]
        self.mc_axis_count = 3
        self.mc_fourth_axis_letter = "C"
        self.mc_fifth_axis_letter = "B"
        self.mc_has_turning_option = False

    def resolve_profile_key(self) -> str:
        """Map the current wizard state to the closest matching preset key.

        Resolution priority:
        1. Exact structural match (spindle_count + head_count + head_types)
        2. Closest partial match
        3. Default fallback (ntx_2sp_2h)
        """
        if self.machine_type == "machining_center":
            if self.mc_axis_count == 5:
                return "machining_center_5ax"
            if self.mc_axis_count == 4:
                return "machining_center_4ax"
            return "machining_center_3ax"

        sc = self.spindle_count
        hc = self.head_count
        # Treat explicit milling head selection OR powered capabilities
        # as intent for a milling-capable profile.
        has_mill = any(t == "milling" for t in self.head_types[:hc])
        has_powered_capability = any(
            bool(self.head_b_axis[i]) or bool(self.head_rotating[i])
            for i in range(hc)
        )
        wants_milling_capability = has_mill or has_powered_capability

        if sc == 2 and hc == 2 and not wants_milling_capability:
            return "ntx_2sp_2h"
        if sc == 2 and hc == 2 and wants_milling_capability:
            return "lathe_2sp_2h_mixed"
        if sc == 2 and hc == 1 and wants_milling_capability:
            return "lathe_2sp_1mill"
        if sc == 2 and hc == 3 and not has_mill:
            return "lathe_2sp_3h"
        if sc == 1 and hc == 1 and not has_mill:
            return "lathe_1sp_1h"
        if sc == 1 and hc == 1 and wants_milling_capability:
            return "lathe_1sp_1mill"

        # Partial fallback: match on spindle count
        if sc == 1:
            if wants_milling_capability:
                return "lathe_1sp_1mill"
            return "lathe_1sp_1h"
        if wants_milling_capability:
            return "lathe_2sp_1mill"
        return DEFAULT_PROFILE_KEY


# ---------------------------------------------------------------------------
# Individual pages
# ---------------------------------------------------------------------------

class _Page(QWidget):
    """Base wizard page."""
    def __init__(self, state: _WizardState, translate: Callable, parent=None):
        super().__init__(parent)
        self._state = state
        self._t = translate

    def on_enter(self) -> None:
        """Called when the wizard navigates to this page."""

    def on_leave(self) -> None:
        """Called when the wizard navigates away; save state."""


class _MachineTypePage(_Page):
    def __init__(self, state, translate, parent=None):
        super().__init__(state, translate, parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel(translate("wizard.step1.title", "Step 1 — Machine Type"))
        title.setProperty("sectionTitle", True)
        layout.addWidget(title)

        desc = QLabel(translate(
            "wizard.step1.description",
            "Select the machine family. Lathes use spindles and jaws; "
            "machining centers use fixtures and operation-keyed zero points.",
        ))
        desc.setWordWrap(True)
        desc.setProperty("detailHint", True)
        layout.addWidget(desc)

        self._lathe_radio = QRadioButton(translate("wizard.machine_type.lathe", "Lathe (turning center)"))
        self._mc_radio = QRadioButton(translate("wizard.machine_type.machining_center", "Machining Center"))
        self._lathe_radio.setChecked(True)

        group_box = QGroupBox()
        gb_layout = QVBoxLayout(group_box)
        gb_layout.addWidget(self._lathe_radio)
        gb_layout.addWidget(self._mc_radio)
        layout.addWidget(group_box)
        layout.addStretch(1)

    def on_leave(self):
        self._state.machine_type = "lathe" if self._lathe_radio.isChecked() else "machining_center"


class _SpindleCountPage(_Page):
    def __init__(self, state, translate, parent=None):
        super().__init__(state, translate, parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel(translate("wizard.step2.title", "Step 2 — Spindle Count"))
        title.setProperty("sectionTitle", True)
        layout.addWidget(title)

        desc = QLabel(translate(
            "wizard.step2.description",
            "Single-spindle machines use OP10 / OP20 terminology instead of\n"
            "Main spindle / Sub spindle.  Dual-spindle machines keep the\n"
            "Main / Sub semantics you may already be familiar with.",
        ))
        desc.setWordWrap(True)
        desc.setProperty("detailHint", True)
        layout.addWidget(desc)

        self._sp1_radio = QRadioButton(translate("wizard.spindle.one", "1 Spindle (OP10 / OP20 terminology)"))
        self._sp2_radio = QRadioButton(translate("wizard.spindle.two", "2 Spindles (Main / Sub spindle)"))
        self._sp2_radio.setChecked(True)

        group_box = QGroupBox()
        gb_layout = QVBoxLayout(group_box)
        gb_layout.addWidget(self._sp1_radio)
        gb_layout.addWidget(self._sp2_radio)
        layout.addWidget(group_box)
        layout.addStretch(1)

    def on_enter(self):
        if self._state.machine_type != "lathe":
            self._sp2_radio.setChecked(True)
            self._sp1_radio.setEnabled(False)
            self._sp2_radio.setEnabled(False)
        else:
            self._sp1_radio.setEnabled(True)
            self._sp2_radio.setEnabled(True)

    def on_leave(self):
        self._state.spindle_count = 1 if self._sp1_radio.isChecked() else 2


class _HeadCountPage(_Page):
    def __init__(self, state, translate, parent=None):
        super().__init__(state, translate, parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel(translate("wizard.step3.title", "Step 3 — Head Count"))
        title.setProperty("sectionTitle", True)
        layout.addWidget(title)

        self._desc = QLabel()
        self._desc.setWordWrap(True)
        self._desc.setProperty("detailHint", True)
        layout.addWidget(self._desc)

        self._h1_radio = QRadioButton(translate("wizard.head.one", "1 Head"))
        self._h2_radio = QRadioButton(translate("wizard.head.two", "2 Heads"))
        self._h3_radio = QRadioButton(translate("wizard.head.three", "3 Heads"))
        self._h2_radio.setChecked(True)

        group_box = QGroupBox()
        gb_layout = QVBoxLayout(group_box)
        gb_layout.addWidget(self._h1_radio)
        gb_layout.addWidget(self._h2_radio)
        gb_layout.addWidget(self._h3_radio)
        layout.addWidget(group_box)
        layout.addStretch(1)

    def on_enter(self):
        if self._state.spindle_count == 1:
            self._desc.setText(self._t(
                "wizard.step3.desc_single_spindle",
                "Single-spindle machines typically use one head.",
            ))
            self._h1_radio.setChecked(True)
            self._h2_radio.setEnabled(False)
            self._h3_radio.setEnabled(False)
        else:
            self._desc.setText(self._t(
                "wizard.step3.desc_dual_spindle",
                "Choose how many cutting heads (turret carriers or milling heads) your machine has.",
            ))
            self._h2_radio.setEnabled(True)
            self._h3_radio.setEnabled(True)

    def on_leave(self):
        if self._h1_radio.isChecked():
            self._state.head_count = 1
        elif self._h3_radio.isChecked():
            self._state.head_count = 3
        else:
            self._state.head_count = 2


class _HeadConfigPage(_Page):
    """Per-head capability toggles (type + b-axis + rotating tools)."""

    def __init__(self, state, translate, parent=None):
        super().__init__(state, translate, parent)
        self._head_widgets: list[dict] = []   # [{type_combo, baxis_combo, rotating_combo}, ...]

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel(translate("wizard.step4.title", "Step 4 — Head Capabilities"))
        title.setProperty("sectionTitle", True)
        layout.addWidget(title)

        desc = QLabel(translate(
            "wizard.step4.description",
            "Configure each head's type and optional capabilities.\n"
            "Turret = traditional turning/grooving carrier.\n"
            "Milling = powered head that can run rotating tools.",
        ))
        desc.setWordWrap(True)
        desc.setProperty("detailHint", True)
        layout.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        self._heads_container = QWidget()
        self._heads_container.setStyleSheet("background: transparent;")
        self._heads_layout = QVBoxLayout(self._heads_container)
        self._heads_layout.setSpacing(10)
        scroll.setWidget(self._heads_container)
        layout.addWidget(scroll, 1)

    def on_enter(self):
        # Rebuild widgets to match current head count
        # Remove old widgets
        while self._heads_layout.count():
            item = self._heads_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._head_widgets.clear()

        for i in range(self._state.head_count):
            head_key = f"HEAD{i + 1}"
            group = create_titled_section(f"{self._t('wizard.head_label', 'Head')} {i + 1} ({head_key})")
            form_layout = QVBoxLayout(group)
            form_layout.setSpacing(6)

            # Head type row
            type_row = QHBoxLayout()
            type_label = QLabel(self._t("wizard.head.type", "Head type:"))
            type_label.setMinimumWidth(130)
            type_combo = QComboBox()
            type_combo.addItem(self._t("wizard.head.type.turret", "Turret (turning/grooving)"), "turret")
            type_combo.addItem(self._t("wizard.head.type.milling", "Milling (powered tools)"), "milling")
            apply_tool_library_combo_style(type_combo)
            type_combo.setProperty("hovered", False)
            repolish_widget(type_combo)
            # Pre-select from state
            if i < len(self._state.head_types) and self._state.head_types[i] == "milling":
                type_combo.setCurrentIndex(1)
            type_row.addWidget(type_label)
            type_row.addWidget(type_combo, 1)
            form_layout.addLayout(type_row)

            # B-axis row
            baxis_row = QHBoxLayout()
            baxis_label = QLabel(self._t("wizard.head.b_axis", "B-axis angle:"))
            baxis_label.setMinimumWidth(130)
            baxis_combo = QComboBox()
            baxis_combo.addItem(self._t("wizard.head.b_axis.disabled", "Disabled"), False)
            baxis_combo.addItem(self._t("wizard.head.b_axis.enabled", "Enabled"), True)
            apply_tool_library_combo_style(baxis_combo)
            baxis_combo.setProperty("hovered", False)
            repolish_widget(baxis_combo)
            if i < len(self._state.head_b_axis) and self._state.head_b_axis[i]:
                baxis_combo.setCurrentIndex(1)
            baxis_row.addWidget(baxis_label)
            baxis_row.addWidget(baxis_combo, 1)
            form_layout.addLayout(baxis_row)

            # Rotating tools row (only meaningful for turret)
            rotating_row = QHBoxLayout()
            rotating_label = QLabel(self._t("wizard.head.rotating_tools", "Rotating tools:"))
            rotating_label.setMinimumWidth(130)
            rotating_combo = QComboBox()
            rotating_combo.addItem(self._t("wizard.head.rotating_tools.disabled", "Not allowed (turret only)"), False)
            rotating_combo.addItem(self._t("wizard.head.rotating_tools.enabled", "Allowed"), True)
            apply_tool_library_combo_style(rotating_combo)
            rotating_combo.setProperty("hovered", False)
            repolish_widget(rotating_combo)
            if i < len(self._state.head_rotating) and self._state.head_rotating[i]:
                rotating_combo.setCurrentIndex(1)
            rotating_row.addWidget(rotating_label)
            rotating_row.addWidget(rotating_combo, 1)
            form_layout.addLayout(rotating_row)

            self._heads_layout.addWidget(group)
            self._head_widgets.append({
                "type_combo": type_combo,
                "baxis_combo": baxis_combo,
                "rotating_combo": rotating_combo,
            })

        self._heads_layout.addStretch(1)

    def on_leave(self):
        for i, widgets in enumerate(self._head_widgets):
            if i >= 3:
                break
            self._state.head_types[i] = widgets["type_combo"].currentData() or "turret"
            self._state.head_b_axis[i] = bool(widgets["baxis_combo"].currentData())
            self._state.head_rotating[i] = bool(widgets["rotating_combo"].currentData())


class _MachiningCenterConfigPage(_Page):
    """Machining center configuration — axis count, axis letters, turning option."""

    def __init__(self, state, translate, parent=None):
        super().__init__(state, translate, parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel(translate("wizard.mc.title", "Machining Center Configuration"))
        title.setProperty("sectionTitle", True)
        layout.addWidget(title)

        desc = QLabel(translate(
            "wizard.mc.description",
            "Configure the number of axes and optional capabilities.\n"
            "Axis-letter defaults follow the common C (rotary) and B (tilt) convention.",
        ))
        desc.setWordWrap(True)
        desc.setProperty("detailHint", True)
        layout.addWidget(desc)

        # ---- Axis count ----
        axis_box = QGroupBox(translate("wizard.mc.axis_count", "Axis count"))
        axis_layout = QVBoxLayout(axis_box)
        self._ax3_radio = QRadioButton(translate("wizard.mc.ax3", "3-Axis (X / Y / Z)"))
        self._ax4_radio = QRadioButton(translate("wizard.mc.ax4", "4-Axis (adds one rotary axis)"))
        self._ax5_radio = QRadioButton(translate("wizard.mc.ax5", "5-Axis (adds two rotary axes)"))
        self._ax3_radio.setChecked(True)
        axis_layout.addWidget(self._ax3_radio)
        axis_layout.addWidget(self._ax4_radio)
        axis_layout.addWidget(self._ax5_radio)
        layout.addWidget(axis_box)

        # ---- Axis letters ----
        self._letters_box = QGroupBox(translate("wizard.mc.axis_letters", "Axis letters"))
        letters_layout = QVBoxLayout(self._letters_box)

        fourth_row = QHBoxLayout()
        self._fourth_label = QLabel(translate("wizard.mc.fourth", "Fourth axis letter:"))
        self._fourth_label.setMinimumWidth(150)
        self._fourth_edit = QLineEdit("C")
        self._fourth_edit.setMaxLength(1)
        self._fourth_edit.setFixedWidth(60)
        fourth_row.addWidget(self._fourth_label)
        fourth_row.addWidget(self._fourth_edit)
        fourth_row.addStretch(1)
        letters_layout.addLayout(fourth_row)

        fifth_row = QHBoxLayout()
        self._fifth_label = QLabel(translate("wizard.mc.fifth", "Fifth axis letter:"))
        self._fifth_label.setMinimumWidth(150)
        self._fifth_edit = QLineEdit("B")
        self._fifth_edit.setMaxLength(1)
        self._fifth_edit.setFixedWidth(60)
        fifth_row.addWidget(self._fifth_label)
        fifth_row.addWidget(self._fifth_edit)
        fifth_row.addStretch(1)
        letters_layout.addLayout(fifth_row)
        layout.addWidget(self._letters_box)

        # ---- Turning option ----
        self._turning_check = QCheckBox(translate(
            "wizard.mc.turning_option",
            "Enable turning option (allows lathe tool types in Tool Library)",
        ))
        layout.addWidget(self._turning_check)

        layout.addStretch(1)

        # Wire radio buttons to update axis-letter visibility
        self._ax3_radio.toggled.connect(self._update_letter_visibility)
        self._ax4_radio.toggled.connect(self._update_letter_visibility)
        self._ax5_radio.toggled.connect(self._update_letter_visibility)

    def _update_letter_visibility(self) -> None:
        ax4 = self._ax4_radio.isChecked()
        ax5 = self._ax5_radio.isChecked()
        self._fourth_label.setVisible(ax4 or ax5)
        self._fourth_edit.setVisible(ax4 or ax5)
        self._fifth_label.setVisible(ax5)
        self._fifth_edit.setVisible(ax5)
        self._letters_box.setVisible(ax4 or ax5)

    def on_enter(self):
        if self._state.mc_axis_count == 5:
            self._ax5_radio.setChecked(True)
        elif self._state.mc_axis_count == 4:
            self._ax4_radio.setChecked(True)
        else:
            self._ax3_radio.setChecked(True)
        self._fourth_edit.setText(self._state.mc_fourth_axis_letter or "C")
        self._fifth_edit.setText(self._state.mc_fifth_axis_letter or "B")
        self._turning_check.setChecked(bool(self._state.mc_has_turning_option))
        self._update_letter_visibility()

    def on_leave(self):
        if self._ax5_radio.isChecked():
            self._state.mc_axis_count = 5
        elif self._ax4_radio.isChecked():
            self._state.mc_axis_count = 4
        else:
            self._state.mc_axis_count = 3
        fourth = self._fourth_edit.text().strip().upper() or "C"
        fifth = self._fifth_edit.text().strip().upper() or "B"
        self._state.mc_fourth_axis_letter = fourth
        self._state.mc_fifth_axis_letter = fifth
        self._state.mc_has_turning_option = self._turning_check.isChecked()


class _SummaryPage(_Page):
    def __init__(self, state, translate, parent=None):
        super().__init__(state, translate, parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel(translate("wizard.step5.title", "Step 5 — Confirm"))
        title.setProperty("sectionTitle", True)
        layout.addWidget(title)

        self._body = QLabel()
        self._body.setWordWrap(True)
        layout.addWidget(self._body)

        layout.addStretch(1)

    def on_enter(self):
        key = self._state.resolve_profile_key()
        profile = load_profile(key)

        if self._state.machine_type == "machining_center":
            axis_desc = f"{self._state.mc_axis_count}-Axis"
            letters = []
            if self._state.mc_axis_count >= 4:
                letters.append(f"4th = {self._state.mc_fourth_axis_letter}")
            if self._state.mc_axis_count == 5:
                letters.append(f"5th = {self._state.mc_fifth_axis_letter}")
            letters_desc = ", ".join(letters) if letters else "—"
            turning_desc = (
                "enabled" if self._state.mc_has_turning_option else "disabled"
            )
            text = (
                f"<b>{self._t('wizard.summary.profile', 'Selected profile')}:</b> "
                f"{profile.name}<br><br>"
                f"<b>{self._t('wizard.summary.axis_count', 'Axis count')}:</b> {axis_desc}<br>"
                f"<b>{self._t('wizard.summary.axis_letters', 'Rotary axis letters')}:</b> {letters_desc}<br>"
                f"<b>{self._t('wizard.summary.turning_option', 'Turning option')}:</b> {turning_desc}<br><br>"
                f"<i>{self._t('wizard.summary.note', 'You can reconfigure this later via Preferences → Configure Machine.')}</i>"
            )
            self._body.setText(text)
            return

        spindle_desc = (
            "1 spindle (OP10/OP20)"
            if self._state.spindle_count == 1
            else "2 spindles (Main / Sub)"
        )
        head_desc = f"{self._state.head_count} head(s)"
        head_types = ", ".join(
            f"HEAD{i+1}: {self._state.head_types[i]}"
            for i in range(self._state.head_count)
        )
        b_axes = ", ".join(
            f"HEAD{i+1}: {'enabled' if self._state.head_b_axis[i] else 'disabled'}"
            for i in range(self._state.head_count)
        )
        text = (
            f"<b>{self._t('wizard.summary.profile', 'Selected profile')}:</b> "
            f"{profile.name}<br><br>"
            f"<b>{self._t('wizard.summary.spindles', 'Spindles')}:</b> {spindle_desc}<br>"
            f"<b>{self._t('wizard.summary.heads', 'Heads')}:</b> {head_desc} — {head_types}<br>"
            f"<b>{self._t('wizard.summary.b_axis', 'B-axis')}:</b> {b_axes}<br><br>"
            f"<i>{self._t('wizard.summary.note', 'You can reconfigure this later via Preferences → Configure Machine.')}</i>"
        )
        self._body.setText(text)


# ---------------------------------------------------------------------------
# Main wizard dialog
# ---------------------------------------------------------------------------

class MachineSetupWizard(QDialog):
    """Step-through wizard for binding a machine profile to a database.

    Usage::

        wizard = MachineSetupWizard(translate=my_translate_fn)
        if wizard.exec() == QDialog.Accepted:
            key = wizard.selected_profile_key()
    """

    def __init__(self, translate: Callable | None = None, parent=None):
        super().__init__(parent)
        self._t = translate or _noop
        self._state = _WizardState()
        self._current_page_index = 0

        self.setWindowTitle(self._t("wizard.title", "Machine Setup"))
        self.setModal(True)
        self.resize(520, 480)
        self.setMinimumSize(420, 380)
        self.setProperty("workEditorDialog", True)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        # Step indicator
        self._step_label = QLabel()
        self._step_label.setProperty("sectionTitle", True)
        root.addWidget(self._step_label)

        # Page stack.  Index 0 is always Machine Type; 1 is MC config (only
        # reachable when MC is chosen); 2-4 are lathe pages; 5 is Summary.
        self._stack = QStackedWidget()
        self._pages: list[_Page] = [
            _MachineTypePage(self._state, self._t),           # 0
            _MachiningCenterConfigPage(self._state, self._t), # 1 (MC only)
            _SpindleCountPage(self._state, self._t),          # 2 (lathe only)
            _HeadCountPage(self._state, self._t),             # 3 (lathe only)
            _HeadConfigPage(self._state, self._t),            # 4 (lathe only)
            _SummaryPage(self._state, self._t),               # 5
        ]
        self._summary_index = 5
        self._mc_config_index = 1
        self._lathe_indices = (2, 3, 4)
        for page in self._pages:
            self._stack.addWidget(page)
        root.addWidget(self._stack, 1)

        # Navigation buttons
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 4, 0, 0)
        nav_row.setSpacing(8)

        self._back_btn = QPushButton(self._t("wizard.back", "Back"))
        self._back_btn.setProperty("panelActionButton", True)
        self._back_btn.clicked.connect(self._go_back)

        self._next_btn = QPushButton(self._t("wizard.next", "Next"))
        self._next_btn.setProperty("panelActionButton", True)
        self._next_btn.setProperty("primaryAction", True)
        self._next_btn.clicked.connect(self._go_next)

        self._cancel_btn = QPushButton(self._t("wizard.cancel", "Cancel"))
        self._cancel_btn.setProperty("panelActionButton", True)
        self._cancel_btn.setProperty("secondaryAction", True)
        self._cancel_btn.clicked.connect(self.reject)

        nav_row.addWidget(self._cancel_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self._back_btn)
        nav_row.addWidget(self._next_btn)
        root.addLayout(nav_row)

        self._go_to_page(0)

    # ------------------------------------------------------------------

    def _page_is_applicable(self, index: int) -> bool:
        """Return True when a page should appear given the current machine type."""
        if index == 0 or index == self._summary_index:
            return True
        is_mc = self._state.machine_type == "machining_center"
        if index == self._mc_config_index:
            return is_mc
        if index in self._lathe_indices:
            return not is_mc
        return True

    def _applicable_indices(self) -> list[int]:
        return [i for i in range(len(self._pages)) if self._page_is_applicable(i)]

    def _go_to_page(self, index: int) -> None:
        if 0 <= self._current_page_index < len(self._pages):
            self._pages[self._current_page_index].on_leave()

        self._current_page_index = max(0, min(index, len(self._pages) - 1))
        page = self._pages[self._current_page_index]
        page.on_enter()
        self._stack.setCurrentWidget(page)

        applicable = self._applicable_indices()
        total = len(applicable)
        current = applicable.index(self._current_page_index) + 1 if self._current_page_index in applicable else 1
        self._step_label.setText(
            self._t("wizard.step_indicator", f"Step {current} of {total}")
            .replace("{current}", str(current))
            .replace("{total}", str(total))
            if "{current}" in self._t("wizard.step_indicator", "")
            else f"{self._t('wizard.step', 'Step')} {current} / {total}"
        )

        self._back_btn.setEnabled(current > 1)
        is_last = self._current_page_index == self._summary_index
        self._next_btn.setText(
            self._t("wizard.finish", "Finish") if is_last else self._t("wizard.next", "Next")
        )

    def _next_applicable(self, from_index: int, direction: int) -> int:
        """Return the next applicable page index in the given direction."""
        i = from_index + direction
        while 0 <= i < len(self._pages):
            if self._page_is_applicable(i):
                return i
            i += direction
        return from_index

    def _go_back(self) -> None:
        target = self._next_applicable(self._current_page_index, -1)
        if target != self._current_page_index:
            self._go_to_page(target)

    def _go_next(self) -> None:
        if self._current_page_index == self._summary_index:
            self.accept()
            return
        # Commit current page state before computing the next applicable page.
        # This is required for page 0 where machine_type controls branching
        # between lathe pages and the machining-center axis page.
        self._pages[self._current_page_index].on_leave()
        target = self._next_applicable(self._current_page_index, +1)
        if target != self._current_page_index:
            self._go_to_page(target)

    def selected_profile_key(self) -> str:
        """Return the profile key selected / derived by the wizard."""
        return self._state.resolve_profile_key()

    def selected_mc_overrides(self) -> dict:
        """Return the machining-center specific overrides chosen in the wizard.

        Returns an empty dict for lathe profiles so callers can blindly merge
        the result into preferences.
        """
        if self._state.machine_type != "machining_center":
            return {}
        return {
            "mc_axis_count": int(self._state.mc_axis_count),
            "mc_fourth_axis_letter": str(self._state.mc_fourth_axis_letter or "C"),
            "mc_fifth_axis_letter": str(self._state.mc_fifth_axis_letter or "B"),
            "mc_has_turning_option": bool(self._state.mc_has_turning_option),
        }

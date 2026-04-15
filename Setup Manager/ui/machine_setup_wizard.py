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
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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

    def __init__(self) -> None:
        self.machine_type = "lathe"
        self.spindle_count = 2
        self.head_count = 2
        self.head_types = ["turret", "turret", "turret"]
        self.head_rotating = [False, False, False]
        self.head_b_axis = [False, False, False]

    def resolve_profile_key(self) -> str:
        """Map the current wizard state to the closest matching preset key.

        Resolution priority:
        1. Exact structural match (spindle_count + head_count + head_types)
        2. Closest partial match
        3. Default fallback (ntx_2sp_2h)
        """
        sc = self.spindle_count
        hc = self.head_count
        # Check head types for 'milling' presence
        has_mill = any(t == "milling" for t in self.head_types[:hc])

        if sc == 2 and hc == 2 and not has_mill:
            return "ntx_2sp_2h"
        if sc == 2 and hc == 1 and has_mill:
            return "lathe_2sp_1mill"
        if sc == 2 and hc == 3 and not has_mill:
            return "lathe_2sp_3h"
        if sc == 1 and hc == 1 and not has_mill:
            return "lathe_1sp_1h"
        if sc == 1 and hc == 1 and has_mill:
            return "lathe_1sp_1mill"

        # Partial fallback: match on spindle count
        if sc == 1:
            return "lathe_1sp_1h"
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
            "Select the machine family. Machining Center support is reserved for a future release.",
        ))
        desc.setWordWrap(True)
        desc.setProperty("detailHint", True)
        layout.addWidget(desc)

        self._lathe_radio = QRadioButton(translate("wizard.machine_type.lathe", "Lathe (turning center)"))
        self._mc_radio = QRadioButton(translate("wizard.machine_type.machining_center", "Machining Center (future)"))
        self._mc_radio.setEnabled(False)
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
        self._heads_container = QWidget()
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
            group = QGroupBox(f"{self._t('wizard.head_label', 'Head')} {i + 1} ({head_key})")
            form_layout = QVBoxLayout(group)
            form_layout.setSpacing(6)

            # Head type row
            type_row = QHBoxLayout()
            type_label = QLabel(self._t("wizard.head.type", "Head type:"))
            type_label.setMinimumWidth(130)
            type_combo = QComboBox()
            type_combo.addItem(self._t("wizard.head.type.turret", "Turret (turning/grooving)"), "turret")
            type_combo.addItem(self._t("wizard.head.type.milling", "Milling (powered tools)"), "milling")
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

        # Page stack
        self._stack = QStackedWidget()
        self._pages: list[_Page] = [
            _MachineTypePage(self._state, self._t),
            _SpindleCountPage(self._state, self._t),
            _HeadCountPage(self._state, self._t),
            _HeadConfigPage(self._state, self._t),
            _SummaryPage(self._state, self._t),
        ]
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

    def _go_to_page(self, index: int) -> None:
        if 0 <= self._current_page_index < len(self._pages):
            self._pages[self._current_page_index].on_leave()

        self._current_page_index = max(0, min(index, len(self._pages) - 1))
        page = self._pages[self._current_page_index]
        page.on_enter()
        self._stack.setCurrentWidget(page)

        total = len(self._pages)
        current = self._current_page_index + 1
        self._step_label.setText(
            self._t("wizard.step_indicator", f"Step {current} of {total}")
            .replace("{current}", str(current))
            .replace("{total}", str(total))
            if "{current}" in self._t("wizard.step_indicator", "")
            else f"{self._t('wizard.step', 'Step')} {current} / {total}"
        )

        self._back_btn.setEnabled(self._current_page_index > 0)
        is_last = self._current_page_index == len(self._pages) - 1
        self._next_btn.setText(
            self._t("wizard.finish", "Finish") if is_last else self._t("wizard.next", "Next")
        )

    def _go_back(self) -> None:
        self._go_to_page(self._current_page_index - 1)

    def _go_next(self) -> None:
        if self._current_page_index >= len(self._pages) - 1:
            self.accept()
        else:
            self._go_to_page(self._current_page_index + 1)

    def selected_profile_key(self) -> str:
        """Return the profile key selected / derived by the wizard."""
        return self._state.resolve_profile_key()

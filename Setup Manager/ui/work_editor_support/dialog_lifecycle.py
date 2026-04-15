"""Dialog lifecycle setup helpers for WorkEditorDialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def setup_tabs(dialog) -> None:
    """Create and register all dialog tabs."""
    dialog.tabs = QTabWidget(dialog)

    dialog.general_tab = QWidget()
    dialog.zeros_tab = QWidget()
    dialog.tools_tab = QWidget()
    dialog.notes_tab = QWidget()

    dialog.tabs.addTab(dialog.general_tab, dialog._t("work_editor.tab.general", "General"))
    dialog.tabs.addTab(dialog.zeros_tab, dialog._t("work_editor.tab.zero_points", "Zero Points"))
    dialog.tabs.addTab(dialog.tools_tab, dialog._t("work_editor.tab.tool_ids", "Tool IDs"))
    dialog.tabs.addTab(dialog.notes_tab, dialog._t("work_editor.tab.notes", "Notes"))


def setup_button_row(dialog) -> None:
    """Create the save/cancel button row and main layout."""
    root = QVBoxLayout(dialog)
    root.addWidget(dialog.tabs, 1)

    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog._on_save)
    buttons.rejected.connect(dialog.reject)
    dialog._dialog_buttons = buttons
    root.addWidget(buttons)


def finalize_ui(dialog) -> None:
    """Finalize visual polish after full widget hierarchy is built."""
    for combo in dialog.findChildren(QComboBox):
        if combo.property("toolLibraryCombo"):
            combo.style().unpolish(combo)
            combo.style().polish(combo)


def apply_secondary_button_theme(dialog) -> None:
    """Style dialog buttons with secondary gray theme, marking Save as primary."""
    save_btn = None
    cancel_btn = None
    if hasattr(dialog, "_dialog_buttons"):
        save_btn = dialog._dialog_buttons.button(QDialogButtonBox.Save)
        cancel_btn = dialog._dialog_buttons.button(QDialogButtonBox.Cancel)
        if save_btn is not None:
            save_btn.setText(dialog._t("common.save", "Save"))
        if cancel_btn is not None:
            cancel_btn.setText(dialog._t("common.cancel", "Cancel"))
    for btn in dialog.findChildren(QPushButton):
        btn.setProperty("secondaryAction", False)
        btn.setProperty("panelActionButton", True)
        if btn is save_btn:
            btn.setProperty("primaryAction", True)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

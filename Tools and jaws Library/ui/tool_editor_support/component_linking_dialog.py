"""Component linking dialog for spare parts linking.

Provides a modal dialog for selecting a component to link to one or more spare parts.
"""

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from shared.ui.helpers.editor_helpers import apply_secondary_button_theme


class ComponentLinkingDialog(QDialog):
    """Modal dialog for selecting a component to link spare parts to.

    Displays a dropdown of available components and allows the user to select one
    to be linked to one or more spare parts rows.

    Parameters:
        options: List of (display_text, component_key) tuples.
        preselected_key: Component key to preselect in the dropdown, if available.
        parent: Parent widget (typically the tool editor dialog).
        translate: Translation callable(key, default, **kwargs) -> str for UI text.
    """

    def __init__(
        self,
        options: list[tuple[str, str]],
        preselected_key: str = '',
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._options = options
        self._selected_key = None
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.setWindowTitle(self._t('tool_editor.component.picker_title', 'Component picker'))
        self.setProperty('workEditorDialog', True)
        self.resize(460, 0)

        dlg_layout = QVBoxLayout(self)
        dlg_layout.setContentsMargins(18, 18, 18, 18)
        dlg_layout.setSpacing(12)

        prompt = QLabel(self._t('tool_editor.component.pick_component', 'Link selected spare parts to:'))
        prompt.setProperty('detailSectionTitle', True)
        dlg_layout.addWidget(prompt)

        self.combo = QComboBox()
        self.combo.setObjectName('componentLinkingCombo')
        for display, key in options:
            self.combo.addItem(display, key)

        # Preselect if available
        preselected_key = (preselected_key or '').strip()
        if preselected_key:
            for idx in range(self.combo.count()):
                if str(self.combo.itemData(idx) or '').strip() == preselected_key:
                    self.combo.setCurrentIndex(idx)
                    break

        self._style_combo(self.combo)
        combo_field = QFrame()
        combo_field.setProperty('editorFieldCard', True)
        combo_field_layout = QHBoxLayout(combo_field)
        combo_field_layout.setContentsMargins(2, 2, 2, 2)
        combo_field_layout.setSpacing(0)
        combo_field_layout.addWidget(self.combo, 1)
        dlg_layout.addWidget(combo_field)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = btn_box.button(QDialogButtonBox.Ok)
        cancel_btn = btn_box.button(QDialogButtonBox.Cancel)
        if ok_btn is not None:
            ok_btn.setProperty('panelActionButton', True)
            ok_btn.setProperty('primaryAction', True)
            ok_btn.setText(self._t('common.ok', 'OK'))
        if cancel_btn is not None:
            cancel_btn.setProperty('panelActionButton', True)
            cancel_btn.setProperty('secondaryAction', True)
            cancel_btn.setText(self._t('common.cancel', 'Cancel'))

        apply_secondary_button_theme(self, ok_btn)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        dlg_layout.addWidget(btn_box)

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _style_combo(self, combo: QComboBox):
        """Apply shared dropdown styling and popup configuration."""
        from ui.widgets.common import apply_shared_dropdown_style

        apply_shared_dropdown_style(combo)
        view = combo.view()
        if view is None:
            return
        max_height = 8 * 44
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setMinimumHeight(0)
        view.setMaximumHeight(max_height)
        popup = view.window()
        popup.setMinimumHeight(0)
        popup.setMaximumHeight(max_height + 8)

    def selected_component_key(self) -> str | None:
        """Return the selected component key, or None if dialog was cancelled."""
        if self.result() != QDialog.Accepted:
            return None
        key = str(self.combo.currentData() or '').strip()
        return key if key else None

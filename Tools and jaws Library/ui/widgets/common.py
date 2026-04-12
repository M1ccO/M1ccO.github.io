from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QAbstractItemView, QComboBox, QWidget

from shared.ui.helpers.common_widgets import (
    AutoShrinkLabel,
    BorderOnlyComboItemDelegate,
    CollapsibleGroup,
    _ComboHoverFilter,
    _ComboPopupPositionFilter,
    _ComboPopupResetFilter,
    _ComboWheelGuardFilter,
    _reset_popup_visual_state,
    add_shadow,
    clear_focused_dropdown_on_outside_click,
    repolish_widget,
    styled_list_item_height,
)


_COMBO_SURFACE = QColor('#FCFCFC')
_COMBO_TEXT = QColor('#111111')
_COMBO_BORDER = QColor('#c8d0d8')
_COMBO_HOVER = QColor('#F0F0F0')


def apply_shared_dropdown_style(combo):
    """Apply unified popup and hover behavior for comboboxes across the app."""
    combo.setProperty('hovered', False)
    combo.setAttribute(Qt.WA_Hover, True)
    combo.setAttribute(Qt.WA_StyledBackground, True)

    combo_palette = QPalette(combo.palette())
    combo_palette.setColor(QPalette.Button, QColor('#FAFAFA'))
    combo_palette.setColor(QPalette.Base, _COMBO_SURFACE)
    combo_palette.setColor(QPalette.Window, _COMBO_SURFACE)
    combo_palette.setColor(QPalette.Text, _COMBO_TEXT)
    combo_palette.setColor(QPalette.ButtonText, _COMBO_TEXT)
    combo_palette.setColor(QPalette.WindowText, _COMBO_TEXT)
    combo_palette.setColor(QPalette.Highlight, _COMBO_HOVER)
    combo_palette.setColor(QPalette.HighlightedText, _COMBO_TEXT)
    combo.setPalette(combo_palette)

    view = combo.view()
    view.setMouseTracking(True)
    view.viewport().setMouseTracking(True)
    view.setAutoFillBackground(True)
    view.viewport().setAutoFillBackground(True)
    view.setItemDelegate(BorderOnlyComboItemDelegate(view))

    view_palette = QPalette(view.palette())
    view_palette.setColor(QPalette.Base, _COMBO_SURFACE)
    view_palette.setColor(QPalette.Window, _COMBO_SURFACE)
    view_palette.setColor(QPalette.Text, _COMBO_TEXT)
    view_palette.setColor(QPalette.WindowText, _COMBO_TEXT)
    view_palette.setColor(QPalette.Highlight, _COMBO_HOVER)
    view_palette.setColor(QPalette.HighlightedText, _COMBO_TEXT)
    view.setPalette(view_palette)
    view.viewport().setPalette(view_palette)

    popup_window = view.window()
    popup_window.setAttribute(Qt.WA_StyledBackground, True)
    popup_window.setPalette(view_palette)
    popup_window.setStyleSheet('background-color: #FCFCFC; border: 1px solid #c8d0d8;')

    popup_row_height = combo.property('dropdownPopupRowHeight')
    if popup_row_height is None:
        size_profile = str(combo.property('dropdownSizeProfile') or '')
        if size_profile == 'compact':
            popup_row_height = 22
        else:
            popup_row_height = 44
    if popup_row_height is not None:
        try:
            popup_row_height = int(popup_row_height)
        except (TypeError, ValueError):
            popup_row_height = None
    if popup_row_height:
        max_rows = max(1, combo.maxVisibleItems())
        popup_height = max_rows * popup_row_height
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        view.setMinimumHeight(0)
        view.setMaximumHeight(popup_height)
        popup_window.setMinimumHeight(0)
        popup_window.setMaximumHeight(popup_height + 6)

    hover_filter = _ComboHoverFilter(combo)
    combo.installEventFilter(hover_filter)
    view.installEventFilter(hover_filter)
    view.viewport().installEventFilter(hover_filter)

    wheel_guard = _ComboWheelGuardFilter(combo)
    combo.installEventFilter(wheel_guard)

    popup_reset_filter = _ComboPopupResetFilter(combo)
    view.installEventFilter(popup_reset_filter)
    view.viewport().installEventFilter(popup_reset_filter)
    view.window().installEventFilter(popup_reset_filter)

    popup_position_filter = _ComboPopupPositionFilter(combo)
    view.window().installEventFilter(popup_position_filter)

    # After selecting an item, clear popup row visuals once the popup closes.
    combo.activated.connect(lambda _idx: QTimer.singleShot(0, lambda: _reset_popup_visual_state(combo)))

    # Keep an owning reference so the filter stays alive.
    combo._shared_dropdown_hover_filter = hover_filter
    combo._shared_dropdown_wheel_guard = wheel_guard
    combo._shared_dropdown_popup_reset_filter = popup_reset_filter
    combo._shared_dropdown_popup_position_filter = popup_position_filter



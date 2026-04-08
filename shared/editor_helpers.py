"""
Common editor dialog utilities shared between Tools and jaws Library and Setup Manager.

Extracted from work_editor_dialog patterns so that tool_editor and jaw_editor
dialogs stay visually consistent without duplicating boilerplate.
"""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_SHADOW_COLOR = QColor(121, 138, 156, 72)
_TITLED_SECTION_STYLESHEET = (
    'QGroupBox {'
    '  background-color: #f0f6fc;'
    '  border: 1px solid #d0d8e0;'
    '  border-radius: 6px;'
    '  margin-top: 10px;'
    '  padding-top: 8px;'
    '}'
    'QGroupBox::title {'
    '  subcontrol-origin: margin;'
    '  left: 10px;'
    '  padding: 0 4px;'
    '  color: #5a6b7c;'
    '  font-size: 8pt;'
    '  font-weight: 600;'
    '}'
)


# ── Shadow helper ────────────────────────────────────────────────────────

def add_shadow(widget, blur_radius=6, x_offset=0, y_offset=1):
    """Apply a subtle drop shadow effect to *widget*."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur_radius)
    effect.setOffset(x_offset, y_offset)
    effect.setColor(_SHADOW_COLOR)
    widget.setGraphicsEffect(effect)


# ── Dialog setup ─────────────────────────────────────────────────────────

def setup_editor_dialog(dialog: QDialog):
    """Apply the standard work-editor property so QSS scoping rules match."""
    dialog.setProperty('workEditorDialog', True)


def apply_titled_section_style(group: QGroupBox) -> QGroupBox:
    """Apply the shared titled-section style used by editor helper panels."""
    group.setStyleSheet(_TITLED_SECTION_STYLESHEET)
    return group


def create_titled_section(title: str) -> QGroupBox:
    """Create a light-blue titled section matching measurement editor groups."""
    group = QGroupBox(title)
    apply_titled_section_style(group)
    group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return group


# ── Button bar ───────────────────────────────────────────────────────────

def create_dialog_buttons(
    dialog: QDialog,
    save_text: str = 'Save',
    cancel_text: str = 'Cancel',
    on_save=None,
    on_cancel=None,
) -> QDialogButtonBox:
    """Create a QDialogButtonBox matching work_editor's pattern.

    Returns the button-box widget, ready to be added to a layout.
    """
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)

    save_btn = buttons.button(QDialogButtonBox.Save)
    cancel_btn = buttons.button(QDialogButtonBox.Cancel)
    if save_btn is not None:
        save_btn.setText(save_text)
    if cancel_btn is not None:
        cancel_btn.setText(cancel_text)

    if on_save is not None:
        buttons.accepted.connect(on_save)
    if on_cancel is not None:
        buttons.rejected.connect(on_cancel)

    return buttons


def ask_multi_edit_mode(parent: QDialog, count: int, translate=None) -> str | None:
    """Ask how to edit multiple selected items.

    Returns:
        'batch' for sequential batch edit,
        'group' for shared group edit,
        None when cancelled.
    """
    t = translate or (lambda _key, default=None, **_kwargs: default or '')
    dialog = QDialog(parent)
    setup_editor_dialog(dialog)
    dialog.setModal(True)
    dialog.setWindowTitle(t('multi_edit.title', 'Multiple items selected'))

    root = QVBoxLayout(dialog)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(10)

    label = QLabel(
        t(
            'multi_edit.prompt',
            'You selected {count} items. Choose edit mode.',
            count=count,
        )
    )
    label.setWordWrap(True)
    label.setStyleSheet('background: transparent; border: none;')
    label.setMaximumWidth(440)
    root.addWidget(label)

    button_row = QHBoxLayout()
    button_row.setContentsMargins(0, 0, 0, 0)
    button_row.setSpacing(8)

    batch_btn = QPushButton(t('multi_edit.batch', 'Batch Edit'))
    group_btn = QPushButton(t('multi_edit.group', 'Group Edit'))
    cancel_btn = QPushButton(t('common.cancel', 'Cancel'))

    for btn in (batch_btn, group_btn, cancel_btn):
        btn.setProperty('panelActionButton', True)
    batch_btn.setProperty('primaryAction', True)
    cancel_btn.setProperty('secondaryAction', True)

    result = {'mode': None}

    def _choose(mode: str):
        result['mode'] = mode
        dialog.accept()

    batch_btn.clicked.connect(lambda: _choose('batch'))
    group_btn.clicked.connect(lambda: _choose('group'))
    cancel_btn.clicked.connect(dialog.reject)

    button_row.addWidget(batch_btn)
    button_row.addWidget(group_btn)
    button_row.addWidget(cancel_btn)
    root.addLayout(button_row)

    apply_secondary_button_theme(dialog, batch_btn)
    dialog.adjustSize()

    if dialog.exec() != QDialog.Accepted:
        return None
    return result['mode']


def apply_secondary_button_theme(dialog: QDialog, save_btn=None):
    """Style every QPushButton in *dialog* to the unified panel-action look.

    Matches ``WorkEditorDialog._set_secondary_button_theme``.
    """
    for btn in dialog.findChildren(QPushButton):
        btn.setProperty('secondaryAction', False)
        btn.setProperty('panelActionButton', True)
        if btn is save_btn:
            btn.setProperty('primaryAction', True)
        btn.style().unpolish(btn)
        btn.style().polish(btn)


# ── Arrow / icon buttons ────────────────────────────────────────────────

def make_arrow_button(icon_path, tooltip: str) -> QPushButton:
    """Create a small square icon-button used for move-up / move-down / pick."""
    btn = QPushButton('')
    btn.setProperty('arrowMoveButton', True)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.PointingHandCursor)
    icon = QIcon(str(icon_path))
    if not icon.isNull():
        btn.setIcon(icon)
        btn.setIconSize(QSize(18, 18))
    btn.setMinimumSize(32, 32)
    btn.setMaximumSize(32, 32)
    add_shadow(btn)
    return btn


def style_panel_action_button(btn: QPushButton):
    """Mark *btn* as a panel-action button and give it a shadow."""
    btn.setProperty('panelActionButton', True)
    add_shadow(btn)


def style_icon_action_button(btn: QPushButton, icon_path, tooltip: str, *, danger: bool = False):
    """Match the compact icon-action buttons used in work_editor tool IDs."""
    btn.setText('')
    btn.setToolTip(tooltip)
    btn.setProperty('panelActionButton', True)
    if danger:
        btn.setProperty('dangerAction', True)
    icon = QIcon(str(icon_path))
    if not icon.isNull():
        btn.setIcon(icon)
        btn.setIconSize(QSize(18, 18))
    btn.setFixedSize(52, 32)
    btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


def style_move_arrow_button(btn: QPushButton, text: str, tooltip: str):
    """Match the rectangular up/down move buttons used in work_editor tool IDs."""
    btn.setText(text)
    btn.setToolTip(tooltip)
    btn.setProperty('panelActionButton', True)
    btn.setMinimumWidth(52)
    btn.setMaximumWidth(64)
    btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    btn.setStyleSheet('font-size: 16px; font-weight: 700;')


# ── Field grid reflow ────────────────────────────────────────────────────

def reflow_fields_grid(
    grid: QGridLayout,
    field_order: list,
    columns: int,
    scroll: QScrollArea | None = None,
):
    """Re-lay the field cards into *columns*.  Identical to the pattern used
    in all five editor dialogs.
    """
    sb = scroll.verticalScrollBar() if scroll is not None else None
    old_scroll = sb.value() if sb is not None else 0

    while grid.count():
        item = grid.takeAt(0)
        w = item.widget()
        if w:
            w.setParent(None)

    visible = list(field_order)
    if columns <= 1:
        for row, field in enumerate(visible):
            grid.addWidget(field, row, 0, 1, 2)
    else:
        left_count = (len(visible) + 1) // 2
        for i in range(left_count):
            grid.addWidget(visible[i], i, 0, 1, 2)
        for j in range(len(visible) - left_count):
            grid.addWidget(visible[left_count + j], j, 2, 1, 2)

    if sb is not None:
        QTimer.singleShot(
            0, lambda s=sb, v=old_scroll: s.setValue(min(v, s.maximum()))
        )


# ── Picker row builder ──────────────────────────────────────────────────

def build_picker_row(editor, handler, tooltip: str, icon_path) -> QWidget:
    """A text input with a small icon button beside it (e.g. component picker)."""
    row = QWidget()
    row.setProperty('editorInlineRow', True)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(editor, 1)

    btn = make_arrow_button(icon_path, tooltip)
    btn.clicked.connect(handler)
    lay.addWidget(btn)
    return row

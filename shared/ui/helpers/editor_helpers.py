"""
Common editor dialog utilities shared between Tools and jaws Library and Setup Manager.

Extracted from work_editor_dialog patterns so that tool_editor and jaw_editor
dialogs stay visually consistent without duplicating boilerplate.
"""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
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
    '  subcontrol-position: top left;'
    '  left: 10px;'
    '  top: -3px;'
    '  padding: 0 6px;'
    '  color: #22303c;'
    '  font-size: 10.5pt;'
    '  font-weight: 700;'
    '}'
)

_CHECKBOX_EDGE_COLOR = '#8aa0b6'
_CHECKBOX_EDGE_HOVER_COLOR = '#6f86a0'
_CHECKBOX_CHECK_ICON = (Path(__file__).resolve().parents[2] / 'assets' / 'check_mark.svg').as_posix()


from shared.ui.helpers.common_widgets import add_shadow
from shared.ui.helpers.icon_loader import icon_from_path


class ResponsiveColumnsHost(QWidget):
    """Lay out panels side-by-side when wide and stack them when narrow."""

    def __init__(
        self,
        switch_width: int = 980,
        parent=None,
        separator_property: str | None = None,
    ):
        super().__init__(parent)
        self._switch_width = switch_width
        self._separator_property = separator_property
        self._added_widgets = 0
        self._separators: list[QFrame] = []
        self._layout = QBoxLayout(QBoxLayout.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(16)

    def add_widget(self, widget: QWidget, stretch: int = 1):
        if self._separator_property and self._added_widgets > 0:
            separator = QFrame()
            separator.setProperty(self._separator_property, True)
            separator.setFrameShadow(QFrame.Plain)
            separator.setLineWidth(1)
            self._separators.append(separator)
            self._layout.addWidget(separator, 0)
        self._layout.addWidget(widget, stretch)
        self._added_widgets += 1
        self._update_separator_shapes()

    def _update_separator_shapes(self):
        if not self._separators:
            return
        is_vertical = self._layout.direction() == QBoxLayout.LeftToRight
        for separator in self._separators:
            if is_vertical:
                separator.setFrameShape(QFrame.VLine)
                separator.setFixedWidth(1)
                separator.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            else:
                separator.setFrameShape(QFrame.HLine)
                separator.setFixedHeight(1)
                separator.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        direction = (
            QBoxLayout.TopToBottom
            if event.size().width() < self._switch_width
            else QBoxLayout.LeftToRight
        )
        if self._layout.direction() != direction:
            self._layout.setDirection(direction)
        self._update_separator_shapes()


# ── Dialog setup ─────────────────────────────────────────────────────────

def setup_editor_dialog(dialog: QDialog):
    """Apply the standard work-editor property so QSS scoping rules match."""
    dialog.setProperty('workEditorDialog', True)


def apply_titled_section_style(group: QGroupBox) -> QGroupBox:
    """Apply the shared titled-section style used by editor helper panels."""
    group.setStyleSheet(_TITLED_SECTION_STYLESHEET)
    return group


def create_titled_section(title: str, parent: QWidget | None = None) -> QGroupBox:
    """Create a light-blue titled section matching measurement editor groups."""
    group = QGroupBox(title, parent)
    apply_titled_section_style(group)
    group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return group


def apply_shared_checkbox_style(
    checkbox: QCheckBox,
    *,
    indicator_size: int = 16,
    min_height: int = 0,
) -> QCheckBox:
    """Apply a shared checkbox look with visible box edges and checkmark icon."""
    checkbox_style = [
        'QCheckBox {'
        '  background: transparent;'
        '  spacing: 6px;'
    ]
    if min_height > 0:
        checkbox_style.append(f'  min-height: {int(min_height)}px;')
    checkbox_style.append('}')
    checkbox_style.extend([
        'QCheckBox::indicator {'
        f'  width: {int(indicator_size)}px;'
        f'  height: {int(indicator_size)}px;'
        f'  border: 1px solid {_CHECKBOX_EDGE_COLOR};'
        '  border-radius: 3px;'
        '  background: #ffffff;'
        '}',
        'QCheckBox::indicator:unchecked {'
        f'  border: 1px solid {_CHECKBOX_EDGE_COLOR};'
        '  border-radius: 3px;'
        '  background: #ffffff;'
        '}',
        'QCheckBox::indicator:checked {'
        f'  border: 1px solid {_CHECKBOX_EDGE_COLOR};'
        '  border-radius: 3px;'
        '  background: #ffffff;'
        f'  image: url("{_CHECKBOX_CHECK_ICON}");'
        '}',
        'QCheckBox::indicator:checked:hover {'
        f'  border: 1px solid {_CHECKBOX_EDGE_HOVER_COLOR};'
        '}',
        'QCheckBox::indicator:unchecked:hover {'
        f'  border: 1px solid {_CHECKBOX_EDGE_HOVER_COLOR};'
        '}',
    ])
    checkbox.setStyleSheet(''.join(checkbox_style))
    return checkbox


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
    icon = icon_from_path(icon_path, size=QSize(18, 18))
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
    icon = icon_from_path(icon_path, size=QSize(18, 18))
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


# ── Detail field card helpers ───────────────────────────────────────────

def focus_editor_widget(widget: QWidget):
    """Focus the most relevant input inside *widget*.

    Used by detail-field labels so clicking a key label focuses its editor.
    """
    if isinstance(widget, QLineEdit):
        widget.setFocus()
        widget.selectAll()
        return
    if isinstance(widget, QTextEdit):
        widget.setFocus()
        return
    if isinstance(widget, QComboBox):
        widget.setFocus()
        return
    if isinstance(widget, QPushButton):
        widget.setFocus()
        return

    for child in widget.findChildren(QLineEdit):
        child.setFocus()
        child.selectAll()
        return
    for child in widget.findChildren(QComboBox):
        child.setFocus()
        return
    for child in widget.findChildren(QTextEdit):
        child.setFocus()
        return
    for child in widget.findChildren(QPushButton):
        child.setFocus()
        return


def build_editor_field_card(
    title: str,
    editor: QWidget,
    *,
    key_label: QLabel | None = None,
    label_min_width: int = 200,
    label_max_width: int = 200,
    label_word_wrap: bool = True,
    label_top_align: bool = True,
    focus_handler=None,
) -> QFrame:
    """Create a standard editor field row used in Tool/Jaw detail panels."""
    frame = QFrame()
    frame.setProperty('editorFieldCard', True)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.setSpacing(8)

    label = key_label if key_label is not None else QLabel(title)
    label.setProperty('detailFieldKey', True)
    label.setWordWrap(bool(label_word_wrap))
    label.setAlignment(Qt.AlignLeft | (Qt.AlignTop if label_top_align else Qt.AlignVCenter))
    label.setMinimumWidth(max(0, int(label_min_width)))
    label.setMaximumWidth(max(0, int(label_max_width)))
    if focus_handler is not None:
        label.mousePressEvent = lambda _event, w=editor: focus_handler(w)

    layout.addWidget(label, 0)
    layout.addWidget(editor, 1)
    frame._field_label = label
    return frame


def build_editor_field_group(fields: list[QWidget]) -> QFrame:
    """Create a standard vertical group for related editor field cards."""
    group = QFrame()
    group.setProperty('editorFieldGroup', True)
    layout = QVBoxLayout(group)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(4)
    for field in fields:
        layout.addWidget(field)
    return group


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


# ── Detail display helpers ─────────────────────────────────────────────

def _normalize_multiline_detail_value(value) -> str:
    raw_value = '' if value is None else str(value)
    return (
        raw_value
        .replace('\r\n', '\n')
        .replace('\r', '\n')
        .replace('\u2028', '\n')
        .replace('\u2029', '\n')
        .replace('\\n', '\n')
    )


def _build_readonly_detail_line(value_text: str, *, tooltip: bool = True) -> QLineEdit:
    line = QLineEdit(value_text if value_text.strip() else '-')
    line.setReadOnly(True)
    line.setFocusPolicy(Qt.NoFocus)
    line.setCursorPosition(0)
    line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    line.setToolTip(value_text.strip() or '-') if tooltip else line.setToolTip('')
    return line


def build_titled_detail_field(label_text: str, value_text: str, *, multiline: bool = False) -> QGroupBox:
    """Create the Tool-style titled readonly detail field."""
    field_group = create_titled_section(label_text)
    field_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    field_group.setMinimumWidth(0)

    flayout = QVBoxLayout(field_group)
    flayout.setContentsMargins(6, 4, 6, 4)
    flayout.setSpacing(4)

    if multiline:
        normalized = _normalize_multiline_detail_value(value_text)
        value_label = QLabel(normalized if normalized.strip() else '-')
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value_label.setFocusPolicy(Qt.NoFocus)
        value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        value_label.setMinimumHeight(32)
        value_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        value_label.setStyleSheet(
            'QLabel {'
            '  background-color: #ffffff;'
            '  border: 1px solid #c8d4e0;'
            '  border-radius: 6px;'
            '  padding: 6px;'
            '  font-size: 10.5pt;'
            '}'
        )
        value_label.setToolTip('')
        flayout.addWidget(value_label)
    else:
        flayout.addWidget(_build_readonly_detail_line('' if value_text is None else str(value_text)))

    return field_group


def build_titled_detail_list_field(label_text: str, values: list[str]) -> QGroupBox:
    """Create a Tool-style titled readonly field with multiple stacked lines."""
    field_group = create_titled_section(label_text)
    field_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    field_group.setMinimumWidth(0)

    flayout = QVBoxLayout(field_group)
    flayout.setContentsMargins(6, 4, 6, 4)
    flayout.setSpacing(6)

    normalized = [str(v).strip() for v in (values or []) if str(v).strip()]
    if not normalized:
        flayout.addWidget(_build_readonly_detail_line('-', tooltip=False))
        return field_group

    for value in normalized:
        flayout.addWidget(_build_readonly_detail_line(value))

    return field_group

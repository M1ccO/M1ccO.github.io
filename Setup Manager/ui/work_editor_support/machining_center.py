from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from config import TOOL_ICONS_DIR

try:
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
except ModuleNotFoundError:
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard


def _axis_display_label(dialog: Any, axis: str) -> str:
    axis_key = str(axis or '').strip().lower()
    if axis_key in {'x', 'y', 'z'}:
        return axis_key.upper()
    profile = dialog.machine_profile
    if axis_key == 'c' and int(getattr(profile, 'axis_count', 3) or 3) >= 4:
        return str(getattr(profile, 'fourth_axis_letter', 'C') or 'C').strip().upper()
    if axis_key == 'b' and int(getattr(profile, 'axis_count', 3) or 3) == 5:
        return str(getattr(profile, 'fifth_axis_letter', 'B') or 'B').strip().upper()
    return axis_key.upper()


def _default_coord_for_index(work_coordinates: list[str] | tuple[str, ...], index: int) -> str:
    if not work_coordinates:
        return 'G54'
    idx = min(max(0, index), len(work_coordinates) - 1)
    return str(work_coordinates[idx] or 'G54')


def _default_operation(dialog: Any, index: int, work_coordinates: list[str] | tuple[str, ...]) -> dict:
    return {
        'op_key': f'OP{(index + 1) * 10}',
        'coord': _default_coord_for_index(work_coordinates, index),
        'sub_program': '',
        'fixture_ids': [],
        'fixture_items': [],
        'selected_fixture_part': '',
        'tool_assignments': [],
        'tool_ids': [],
        'axes': {axis: '' for axis in dialog._zero_axes},
    }


def _normalize_fixture_part_ids(raw: Any) -> list[str]:
    if isinstance(raw, list):
        values = raw
    else:
        text = str(raw or '').strip()
        if not text:
            values = []
        else:
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = []
            values = parsed if isinstance(parsed, list) else []
    normalized: list[str] = []
    for item in values:
        value = str(item or '').strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _fixture_kind(entry: dict) -> str:
    return str(entry.get('fixture_kind') or '').strip().lower()


def _op_part_options(op: dict) -> tuple[dict | None, list[str]]:
    fixtures = _fixture_display_items(op)
    if not fixtures:
        return None, []

    assembly = next((item for item in fixtures if _fixture_kind(item) == 'assembly'), None)
    part_ids = [
        str(item.get('fixture_id') or item.get('id') or '').strip()
        for item in fixtures
        if _fixture_kind(item) == 'part'
    ]
    part_ids = [item for item in part_ids if item]

    if assembly is None:
        deduped: list[str] = []
        for part_id in part_ids:
            if part_id not in deduped:
                deduped.append(part_id)
        return None, deduped

    assembly_part_ids = _normalize_fixture_part_ids(assembly.get('assembly_part_ids'))
    options = assembly_part_ids or part_ids
    deduped: list[str] = []
    for option in options:
        if option not in deduped:
            deduped.append(option)
    return assembly, deduped


def _normalize_operation(dialog: Any, raw: dict, index: int, work_coordinates: list[str] | tuple[str, ...]) -> dict:
    base = _default_operation(dialog, index, work_coordinates)
    if not isinstance(raw, dict):
        return base
    op_key = str(raw.get('op_key') or base['op_key']).strip() or base['op_key']
    coord = str(raw.get('coord') or base['coord']).strip() or base['coord']
    sub_program = str(raw.get('sub_program') or '').strip()
    fixture_ids = [str(item).strip() for item in (raw.get('fixture_ids') or []) if str(item).strip()]
    fixture_items: list[dict] = []
    raw_items = raw.get('fixture_items') or []
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            fixture_id = str(item.get('fixture_id') or item.get('id') or '').strip()
            if not fixture_id:
                continue
            fixture_items.append(
                {
                    'fixture_id': fixture_id,
                    'fixture_type': str(item.get('fixture_type') or '').strip(),
                    'fixture_kind': str(item.get('fixture_kind') or '').strip(),
                    'assembly_part_ids': _normalize_fixture_part_ids(item.get('assembly_part_ids')),
                }
            )
    if not fixture_items and fixture_ids:
        fixture_items = [
            {'fixture_id': fixture_id, 'fixture_type': '', 'fixture_kind': '', 'assembly_part_ids': []}
            for fixture_id in fixture_ids
        ]

    tool_assignments: list[dict] = []
    raw_tool_assignments = raw.get('tool_assignments') or []
    if isinstance(raw_tool_assignments, list):
        for item in raw_tool_assignments:
            if isinstance(item, dict):
                tool_assignments.append(dict(item))

    tool_ids = [str(item).strip() for item in (raw.get('tool_ids') or []) if str(item).strip()]

    axes = {}
    raw_axes = raw.get('axes') if isinstance(raw.get('axes'), dict) else {}
    for axis in dialog._zero_axes:
        axes[axis] = str(raw_axes.get(axis, raw.get(axis, '')) or '').strip()

    return {
        'op_key': op_key,
        'coord': coord,
        'sub_program': sub_program,
        'fixture_ids': fixture_ids,
        'fixture_items': fixture_items,
        'selected_fixture_part': str(raw.get('selected_fixture_part') or '').strip(),
        'tool_assignments': tool_assignments,
        'tool_ids': tool_ids,
        'axes': axes,
    }


def _sync_operations_from_widgets(dialog: Any) -> None:
    widgets_by_key = getattr(dialog, '_mc_operation_widgets', {}) or {}
    shared_sub_program = ''
    if hasattr(dialog, 'mc_sub_program_input') and dialog.mc_sub_program_input is not None:
        shared_sub_program = dialog.mc_sub_program_input.text().strip()
    synced: list[dict] = []
    for op in getattr(dialog, '_mc_operations', []) or []:
        op_key = str(op.get('op_key') or '').strip()
        widgets = widgets_by_key.get(op_key)
        if widgets is None:
            copied = dict(op)
            copied['sub_program'] = shared_sub_program
            synced.append(copied)
            continue
        axes = {
            axis: widgets['axis_inputs'][axis].text().strip()
            for axis in dialog._zero_axes
            if axis in widgets['axis_inputs']
        }
        synced.append(
            {
                'op_key': op_key,
                'coord': widgets['coord_combo'].currentText().strip(),
                'sub_program': shared_sub_program,
                'fixture_ids': [str(item).strip() for item in (op.get('fixture_ids') or []) if str(item).strip()],
                'fixture_items': [dict(item) for item in (op.get('fixture_items') or []) if isinstance(item, dict)],
                'selected_fixture_part': str(
                    (
                        widgets.get('fixtures_part_combo').currentData()
                        if widgets.get('fixtures_part_combo') is not None
                        else op.get('selected_fixture_part')
                    )
                    or ''
                ).strip(),
                'tool_assignments': [dict(item) for item in (op.get('tool_assignments') or []) if isinstance(item, dict)],
                'tool_ids': [str(item).strip() for item in (op.get('tool_ids') or []) if str(item).strip()],
                'axes': axes,
            }
        )
    dialog._mc_operations = synced


def _fixture_display_items(op: dict) -> list[dict]:
    fixture_items = [dict(item) for item in (op.get('fixture_items') or []) if isinstance(item, dict)]
    if fixture_items:
        return fixture_items
    fixture_ids = [str(item).strip() for item in (op.get('fixture_ids') or []) if str(item).strip()]
    return [
        {'fixture_id': fixture_id, 'fixture_type': '', 'fixture_kind': '', 'assembly_part_ids': []}
        for fixture_id in fixture_ids
    ]


def _sync_fixture_cards(dialog: Any, op_key: str) -> None:
    widgets = getattr(dialog, '_mc_operation_widgets', {}).get(op_key)
    if widgets is None:
        return
    op = next((item for item in dialog._mc_operations if str(item.get('op_key') or '').strip() == op_key), None)
    if op is None:
        return

    assembly_layout = widgets['fixtures_assembly_layout']
    assembly_host = widgets['fixtures_assembly_host']
    part_combo = widgets['fixtures_part_combo']
    placeholder = widgets['fixtures_placeholder']
    for card in widgets.get('fixture_cards') or []:
        try:
            card.deleteLater()
        except Exception:
            pass
    widgets['fixture_cards'] = []

    while assembly_layout.count():
        item = assembly_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()

    fixtures = _fixture_display_items(op)
    assembly_item, part_options = _op_part_options(op)

    assembly_host.setVisible(False)
    part_combo.blockSignals(True)
    part_combo.clear()
    part_combo.setVisible(False)

    if assembly_item is not None:
        fixture_icon = QIcon(str(TOOL_ICONS_DIR / 'assemblies_icon.svg'))
        if fixture_icon.isNull():
            fixture_icon = QIcon()
        fixture_id = str(assembly_item.get('fixture_id') or assembly_item.get('id') or '').strip()
        fixture_type = str(assembly_item.get('fixture_type') or '').strip()
        fixture_kind = str(assembly_item.get('fixture_kind') or '').strip()
        title = f'{fixture_id}  -  {fixture_type}' if fixture_type else fixture_id
        card = MiniAssignmentCard(
            icon=fixture_icon,
            title=title,
            subtitle=fixture_kind,
            badges=[],
            editable=False,
            compact=True,
            parent=widgets['fixtures_controls_host'],
        )
        card.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        assembly_layout.addWidget(card, 0, Qt.AlignLeft)
        widgets['fixture_cards'].append(card)
        assembly_host.setVisible(True)

    for part_id in part_options:
        part_combo.addItem(part_id, part_id)

    if part_options:
        selected_part = str(op.get('selected_fixture_part') or '').strip()
        selected_index = part_combo.findData(selected_part)
        if selected_index < 0:
            selected_index = 0
        part_combo.setCurrentIndex(selected_index)
        op['selected_fixture_part'] = str(part_combo.currentData() or '').strip()
        part_combo.setVisible(True)

    part_combo.blockSignals(False)

    if not fixtures:
        placeholder.setText(dialog._t('work_editor.mc.no_fixtures', 'No fixtures selected'))
        placeholder.setVisible(True)
        card = widgets.get('card')
        if card is not None:
            card.adjustSize()
            card.setFixedHeight(card.sizeHint().height())
        return

    if assembly_item is not None and not part_options:
        placeholder.setText(dialog._t('work_editor.mc.no_assembly_parts', 'No part fixtures linked to selected assembly'))
        placeholder.setVisible(True)
        card = widgets.get('card')
        if card is not None:
            card.adjustSize()
            card.setFixedHeight(card.sizeHint().height())
        return

    if assembly_item is None and not part_options:
        placeholder.setText(dialog._t('work_editor.mc.no_part_fixtures', 'No part fixtures selected'))
        placeholder.setVisible(True)
        card = widgets.get('card')
        if card is not None:
            card.adjustSize()
            card.setFixedHeight(card.sizeHint().height())
        return

    placeholder.setVisible(False)
    card = widgets.get('card')
    if card is not None:
        card.adjustSize()
        card.setFixedHeight(card.sizeHint().height())


def _refresh_operation_fixture_summary(dialog: Any, op_key: str) -> None:
    _sync_fixture_cards(dialog, op_key)


def _rebuild_operation_groups(dialog: Any, work_coordinates: list[str] | tuple[str, ...]) -> None:
    _sync_operations_from_widgets(dialog)

    while dialog._mc_operations_layout.count():
        item = dialog._mc_operations_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()

    dialog._mc_operation_widgets = {}

    for op in dialog._mc_operations:
        op_key = str(op.get('op_key') or '').strip()
        card = dialog._mc_create_section(op_key)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.setSpacing(10)

        coord_combo = dialog._mc_create_coord_combo(work_coordinates)
        idx = coord_combo.findText(str(op.get('coord') or '').strip())
        if idx >= 0:
            coord_combo.setCurrentIndex(idx)

        work_offset_label = QLabel(dialog._t('work_editor.mc.work_offset', 'Work offset'))
        work_offset_label.setProperty('detailFieldKey', True)
        card_layout.addWidget(work_offset_label, 0)

        section_grid = QGridLayout()
        section_grid.setContentsMargins(2, 0, 2, 2)
        section_grid.setHorizontalSpacing(8)
        section_grid.setVerticalSpacing(6)

        row_label_header = QLabel('')
        row_label_header.setMinimumWidth(96)
        section_grid.addWidget(row_label_header, 0, 0)

        coord_header = QLabel('WCS')
        coord_header.setProperty('detailFieldKey', True)
        coord_header.setAlignment(Qt.AlignCenter)
        section_grid.addWidget(coord_header, 0, 1)

        axis_inputs: dict[str, QLineEdit] = {}
        display_axes = [axis for axis in ('z', 'x', 'y', 'c', 'b') if axis in dialog._zero_axes]
        for col, axis in enumerate(display_axes):
            axis_label = QLabel(_axis_display_label(dialog, axis))
            axis_label.setProperty('detailFieldKey', True)
            axis_label.setAlignment(Qt.AlignCenter)
            section_grid.addWidget(axis_label, 0, col + 2)

            if col == 0:
                zero_row_label = QLabel(dialog._t('work_editor.mc.zero_points', 'Zero Points'))
                zero_row_label.setWordWrap(False)
                section_grid.addWidget(zero_row_label, 1, 0)

            axis_input = QLineEdit(str((op.get('axes') or {}).get(axis, '') or '').strip())
            axis_input.setPlaceholderText(_axis_display_label(dialog, axis))
            axis_input.setMinimumWidth(88)
            axis_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            axis_inputs[axis] = axis_input
            section_grid.addWidget(axis_input, 1, col + 2)

        section_grid.addWidget(coord_combo, 1, 1)

        fixtures_row_label = QLabel(dialog._t('work_editor.mc.fixtures', 'Fixtures'))
        fixtures_row_label.setWordWrap(False)
        section_grid.addWidget(fixtures_row_label, 2, 0)

        fixtures_controls_host = QWidget(card)
        fixtures_controls_layout = QHBoxLayout(fixtures_controls_host)
        fixtures_controls_layout.setContentsMargins(0, 0, 0, 0)
        fixtures_controls_layout.setSpacing(8)

        fixtures_assembly_host = QWidget(fixtures_controls_host)
        fixtures_assembly_layout = QVBoxLayout(fixtures_assembly_host)
        fixtures_assembly_layout.setContentsMargins(0, 0, 0, 0)
        fixtures_assembly_layout.setSpacing(0)
        fixtures_controls_layout.addWidget(fixtures_assembly_host, 0)

        fixtures_part_combo = QComboBox(fixtures_controls_host)
        fixtures_part_combo.setProperty('modernDropdown', True)
        fixtures_part_combo.setMinimumWidth(92)
        fixtures_part_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        dialog._apply_coord_combo_popup_style(fixtures_part_combo)
        fixtures_controls_layout.addWidget(fixtures_part_combo, 0)

        fixtures_assembly_host = QWidget(fixtures_controls_host)
        fixtures_assembly_layout = QVBoxLayout(fixtures_assembly_host)
        fixtures_assembly_layout.setContentsMargins(0, 0, 0, 0)
        fixtures_assembly_layout.setSpacing(0)
        fixtures_controls_layout.addWidget(fixtures_assembly_host, 0)

        fixtures_placeholder = QLabel(dialog._t('work_editor.mc.no_fixtures', 'No fixtures selected'))
        fixtures_placeholder.setProperty('detailHint', True)
        fixtures_placeholder.setStyleSheet('font-style: italic; font-weight: 400;')
        fixtures_placeholder.setWordWrap(True)
        fixtures_placeholder.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        fixtures_controls_layout.addWidget(fixtures_placeholder, 0)
        fixtures_controls_layout.addStretch(1)

        section_grid.addWidget(fixtures_controls_host, 2, 1, 1, len(display_axes) + 1)

        section_grid.setColumnStretch(0, 0)
        section_grid.setColumnStretch(1, 1)
        for col in range(2, 2 + len(display_axes)):
            section_grid.setColumnStretch(col, 1)
        card_layout.addLayout(section_grid)

        def _on_fixture_part_combo_changed(_index: int, *, combo: QComboBox = fixtures_part_combo, key: str = op_key) -> None:
            selected_part = str(combo.currentData() or combo.currentText() or '').strip()
            target = next(
                (item for item in dialog._mc_operations if str(item.get('op_key') or '').strip() == key),
                None,
            )
            if target is not None:
                target['selected_fixture_part'] = selected_part

        fixtures_part_combo.currentIndexChanged.connect(_on_fixture_part_combo_changed)

        dialog._mc_operation_widgets[op_key] = {
            'card': card,
            'coord_combo': coord_combo,
            'axis_inputs': axis_inputs,
            'fixtures_controls_host': fixtures_controls_host,
            'fixtures_assembly_host': fixtures_assembly_host,
            'fixtures_assembly_layout': fixtures_assembly_layout,
            'fixtures_part_combo': fixtures_part_combo,
            'fixtures_placeholder': fixtures_placeholder,
            'fixture_cards': [],
        }
        _sync_fixture_cards(dialog, op_key)
        # Keep each OP section compact to avoid stretched background artifacts between cards.
        card.adjustSize()
        card.setFixedHeight(card.sizeHint().height())
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        dialog._mc_operations_layout.addWidget(card)

    dialog._mc_operations_layout.addStretch(1)
    if hasattr(dialog, '_refresh_mc_tools_op_options'):
        try:
            dialog._refresh_mc_tools_op_options()
        except Exception:
            pass


def build_machining_center_zeros_tab_ui(
    dialog: Any,
    *,
    create_titled_section_fn: Callable[[str], object],
    work_coordinates: list[str] | tuple[str, ...],
) -> None:
    dialog._mc_work_coordinates = tuple(work_coordinates)
    dialog._mc_operations = []
    dialog._mc_operation_widgets = {}

    dialog.zeros_tab.setProperty('zeroPointsSurface', True)
    outer = QVBoxLayout(dialog.zeros_tab)
    outer.setContentsMargins(18, 18, 18, 18)
    outer.setSpacing(0)

    programs_group = create_titled_section_fn(dialog._t('work_editor.zeros.nc_programs', 'NC Programs'))
    programs_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    programs_layout = QFormLayout(programs_group)
    programs_layout.setSpacing(8)
    dialog.main_program_input = QLineEdit()
    programs_layout.addRow(dialog._t('setup_page.field.main_program', 'Main program'), dialog.main_program_input)
    dialog.mc_sub_program_input = QLineEdit()
    programs_layout.addRow(dialog._t('work_editor.mc.sub_program', 'Sub-program'), dialog.mc_sub_program_input)
    dialog.mc_operation_count_spin = QSpinBox()
    dialog.mc_operation_count_spin.setMinimum(1)
    dialog.mc_operation_count_spin.setMaximum(20)
    dialog.mc_operation_count_spin.setValue(1)
    programs_layout.addRow(dialog._t('work_editor.mc.operation_count', 'Operations'), dialog.mc_operation_count_spin)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)

    content = QWidget()
    content.setProperty('zeroPointsSurface', True)
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(12)
    content_layout.addWidget(programs_group, 0)

    host = QWidget()
    dialog._mc_operations_layout = QVBoxLayout(host)
    dialog._mc_operations_layout.setContentsMargins(0, 0, 0, 0)
    dialog._mc_operations_layout.setSpacing(10)
    content_layout.addWidget(host, 1)

    scroll.setWidget(content)
    outer.addWidget(scroll, 1)

    def _create_section(title: str):
        section = create_titled_section_fn(title)
        # create_titled_section defaults to fixed vertical policy; operation cards
        # must grow with fixture cards to avoid overlap between OP sections.
        section.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        return section

    def _create_coord_combo(coords: list[str] | tuple[str, ...]):
        from PySide6.QtWidgets import QComboBox

        combo = QComboBox()
        combo.addItems(list(coords))
        combo.setProperty('modernDropdown', True)
        dialog._apply_coord_combo_popup_style(combo)
        return combo

    dialog._mc_create_section = _create_section
    dialog._mc_create_coord_combo = _create_coord_combo

    def _on_count_changed(value: int) -> None:
        _sync_operations_from_widgets(dialog)
        desired = max(1, int(value or 1))
        current = list(dialog._mc_operations)
        while len(current) < desired:
            current.append(_default_operation(dialog, len(current), dialog._mc_work_coordinates))
        if len(current) > desired:
            current = current[:desired]
        dialog._mc_operations = [
            _normalize_operation(dialog, item, index, dialog._mc_work_coordinates)
            for index, item in enumerate(current)
        ]
        _rebuild_operation_groups(dialog, dialog._mc_work_coordinates)

    dialog.mc_operation_count_spin.valueChanged.connect(_on_count_changed)
    _on_count_changed(1)


def load_machining_center_payload(dialog: Any, payload: dict) -> None:
    raw_ops = payload.get('mc_operations', [])
    if isinstance(raw_ops, str):
        try:
            raw_ops = json.loads(raw_ops)
        except Exception:
            raw_ops = []
    if not isinstance(raw_ops, list):
        raw_ops = []

    desired_count = int(payload.get('mc_operation_count', len(raw_ops) or 1) or 1)
    desired_count = max(1, desired_count)
    shared_sub_program = ''
    for raw in raw_ops:
        if not isinstance(raw, dict):
            continue
        candidate = str(raw.get('sub_program') or '').strip()
        if candidate:
            shared_sub_program = candidate
            break
    if not shared_sub_program:
        shared_sub_program = str(payload.get('head1_sub_program') or '').strip()
    ops = []
    for index in range(desired_count):
        raw = raw_ops[index] if index < len(raw_ops) else {}
        op = _normalize_operation(dialog, raw, index, dialog._mc_work_coordinates)
        op['sub_program'] = shared_sub_program
        ops.append(op)
    dialog._mc_operations = ops
    if hasattr(dialog, 'mc_sub_program_input') and dialog.mc_sub_program_input is not None:
        dialog.mc_sub_program_input.setText(shared_sub_program)
    if hasattr(dialog, 'mc_operation_count_spin'):
        dialog.mc_operation_count_spin.blockSignals(True)
        dialog.mc_operation_count_spin.setValue(desired_count)
        dialog.mc_operation_count_spin.blockSignals(False)
    _rebuild_operation_groups(dialog, dialog._mc_work_coordinates)


def collect_machining_center_payload(dialog: Any) -> tuple[int, list[dict]]:
    _sync_operations_from_widgets(dialog)
    shared_sub_program = ''
    if hasattr(dialog, 'mc_sub_program_input') and dialog.mc_sub_program_input is not None:
        shared_sub_program = dialog.mc_sub_program_input.text().strip()
    normalized: list[dict] = []
    for index, item in enumerate(dialog._mc_operations):
        op = _normalize_operation(dialog, item, index, dialog._mc_work_coordinates)
        op['sub_program'] = shared_sub_program
        normalized.append(op)
    dialog._mc_operations = normalized
    return len(normalized), normalized


def apply_fixture_selection_to_operation(dialog: Any, operation_key: str, selected_items: list[dict]) -> bool:
    target_key = str(operation_key or '').strip()
    if not target_key:
        return False
    op = next((item for item in dialog._mc_operations if str(item.get('op_key') or '').strip() == target_key), None)
    if op is None:
        return False

    normalized_items: list[dict] = []
    fixture_ids: list[str] = []
    for item in selected_items:
        if not isinstance(item, dict):
            continue
        fixture_id = str(item.get('fixture_id') or item.get('id') or '').strip()
        if not fixture_id:
            continue
        entry = {
            'fixture_id': fixture_id,
            'fixture_type': str(item.get('fixture_type') or '').strip(),
            'fixture_kind': str(item.get('fixture_kind') or '').strip(),
            'assembly_part_ids': _normalize_fixture_part_ids(item.get('assembly_part_ids')),
        }
        normalized_items.append(entry)
        fixture_ids.append(fixture_id)

    op['fixture_ids'] = fixture_ids
    op['fixture_items'] = normalized_items
    _assembly_item, part_options = _op_part_options(op)
    current_selected = str(op.get('selected_fixture_part') or '').strip()
    op['selected_fixture_part'] = current_selected if current_selected in part_options else (part_options[0] if part_options else '')
    _refresh_operation_fixture_summary(dialog, target_key)
    return True

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


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
        'axes': {axis: '' for axis in dialog._zero_axes},
    }


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
                }
            )
    if not fixture_items and fixture_ids:
        fixture_items = [{'fixture_id': fixture_id, 'fixture_type': '', 'fixture_kind': ''} for fixture_id in fixture_ids]

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
        'axes': axes,
    }


def _sync_operations_from_widgets(dialog: Any) -> None:
    widgets_by_key = getattr(dialog, '_mc_operation_widgets', {}) or {}
    synced: list[dict] = []
    for op in getattr(dialog, '_mc_operations', []) or []:
        op_key = str(op.get('op_key') or '').strip()
        widgets = widgets_by_key.get(op_key)
        if widgets is None:
            synced.append(dict(op))
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
                'sub_program': widgets['sub_program_input'].text().strip(),
                'fixture_ids': [str(item).strip() for item in (op.get('fixture_ids') or []) if str(item).strip()],
                'fixture_items': [dict(item) for item in (op.get('fixture_items') or []) if isinstance(item, dict)],
                'axes': axes,
            }
        )
    dialog._mc_operations = synced


def _fixture_summary_text(op: dict, translate: Callable[[str, str | None], str]) -> str:
    fixture_items = [dict(item) for item in (op.get('fixture_items') or []) if isinstance(item, dict)]
    if not fixture_items:
        fixture_ids = [str(item).strip() for item in (op.get('fixture_ids') or []) if str(item).strip()]
        if not fixture_ids:
            return translate('work_editor.mc.no_fixtures', 'No fixtures selected')
        return '\n'.join(fixture_ids)

    rows: list[str] = []
    for item in fixture_items:
        fixture_id = str(item.get('fixture_id') or '').strip()
        fixture_type = str(item.get('fixture_type') or '').strip()
        if fixture_id and fixture_type:
            rows.append(f'{fixture_id} - {fixture_type}')
        elif fixture_id:
            rows.append(fixture_id)
    return '\n'.join(rows) if rows else translate('work_editor.mc.no_fixtures', 'No fixtures selected')


def _refresh_operation_fixture_summary(dialog: Any, op_key: str) -> None:
    widgets = getattr(dialog, '_mc_operation_widgets', {}).get(op_key)
    if widgets is None:
        return
    op = next((item for item in dialog._mc_operations if str(item.get('op_key') or '').strip() == op_key), None)
    if op is None:
        return
    widgets['fixtures_summary'].setText(_fixture_summary_text(op, dialog._t))


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
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)

        coord_combo = dialog._mc_create_coord_combo(work_coordinates)
        idx = coord_combo.findText(str(op.get('coord') or '').strip())
        if idx >= 0:
            coord_combo.setCurrentIndex(idx)
        form.addRow(dialog._t('work_editor.mc.work_offset', 'Work offset'), coord_combo)

        sub_program_input = QLineEdit(str(op.get('sub_program') or '').strip())
        form.addRow(dialog._t('work_editor.mc.sub_program', 'Sub-program'), sub_program_input)
        card_layout.addLayout(form)

        axes_grid = QGridLayout()
        axes_grid.setHorizontalSpacing(8)
        axes_grid.setVerticalSpacing(6)
        axis_inputs: dict[str, QLineEdit] = {}
        for col, axis in enumerate(dialog._zero_axes):
            axis_label = QLabel(_axis_display_label(dialog, axis))
            axis_label.setProperty('detailFieldKey', True)
            axis_label.setAlignment(Qt.AlignCenter)
            axes_grid.addWidget(axis_label, 0, col)
            axis_input = QLineEdit(str((op.get('axes') or {}).get(axis, '') or '').strip())
            axis_input.setPlaceholderText(_axis_display_label(dialog, axis))
            axis_inputs[axis] = axis_input
            axes_grid.addWidget(axis_input, 1, col)
        card_layout.addLayout(axes_grid)

        fixtures_section = QWidget()
        fixtures_layout = QVBoxLayout(fixtures_section)
        fixtures_layout.setContentsMargins(0, 0, 0, 0)
        fixtures_layout.setSpacing(6)
        fixtures_title = QLabel(dialog._t('work_editor.mc.fixtures', 'Fixtures'))
        fixtures_title.setProperty('detailFieldKey', True)
        fixtures_layout.addWidget(fixtures_title)
        fixtures_summary = QLabel(_fixture_summary_text(op, dialog._t))
        fixtures_summary.setWordWrap(True)
        fixtures_summary.setProperty('detailHint', True)
        fixtures_layout.addWidget(fixtures_summary)
        fixtures_actions = QHBoxLayout()
        fixtures_actions.setContentsMargins(0, 0, 0, 0)
        fixtures_actions.setSpacing(8)
        select_btn = QPushButton(dialog._t('work_editor.mc.select_fixtures', 'SELECT FIXTURES'))
        select_btn.setProperty('panelActionButton', True)
        select_btn.setProperty('primaryAction', True)
        select_btn.clicked.connect(lambda _checked=False, key=op_key: dialog._open_fixture_selector(key))
        fixtures_actions.addWidget(select_btn, 0)
        fixtures_actions.addStretch(1)
        fixtures_layout.addLayout(fixtures_actions)
        card_layout.addWidget(fixtures_section)

        dialog._mc_operation_widgets[op_key] = {
            'coord_combo': coord_combo,
            'sub_program_input': sub_program_input,
            'axis_inputs': axis_inputs,
            'fixtures_summary': fixtures_summary,
        }
        dialog._mc_operations_layout.addWidget(card)

    dialog._mc_operations_layout.addStretch(1)


def build_machining_center_zeros_tab_ui(
    dialog: Any,
    *,
    create_titled_section_fn: Callable[[str], object],
    work_coordinates: list[str] | tuple[str, ...],
) -> None:
    dialog._mc_work_coordinates = tuple(work_coordinates)
    dialog._mc_operations = []
    dialog._mc_operation_widgets = {}

    outer = QVBoxLayout(dialog.zeros_tab)
    outer.setContentsMargins(18, 18, 18, 18)
    outer.setSpacing(10)

    programs_group = create_titled_section_fn(dialog._t('work_editor.zeros.nc_programs', 'NC Programs'))
    programs_layout = QFormLayout(programs_group)
    programs_layout.setSpacing(8)
    dialog.main_program_input = QLineEdit()
    programs_layout.addRow(dialog._t('setup_page.field.main_program', 'Main program'), dialog.main_program_input)
    dialog.mc_operation_count_spin = QSpinBox()
    dialog.mc_operation_count_spin.setMinimum(1)
    dialog.mc_operation_count_spin.setMaximum(20)
    dialog.mc_operation_count_spin.setValue(1)
    programs_layout.addRow(dialog._t('work_editor.mc.operation_count', 'Operations'), dialog.mc_operation_count_spin)
    outer.addWidget(programs_group, 0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    host = QWidget()
    dialog._mc_operations_layout = QVBoxLayout(host)
    dialog._mc_operations_layout.setContentsMargins(0, 0, 0, 0)
    dialog._mc_operations_layout.setSpacing(10)
    scroll.setWidget(host)
    outer.addWidget(scroll, 1)

    def _create_section(title: str):
        return create_titled_section_fn(title)

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
    ops = []
    for index in range(desired_count):
        raw = raw_ops[index] if index < len(raw_ops) else {}
        ops.append(_normalize_operation(dialog, raw, index, dialog._mc_work_coordinates))
    dialog._mc_operations = ops
    if hasattr(dialog, 'mc_operation_count_spin'):
        dialog.mc_operation_count_spin.blockSignals(True)
        dialog.mc_operation_count_spin.setValue(desired_count)
        dialog.mc_operation_count_spin.blockSignals(False)
    _rebuild_operation_groups(dialog, dialog._mc_work_coordinates)


def collect_machining_center_payload(dialog: Any) -> tuple[int, list[dict]]:
    _sync_operations_from_widgets(dialog)
    normalized: list[dict] = []
    for index, item in enumerate(dialog._mc_operations):
        op = _normalize_operation(dialog, item, index, dialog._mc_work_coordinates)
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
        }
        normalized_items.append(entry)
        fixture_ids.append(fixture_id)

    op['fixture_ids'] = fixture_ids
    op['fixture_items'] = normalized_items
    _refresh_operation_fixture_summary(dialog, target_key)
    return True

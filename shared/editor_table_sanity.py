from __future__ import annotations

"""Minimal sanity-check helper for shared EditorTable serialization behavior.

Run manually:
    python -m shared.editor_table_sanity
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from shared.editor_table import EditorTable


def run_editor_table_sanity_checks() -> list[str]:
    app = QApplication.instance() or QApplication([])
    _ = app  # keep local reference for linters

    table = EditorTable(['Name', 'Code', 'Linked'])
    table.set_column_keys(['name', 'code', 'linked_component'])
    table.set_read_only_columns(['linked_component'])

    table.add_row_dict({'name': 'Holder', 'code': 'HT06', 'linked_component': 'Holder (HT06)'})
    table.set_cell_user_data(0, 'linked_component', Qt.UserRole, 'holder:HT06')

    rows = table.row_dicts()
    assert len(rows) == 1, 'Expected one row in table.'
    assert rows[0]['name'] == 'Holder', 'Row dict did not preserve name.'
    assert rows[0]['code'] == 'HT06', 'Row dict did not preserve code.'

    stored_key = table.cell_user_data(0, 'linked_component', Qt.UserRole, '')
    assert stored_key == 'holder:HT06', 'UserRole component key mismatch.'

    table.add_row_dict({'name': 'Insert', 'code': 'DNMG', 'linked_component': 'Insert (DNMG)'})
    table.set_cell_user_data(1, 'linked_component', Qt.UserRole, 'cutting:DNMG')

    table.selectRow(1)
    table.move_selected_row(-1)

    moved_rows = table.row_dicts()
    assert moved_rows[0]['name'] == 'Insert', 'Row move did not preserve order.'
    assert moved_rows[1]['name'] == 'Holder', 'Row move did not preserve second row.'

    moved_key = table.cell_user_data(0, 'linked_component', Qt.UserRole, '')
    assert moved_key == 'cutting:DNMG', 'UserRole data was not preserved on row move.'

    return [
        'Row dict serialization OK',
        'UserRole data storage OK',
        'Non-destructive row move preserves data OK',
    ]


def main():
    results = run_editor_table_sanity_checks()
    for line in results:
        print(line)


if __name__ == '__main__':
    main()

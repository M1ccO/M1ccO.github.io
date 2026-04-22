"""Detail panel builders for JawPage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from config import PROJECTS_DIR, SHARED_UI_PREFERENCES_PATH
from shared.ui.helpers.editor_helpers import (
    build_titled_detail_field,
    build_titled_detail_list_field,
)
from ui.jaw_page_support.detail_layout_rules import apply_jaw_detail_grid_rules


def populate_detail_panel(page, jaw: dict | None) -> None:
    _clear_details(page)

    if not jaw:
        page.detail_layout.addWidget(build_empty_details_card(page))
        page.detail_layout.addStretch(1)
        return

    card = QFrame()
    card.setProperty('subCard', True)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)
    layout.addWidget(build_jaw_detail_header(page, jaw))

    info = QGridLayout()
    info.setHorizontalSpacing(14)
    info.setVerticalSpacing(8)

    def add_field(row: int, col: int, row_span: int, col_span: int, label_text: str, value_text: str) -> None:
        info.addWidget(
            build_titled_detail_field(label_text, '' if value_text is None else str(value_text)),
            row,
            col,
            row_span,
            col_span,
            Qt.AlignTop,
        )

    next_row = apply_jaw_detail_grid_rules(
        jaw=jaw,
        translate=page._t,
        localized_spindle_side=page._localized_spindle_side(jaw.get('spindle_side', '')),
        add_field=add_field,
    )

    info.addWidget(
        build_titled_detail_list_field(
            page._t('jaw_library.field.used_in_works', 'Used in works:'),
            _split_used_in_works(_lookup_setup_db_used_in_works(jaw.get('jaw_id', ''))),
        ),
        next_row,
        0,
        1,
        4,
        Qt.AlignTop,
    )

    notes_text = str(jaw.get('notes', '') or '').strip()
    if notes_text:
        info.addWidget(
            build_titled_detail_field(
                page._t('jaw_library.field.notes', 'Notes'),
                notes_text,
                multiline=True,
            ),
            next_row + 1,
            0,
            1,
            4,
            Qt.AlignTop,
        )

    layout.addLayout(info)
    # Inline 3D preview section intentionally removed.
    layout.addStretch(1)
    page.detail_layout.addWidget(card)


def build_empty_details_card(page) -> QFrame:
    card = QFrame()
    card.setProperty('subCard', True)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QLabel(page._t('jaw_library.section.details', 'Jaw details'))
    title.setProperty('detailSectionTitle', True)
    hint = QLabel(page._t('jaw_library.message.select_jaw_for_details', 'Select a jaw to view details.'))
    hint.setProperty('detailHint', True)
    hint.setWordWrap(True)
    layout.addWidget(title)
    layout.addWidget(hint)

    placeholder = QFrame()
    placeholder.setProperty('diagramPanel', True)
    placeholder_layout = QVBoxLayout(placeholder)
    placeholder_layout.setContentsMargins(12, 12, 12, 12)
    placeholder_layout.addStretch(1)
    placeholder_layout.addStretch(1)
    layout.addWidget(placeholder)
    return card


def build_jaw_detail_header(page, jaw: dict) -> QFrame:
    header = QFrame()
    header.setProperty('detailHeader', True)
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(14, 14, 14, 12)
    header_layout.setSpacing(4)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(10)

    jaw_id_lbl = QLabel(jaw.get('jaw_id', ''))
    jaw_id_lbl.setProperty('detailHeroTitle', True)
    jaw_id_lbl.setWordWrap(True)

    diam_lbl = QLabel(jaw.get('clamping_diameter_text', '') or '')
    diam_lbl.setProperty('detailHeroTitle', True)
    diam_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    title_row.addWidget(jaw_id_lbl, 1)
    title_row.addWidget(diam_lbl, 0, Qt.AlignRight)

    badge_row = QHBoxLayout()
    badge_row.setContentsMargins(0, 0, 0, 0)
    badge = QLabel(page._localized_jaw_type(jaw.get('jaw_type', '')))
    badge.setProperty('toolBadge', True)
    badge_row.addWidget(badge, 0, Qt.AlignLeft)
    badge_row.addStretch(1)

    header_layout.addLayout(title_row)
    header_layout.addLayout(badge_row)
    return header


def _clear_details(page) -> None:
    while page.detail_layout.count():
        item = page.detail_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def _split_used_in_works(value: str) -> list[str]:
    return [part.strip() for part in str(value or '').split('|') if part.strip()]


def _lookup_setup_db_used_in_works(jaw_id: str) -> str:
    if not jaw_id:
        return ''

    db_path: Path | None = None
    try:
        if SHARED_UI_PREFERENCES_PATH.exists():
            prefs = json.loads(SHARED_UI_PREFERENCES_PATH.read_text(encoding='utf-8'))
            candidate = str((prefs or {}).get('setup_db_path', '') or '').strip()
            if candidate:
                db_path = Path(candidate)
    except Exception:
        db_path = None

    if db_path is None or not db_path.exists():
        db_path = PROJECTS_DIR / 'Setup Manager' / 'databases' / 'setup_manager.db'
    if not db_path.exists():
        return ''

    try:
        uri = f'file:{db_path.as_posix()}?mode=ro&immutable=1'
        conn = sqlite3.connect(uri, uri=True)
        rows = conn.execute(
            'SELECT DISTINCT drawing_id FROM works '
            'WHERE (main_jaw_id = ? OR sub_jaw_id = ?) AND drawing_id != ""',
            (jaw_id, jaw_id),
        ).fetchall()
        conn.close()
        return ' | '.join(row[0] for row in rows if row and row[0])
    except Exception:
        return ''


__all__ = [
    'build_empty_details_card',
    'build_jaw_detail_header',
    'populate_detail_panel',
]
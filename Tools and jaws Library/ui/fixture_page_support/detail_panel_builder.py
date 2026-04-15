"""Detail panel builders for FixturePage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from config import PROJECTS_DIR, SHARED_UI_PREFERENCES_PATH
from shared.ui.helpers.editor_helpers import (
    build_titled_detail_field,
    build_titled_detail_list_field,
    create_titled_section,
)
from shared.ui.stl_preview import StlPreviewWidget
from ui.fixture_page_support.detail_layout_rules import apply_fixture_detail_grid_rules
from ui.fixture_page_support.preview_rules import (
    apply_fixture_preview_transform,
    fixture_preview_label,
    fixture_preview_measurement_overlays,
    fixture_preview_stl_path,
)


def populate_detail_panel(page, fixture: dict | None) -> None:
    _clear_details(page)

    if not fixture:
        page.detail_layout.addWidget(build_empty_details_card(page))
        page.detail_layout.addStretch(1)
        return

    card = QFrame()
    card.setProperty('subCard', True)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)
    layout.addWidget(build_fixture_detail_header(page, fixture))

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

    next_row = apply_fixture_detail_grid_rules(
        fixture=fixture,
        translate=page._t,
        localized_spindle_side=page._localized_fixture_kind(fixture.get('fixture_kind', '')),
        add_field=add_field,
    )

    info.addWidget(
        build_titled_detail_list_field(
            page._t('fixture_library.field.used_in_works', 'Used in works:'),
            _split_used_in_works(fixture.get('used_in_work', '')),
        ),
        next_row,
        0,
        1,
        4,
        Qt.AlignTop,
    )

    notes_text = str(fixture.get('notes', '') or '').strip()
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

    title = QLabel(page._t('fixture_library.section.details', 'Fixture details'))
    title.setProperty('detailSectionTitle', True)
    hint = QLabel(page._t('fixture_library.message.select_fixture_for_details', 'Select a fixture to view details.'))
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


def build_fixture_detail_header(page, fixture: dict) -> QFrame:
    header = QFrame()
    header.setProperty('detailHeader', True)
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(14, 14, 14, 12)
    header_layout.setSpacing(4)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(10)

    fixture_id_lbl = QLabel(fixture.get('fixture_id', ''))
    fixture_id_lbl.setProperty('detailHeroTitle', True)
    fixture_id_lbl.setWordWrap(True)

    diam_lbl = QLabel(fixture.get('clamping_diameter_text', '') or '')
    diam_lbl.setProperty('detailHeroTitle', True)
    diam_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    title_row.addWidget(fixture_id_lbl, 1)
    title_row.addWidget(diam_lbl, 0, Qt.AlignRight)

    badge_row = QHBoxLayout()
    badge_row.setContentsMargins(0, 0, 0, 0)
    badge = QLabel(page._localized_fixture_type(fixture.get('fixture_type', '')))
    badge.setProperty('toolBadge', True)
    badge_row.addWidget(badge, 0, Qt.AlignLeft)
    badge_row.addStretch(1)

    header_layout.addLayout(title_row)
    header_layout.addLayout(badge_row)
    return header


def build_fixture_preview_card(page, fixture: dict) -> QWidget:
    preview_card = create_titled_section(page._t('tool_library.section.preview', 'Preview'))
    preview_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    preview_layout = QVBoxLayout(preview_card)
    preview_layout.setSpacing(10)
    preview_layout.setContentsMargins(6, 4, 6, 6)

    diagram = QWidget()
    diagram.setObjectName('detailPreviewGradientHost')
    diagram.setAttribute(Qt.WA_StyledBackground, True)
    diagram.setStyleSheet(
        'QWidget#detailPreviewGradientHost {'
        '  background-color: #d6d9de;'
        '  border: none;'
        '  border-radius: 6px;'
        '}'
    )
    diagram.setMinimumHeight(300)
    diagram.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    diagram_layout = QVBoxLayout(diagram)
    diagram_layout.setContentsMargins(6, 6, 6, 6)
    diagram_layout.setSpacing(0)

    viewer = page._detail_preview_widget
    if viewer is None:
        viewer = StlPreviewWidget()
        page._detail_preview_widget = viewer
    if viewer.parent() is not diagram:
        viewer.setParent(diagram)
    viewer.setStyleSheet('background: transparent; border: none;')
    viewer.set_status_overlay_enabled(False)
    viewer.set_control_hint_text(
        page._t(
            'tool_editor.hint.rotate_pan_zoom',
            'Rotate: left mouse | Pan: right mouse | Zoom: mouse wheel',
        )
    )

    model_key = page._preview_model_key(fixture)
    if page._detail_preview_model_key != model_key:
        loaded = page._load_preview_content(viewer, fixture, label=fixture_preview_label(fixture, page._t))
        if loaded:
            page._detail_preview_model_key = model_key
        else:
            page._detail_preview_model_key = None
    else:
        loaded = True

    if loaded:
        apply_fixture_preview_transform(viewer, fixture)
        overlays = fixture_preview_measurement_overlays(fixture)
        viewer.set_measurement_overlays(overlays)
        viewer.set_measurements_visible(bool(overlays))
        diagram_layout.addWidget(viewer, 1)
        viewer.show()
    else:
        viewer.clear()
        viewer.hide()
        stl_path = fixture_preview_stl_path(fixture)
        placeholder = QLabel(
            page._t('tool_library.preview.invalid_data', 'No valid 3D model data found.')
            if stl_path
            else page._t('tool_library.preview.none_assigned', 'No 3D model assigned.')
        )
        placeholder.setProperty('detailHint', True)
        placeholder.setWordWrap(True)
        placeholder.setAlignment(Qt.AlignCenter)
        diagram_layout.addStretch(1)
        diagram_layout.addWidget(placeholder)
        diagram_layout.addStretch(1)

    preview_layout.addWidget(diagram, 1)
    return preview_card


def _clear_details(page) -> None:
    if page._detail_preview_widget is not None:
        page._detail_preview_widget.hide()
        page._detail_preview_widget.setParent(None)
    while page.detail_layout.count():
        item = page.detail_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def _split_used_in_works(value: str) -> list[str]:
    return [part.strip() for part in str(value or '').split('|') if part.strip()]


def _lookup_setup_db_used_in_works(fixture_id: str) -> str:
    if not fixture_id:
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
            (fixture_id, fixture_id),
        ).fetchall()
        conn.close()
        return ' | '.join(row[0] for row in rows if row and row[0])
    except Exception:
        return ''


__all__ = [
    'build_empty_details_card',
    'build_fixture_detail_header',
    'build_fixture_preview_card',
    'populate_detail_panel',
]

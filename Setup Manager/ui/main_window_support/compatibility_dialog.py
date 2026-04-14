from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from shared.ui.helpers.editor_helpers import create_titled_section, setup_editor_dialog
from ui.widgets.common import add_shadow


def show_compatibility_report_dialog(
    window,
    *,
    title: str,
    summary: str,
    informative: str,
    details: str,
    has_issues: bool,
) -> None:
    dialog = QDialog(window)
    setup_editor_dialog(dialog)
    dialog.setObjectName("compatibilityReportDialog")
    dialog.setProperty("preferencesDialog", True)
    dialog.setAttribute(Qt.WA_StyledBackground, True)
    dialog.setStyleSheet(
        "QDialog#compatibilityReportDialog {"
        " background-color: #ffffff;"
        "}"
    )
    dialog.setModal(True)
    dialog.setWindowTitle(title)
    dialog.resize(700, 560)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(14, 14, 14, 14)
    root.setSpacing(12)

    summary_group = create_titled_section(window._t("preferences.database.compatibility.summary_title", "Summary"))
    summary_layout = QVBoxLayout(summary_group)
    summary_layout.setContentsMargins(12, 12, 12, 12)
    summary_layout.setSpacing(8)

    status_label = QLabel(
        window._t(
            "preferences.database.compatibility.status_warning",
            "Compatibility issues were found.",
        )
        if has_issues
        else window._t(
            "preferences.database.compatibility.status_ok",
            "All checked work references resolved successfully.",
        )
    )
    status_label.setProperty("detailHint", True)
    status_label.setWordWrap(True)
    summary_layout.addWidget(status_label)

    summary_text = QPlainTextEdit()
    summary_text.setReadOnly(True)
    summary_text.setPlainText(summary)
    summary_text.setMinimumHeight(180)
    summary_text.setStyleSheet("QPlainTextEdit { background: #ffffff; }")
    summary_layout.addWidget(summary_text)
    root.addWidget(summary_group)

    db_group = create_titled_section(window._t("preferences.database.compatibility.paths_title", "Database Paths"))
    db_layout = QVBoxLayout(db_group)
    db_layout.setContentsMargins(12, 12, 12, 12)
    db_layout.setSpacing(8)
    info_text = QPlainTextEdit()
    info_text.setReadOnly(True)
    info_text.setPlainText(informative)
    info_text.setMinimumHeight(120)
    info_text.setStyleSheet("QPlainTextEdit { background: #ffffff; }")
    db_layout.addWidget(info_text)
    root.addWidget(db_group)

    if details:
        details_group = create_titled_section(window._t("preferences.database.compatibility.details_title", "Issue Details"))
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(12, 12, 12, 12)
        details_layout.setSpacing(8)
        details_text = QPlainTextEdit()
        details_text.setReadOnly(True)
        details_text.setPlainText(details)
        details_text.setMinimumHeight(140)
        details_text.setStyleSheet("QPlainTextEdit { background: #ffffff; }")
        details_layout.addWidget(details_text)
        root.addWidget(details_group, 1)

    button_row = QHBoxLayout()
    button_row.addStretch(1)
    ok_btn = QPushButton(window._t("common.ok", "OK"))
    ok_btn.setProperty("panelActionButton", True)
    ok_btn.setProperty("primaryAction", True)
    add_shadow(ok_btn)
    ok_btn.clicked.connect(dialog.accept)
    button_row.addWidget(ok_btn)
    root.addLayout(button_row)

    dialog.exec()

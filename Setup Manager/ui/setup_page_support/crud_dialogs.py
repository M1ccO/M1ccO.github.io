from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from ui.widgets.common import add_shadow, repolish_widget


def confirm_delete_work(page, work_id: str) -> bool:
    answer = QMessageBox.question(
        page,
        page._t("setup_page.message.delete_work_title", "Delete work"),
        page._t("setup_page.message.delete_work_prompt", "Delete work '{work_id}'?", work_id=work_id),
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return answer == QMessageBox.Yes


def ask_delete_logbook_entries(page, work_id: str, logbook_count: int):
    box = QMessageBox(page)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(page._t("setup_page.message.delete_logbook_title", "Delete logbook entries?"))
    box.setText(
        page._t(
            "setup_page.message.delete_logbook_body",
            "Work '{work_id}' has {count} logbook entr{plural}.\n\nDo you also want to delete those logbook entries?",
            work_id=work_id,
            count=logbook_count,
            plural="y" if logbook_count == 1 else "ies",
        )
    )
    yes_btn = box.addButton(
        page._t("setup_page.message.delete_logbook_yes", "Delete entries"),
        QMessageBox.DestructiveRole,
    )
    keep_btn = box.addButton(
        page._t("setup_page.message.delete_logbook_keep", "Keep entries"),
        QMessageBox.AcceptRole,
    )
    cancel_btn = box.addButton(
        page._t("common.cancel", "Cancel"),
        QMessageBox.RejectRole,
    )

    for btn, primary, danger in (
        (keep_btn, True, False),
        (yes_btn, False, True),
        (cancel_btn, False, False),
    ):
        btn.setProperty("panelActionButton", True)
        btn.setProperty("primaryAction", bool(primary))
        btn.setProperty("secondaryAction", not bool(primary) and not bool(danger))
        btn.setProperty("dangerAction", bool(danger))
        add_shadow(btn)
        repolish_widget(btn)

    box.setDefaultButton(keep_btn)
    box.setEscapeButton(cancel_btn)
    box.exec()

    if box.clickedButton() is cancel_btn or box.clickedButton() is None:
        return None
    return box.clickedButton() is yes_btn

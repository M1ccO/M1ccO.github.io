from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QMessageBox

from config import TEMP_DIR


def view_setup_card(page) -> None:
    work_id = page._selected_work_id()
    if not work_id:
        QMessageBox.information(
            page,
            page._t("setup_page.message.no_work_title", "No work"),
            page._t("setup_page.message.select_work_first", "Select a work first."),
        )
        return

    work = page.work_service.get_work(work_id)
    if not work:
        QMessageBox.warning(
            page,
            page._t("setup_page.message.missing_title", "Missing"),
            page._t("setup_page.message.work_no_longer_exists", "Work no longer exists."),
        )
        return

    entries = page.logbook_service.list_entries(filters={"work_id": work_id})
    entry = entries[0] if entries else None
    if not entry:
        answer = QMessageBox.question(
            page,
            page._t("setup_page.message.no_logbook_entry_title", "No logbook entry"),
            page._t(
                "setup_page.message.no_logbook_entry_body",
                "No logbook entry exists for this work. Continue printing without run data?",
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

    try:
        preview_dir = TEMP_DIR / "setup_cards"
        preview_dir.mkdir(parents=True, exist_ok=True)
        date_stamp = datetime.now().strftime('%d-%m-%Y')
        output_path = preview_dir / f"setup-card__{date_stamp}.pdf"
        page.print_service.generate_setup_card(
            work,
            entry,
            output_path,
            machine_profile_key=page.work_service.get_machine_profile_key(),
        )
        if not page.draw_service.open_drawing(output_path):
            QMessageBox.warning(
                page,
                page._t("setup_page.message.open_failed", "Open failed"),
                page._t(
                    "setup_page.message.setup_card_created_not_opened",
                    "Setup card created but could not be opened:\n{path}",
                    path=output_path,
                ),
            )
    except Exception as exc:
        QMessageBox.critical(page, page._t("setup_page.message.view_failed", "View failed"), str(exc))

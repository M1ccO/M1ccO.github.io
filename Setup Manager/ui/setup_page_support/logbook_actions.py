from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QMessageBox

from config import USER_DATA_DIR
from ui.setup_page_support.log_entry_dialog import LogEntryDialog


def add_log_entry(page) -> None:
    work_id = page._selected_work_id()
    if not work_id:
        QMessageBox.information(
            page,
            page._t("setup_page.message.no_work_title", "No work"),
            page._t("setup_page.message.select_work_first", "Select a work first."),
        )
        return

    try:
        # Serial generation failure should not block entry creation.
        next_serial = page.logbook_service.generate_next_serial(work_id, date.today().year)
    except Exception:
        next_serial = ""

    dialog = LogEntryDialog(work_id, next_serial, page, translate=page._t)
    if dialog.exec() != QDialog.Accepted:
        return

    payload = dialog.get_data()
    try:
        # Persist first; all preview/print behavior happens only after successful save.
        created_entry = page.logbook_service.add_entry(
            work_id=work_id,
            order_number=payload["order_number"],
            quantity=payload["quantity"],
            notes=payload["notes"],
            custom_serial=payload["custom_serial"],
            entry_date=payload["entry_date"],
        )
        page.refresh_works()
        page.logbookChanged.emit()
    except Exception as exc:
        QMessageBox.critical(page, page._t("setup_page.message.save_failed", "Save failed"), str(exc))
        return

    handle_logbook_entry_post_save(page, work_id, created_entry, dialog.should_print_card())


def handle_logbook_entry_post_save(page, work_id: str, created_entry: dict, should_print_card: bool) -> None:
    if should_print_card:
        try:
            work = page.work_service.get_work(work_id)
            if not work:
                QMessageBox.warning(
                    page,
                    page._t("setup_page.message.print_card_title", "Lava card"),
                    page._t(
                        "setup_page.message.entry_saved_missing_work",
                        "Entry saved, but the related work record could not be loaded.",
                    ),
                )
                QMessageBox.information(
                    page,
                    page._t("setup_page.message.saved_title", "Saved"),
                    page._t("setup_page.message.logbook_created", "Logbook entry created."),
                )
                return
            preview_dir = USER_DATA_DIR / "setup_cards"
            preview_dir.mkdir(parents=True, exist_ok=True)
            date_stamp = datetime.now().strftime('%d-%m-%Y')
            output_path = preview_dir / f"lava-kortti__{date_stamp}.pdf"
            page.print_service.generate_logbook_entry_card(work, created_entry, output_path)
            saved_notice = QMessageBox(page)
            saved_notice.setIcon(QMessageBox.Information)
            saved_notice.setWindowTitle(page._t("setup_page.message.saved_title", "Saved"))
            saved_notice.setText(
                page._t("setup_page.message.logbook_created_opening", "Logbook entry created. Opening card preview...")
            )
            saved_notice.setStandardButtons(QMessageBox.NoButton)
            saved_notice.setModal(False)
            saved_notice.show()

            def _open_card_after_delay():
                # Delay keeps UX smooth and avoids racing immediate viewer launch
                # against notice rendering/cleanup.
                try:
                    saved_notice.close()
                    saved_notice.deleteLater()
                except Exception:
                    pass
                if not page.draw_service.open_drawing(output_path):
                    QMessageBox.warning(
                        page,
                        page._t("setup_page.message.open_failed", "Open failed"),
                        page._t(
                            "setup_page.message.card_created_not_opened",
                            "Lava card created but could not be opened:\n{path}",
                            path=output_path,
                        ),
                    )

            notice_timer = QTimer(saved_notice)
            notice_timer.setSingleShot(True)
            notice_timer.timeout.connect(_open_card_after_delay)
            notice_timer.start(700)
        except Exception as exc:
            QMessageBox.warning(
                page,
                page._t("setup_page.message.print_card_title", "Lava card"),
                page._t(
                    "setup_page.message.entry_saved_card_generation_failed",
                    "Entry saved, but Lava card generation failed:\n{error}",
                    error=exc,
                ),
            )
            QMessageBox.information(
                page,
                page._t("setup_page.message.saved_title", "Saved"),
                page._t("setup_page.message.logbook_created", "Logbook entry created."),
            )
        return

    QMessageBox.information(
        page,
        page._t("setup_page.message.saved_title", "Saved"),
        page._t("setup_page.message.logbook_created", "Logbook entry created."),
    )

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QSignalBlocker, QTimer, Qt
from PySide6.QtGui import QStandardItem

from ui.setup_catalog_delegate import ROLE_WORK_DATA, ROLE_WORK_ID
from ui.setup_page_support.library_context import collect_library_filter_ids, emit_library_launch_context


def toggle_search(page) -> None:
    show = page.search_toggle_btn.isChecked()
    page._search_visible = show
    page.search_input.setVisible(show)
    page.search_toggle_btn.setIcon(page.close_icon if show else page.search_icon)
    if show:
        page.search_input.setFocus()
        return
    page.search_input.clear()
    page.refresh_works()


def sync_work_row_widths(page) -> None:
    if not hasattr(page, "work_list"):
        return
    page.work_list.doItemsLayout()
    page.work_list.viewport().update()


def sync_work_row_modes(page) -> None:
    compact = False
    page._work_delegate.set_compact_mode(compact)
    sync_work_row_widths(page)
    QTimer.singleShot(0, lambda: sync_work_row_widths(page))


def handle_event_filter(page, obj, event):
    if obj is page.work_list.viewport() and event.type() == QEvent.Resize:
        # One immediate layout pass + one queued pass keeps delegate widths correct
        # when Qt emits rapid size changes.
        sync_work_row_widths(page)
        QTimer.singleShot(0, lambda: sync_work_row_widths(page))
    if obj in (page.work_list, page.work_list.viewport()):
        if event.type() == QEvent.MouseButtonPress:
            page._last_mouse_button = event.button()
            if not page.work_list.indexAt(event.pos()).isValid():
                page._clear_selection()


def handle_item_double_clicked(page, item) -> None:
    work_id = item.data(ROLE_WORK_ID) if item and item.isValid() else None
    if not work_id:
        return

    work = page.work_service.get_work(work_id)
    if not work:
        return

    tool_ids, jaw_ids = collect_library_filter_ids(work)
    # Right-click + double-click opens Jaws view; default double-click opens Tools view.
    if page._last_mouse_button == Qt.RightButton:
        page.openLibraryWithModuleRequested.emit(tool_ids, jaw_ids, "jaws")
    else:
        page.openLibraryWithModuleRequested.emit(tool_ids, jaw_ids, "tools")

    page._last_mouse_button = None


def apply_localization(page, translate=None) -> None:
    if translate is not None:
        page._translate = translate
    page._row_headers = {
        "work_id": page._t("setup_page.row.work_id", "Work ID"),
        "drawing": page._t("setup_page.row.drawing", "Drawing"),
        "description": page._t("setup_page.row.description", "Description"),
        "last_run": page._t("setup_page.row.last_run", "Last run"),
    }
    if hasattr(page, "_work_delegate"):
        page._work_delegate.set_headers(page._row_headers)
    page.search_toggle_btn.setToolTip(page._t("setup_page.search_toggle_tip", "Show/hide search"))
    page.search_input.setPlaceholderText(page._t("setup_page.search_placeholder", "Search works..."))
    page.make_logbook_entry_btn.setText(page._t("setup_page.make_logbook_entry", "Make logbook entry"))
    page.new_btn.setText(page._t("setup_page.new_work", "New Work"))
    page.edit_btn.setText(page._t("setup_page.edit_work", "Edit Work"))
    page.delete_btn.setText(page._t("setup_page.delete_work", "Delete Work"))
    page.copy_btn.setText(page._t("setup_page.duplicate", "Duplicate"))
    page.print_btn.setText(page._t("setup_page.view_setup_card", "View Setup Card"))
    page._update_selection_count_label()
    page.refresh_works()


def refresh_works(page) -> None:
    search = page.search_input.text().strip()
    works = page.work_service.list_works(search)
    page.latest_entries_by_work = page.logbook_service.latest_entries_by_work_ids(
        [work.get("work_id") for work in works]
    )
    previous_id = page.current_work_id
    restored = False

    # Rebuilding the model can fire selection signals; block temporarily to avoid
    # transient context churn during refresh.
    blocker = QSignalBlocker(page.work_list.selectionModel())
    page._work_model.clear()
    restored_index = QModelIndex()
    for work in works:
        work_id = work.get("work_id", "")
        drawing_id = work.get("drawing_id", "")
        description = (work.get("description") or "").strip()
        latest_entry = page.latest_entries_by_work.get(work_id)
        latest_text = ""
        if latest_entry:
            latest_text = (
                f"{latest_entry.get('date', '')}  |  {latest_entry.get('batch_serial', '')}"
            )
        row_data = {
            "work_id": work_id,
            "drawing_id": drawing_id,
            "description": description,
            "latest_text": latest_text or page._t("setup_page.row.no_runs", "No runs yet"),
        }
        item = QStandardItem()
        item.setData(work_id, ROLE_WORK_ID)
        item.setData(row_data, ROLE_WORK_DATA)
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        page._work_model.appendRow(item)

        if previous_id and work_id == previous_id:
            restored_index = page._work_model.index(page._work_model.rowCount() - 1, 0)
            restored = True

    if not restored:
        page.current_work_id = None
        page.work_list.selectionModel().clearSelection()
        page.work_list.setCurrentIndex(QModelIndex())

    del blocker

    page._sync_work_row_widths()
    QTimer.singleShot(0, page._sync_work_row_widths)

    if restored:
        # Preserve context when the previous selection still exists after filtering/refresh.
        page.current_work_id = previous_id
        page.work_list.setCurrentIndex(restored_index)
        page.work_list.scrollTo(restored_index)
        page._set_selected_card(page.current_work_id)
        selected_work = page.work_service.get_work(page.current_work_id)
        emit_library_launch_context(page, selected_work)
    else:
        page._set_selected_card(None)
        emit_library_launch_context(page, None)

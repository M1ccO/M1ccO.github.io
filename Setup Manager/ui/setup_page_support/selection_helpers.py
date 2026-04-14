from __future__ import annotations

from PySide6.QtCore import QModelIndex

from ui.setup_catalog_delegate import ROLE_WORK_ID
from ui.setup_page_support.library_context import emit_library_launch_context


def selected_work_ids(page) -> list[str]:
    model = page.work_list.selectionModel()
    if model is None:
        return []
    # Keep list order stable so downstream batch operations are deterministic.
    indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
    work_ids: list[str] = []
    for index in indexes:
        work_id = (index.data(ROLE_WORK_ID) or "").strip()
        if work_id and work_id not in work_ids:
            work_ids.append(work_id)
    return work_ids


def update_selection_count_label(page) -> None:
    count = len(selected_work_ids(page))
    if count > 1:
        page.selection_count_label.setText(
            page._t("setup_page.selection.count", "{count} selected", count=count)
        )
        page.selection_count_label.show()
        return
    page.selection_count_label.hide()


def set_current_item_by_work_id(page, work_id):
    for row in range(page._work_model.rowCount()):
        index = page._work_model.index(row, 0)
        if index.data(ROLE_WORK_ID) == work_id:
            page.work_list.setCurrentIndex(index)
            page.work_list.scrollTo(index)
            return index
    return QModelIndex()


def clear_selection(page) -> None:
    page.work_list.selectionModel().clearSelection()
    page.work_list.setCurrentIndex(QModelIndex())
    page.current_work_id = None
    update_selection_count_label(page)
    page._set_selected_card(None)
    # Clearing selection must also clear launch context so sidebar actions return
    # to unfiltered mode immediately.
    emit_library_launch_context(page, None)


def on_selection_changed(page, current) -> None:
    work_id = current.data(ROLE_WORK_ID) if current and current.isValid() else None
    page.current_work_id = work_id
    update_selection_count_label(page)
    page._set_selected_card(work_id)
    selected_work = page.work_service.get_work(work_id) if work_id else None
    # Selection changes are the single source of truth for launch-card context.
    emit_library_launch_context(page, selected_work)

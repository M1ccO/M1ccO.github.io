from pathlib import Path
import tempfile
from datetime import datetime
from datetime import date
from typing import Callable

from PySide6.QtCore import QDate, QEvent, QSignalBlocker, Qt, Signal, QSize, QTimer, QModelIndex
from PySide6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from config import (
    USER_DATA_DIR,
    TEMP_DIR,
)
from ui.widgets.common import AutoShrinkLabel, add_shadow, repolish_widget, styled_list_item_height
from ui.setup_catalog_delegate import ROLE_WORK_DATA, ROLE_WORK_ID, SetupCatalogDelegate
from ui.setup_page_support import (
    build_library_launch_context_payload,
    collect_library_filter_ids,
    LogEntryDialog,
)
from ui.work_editor_dialog import WorkEditorDialog
try:
    from shared.ui.helpers.editor_helpers import (
        apply_shared_checkbox_style,
        ask_multi_edit_mode,
        create_titled_section,
        setup_editor_dialog,
    )
except ModuleNotFoundError:
    from editor_helpers import (
        apply_shared_checkbox_style,
        ask_multi_edit_mode,
        create_titled_section,
        setup_editor_dialog,
    )

from ui.icon_helpers import toolbar_icon_with_svg_render_fallback as _toolbar_icon_with_svg_render_fallback
from shared.data.backup_helpers import create_db_backup, prune_backups


class SetupPage(QWidget):
    logbookChanged = Signal()
    openLibraryMasterFilterRequested = Signal(object, object)
    openLibraryWithModuleRequested = Signal(object, object, str)  # tool_ids, jaw_ids, module
    libraryLaunchContextChanged = Signal(object)

    def __init__(
        self,
        work_service,
        logbook_service,
        draw_service,
        print_service,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.work_service = work_service
        self.logbook_service = logbook_service
        self.draw_service = draw_service
        self.print_service = print_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")

        self.drawings_enabled = True  # updated by main_window from preferences
        self.current_work_id = None
        self.latest_entries_by_work = {}
        self._search_visible = False
        self._min_list_panel_width = 340
        self._last_mouse_button = None  # Track mouse button for double-click handling
        self._row_headers = {
            "work_id": self._t("setup_page.row.work_id", "Work ID"),
            "drawing": self._t("setup_page.row.drawing", "Drawing"),
            "description": self._t("setup_page.row.description", "Description"),
            "last_run": self._t("setup_page.row.last_run", "Last run"),
        }
        self._tool_db_mtime = self._safe_mtime(self.draw_service.tool_db_path)
        self._jaw_db_mtime = self._safe_mtime(self.draw_service.jaw_db_path)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        controls_frame = QFrame()
        controls_frame.setProperty("topBarContainer", True)
        controls = QHBoxLayout(controls_frame)
        controls.setContentsMargins(8, 6, 8, 6)
        controls.setSpacing(8)

        self.search_icon = _toolbar_icon_with_svg_render_fallback("search_icon", 28)
        self.close_icon = _toolbar_icon_with_svg_render_fallback("close_icon", 28)

        self.search_toggle_btn = QToolButton()
        self.search_toggle_btn.setProperty("topBarIconButton", True)
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.setToolTip(self._t("setup_page.search_toggle_tip", "Show/hide search"))
        self.search_toggle_btn.setIcon(self.search_icon)
        self.search_toggle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.search_toggle_btn.setIconSize(QSize(28, 28))
        self.search_toggle_btn.setFixedSize(36, 36)
        self.search_toggle_btn.setAutoRaise(True)
        self.search_toggle_btn.clicked.connect(self._toggle_search)
        controls.addWidget(self.search_toggle_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self._t("setup_page.search_placeholder", "Search works..."))
        self.search_input.textChanged.connect(self.refresh_works)
        self.search_input.setVisible(False)
        self.search_input.setFixedWidth(220)
        controls.addWidget(self.search_input)

        self.make_logbook_entry_btn = QPushButton(self._t("setup_page.make_logbook_entry", "Make logbook entry"))
        self.make_logbook_entry_btn.setProperty("panelActionButton", True)
        self.make_logbook_entry_btn.setProperty("secondaryAction", True)
        self.make_logbook_entry_btn.setFixedHeight(30)
        self.make_logbook_entry_btn.setFixedWidth(260)
        self.make_logbook_entry_btn.clicked.connect(self.add_log_entry)

        self.new_btn = QPushButton(self._t("setup_page.new_work", "New Work"))
        self.edit_btn = QPushButton(self._t("setup_page.edit_work", "Edit Work"))
        self.delete_btn = QPushButton(self._t("setup_page.delete_work", "Delete Work"))
        self.copy_btn = QPushButton(self._t("setup_page.duplicate", "Duplicate"))
        self.print_btn = QPushButton(self._t("setup_page.view_setup_card", "View Setup Card"))
        self.print_btn.setProperty("panelActionButton", True)
        self.print_btn.setProperty("secondaryAction", True)
        self.print_btn.setFixedHeight(30)
        self.print_btn.setFixedWidth(260)

        self.new_btn.clicked.connect(self.create_work)
        self.edit_btn.clicked.connect(self.edit_work)
        self.delete_btn.clicked.connect(self.delete_work)
        self.copy_btn.clicked.connect(self.duplicate_work)
        self.print_btn.clicked.connect(self.view_setup_card)

        controls.addStretch(1)
        controls.addWidget(self.print_btn)
        controls.addWidget(self.make_logbook_entry_btn)
        root.addWidget(controls_frame)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("setupWorkSplitter")
        splitter.setHandleWidth(1)
        self.work_list = QListView()
        self.work_list.setObjectName("setupWorkList")
        self.work_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.work_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.work_list.setSpacing(0)
        self.work_list.setSelectionMode(QListView.ExtendedSelection)
        self.work_list.setMouseTracking(True)
        self.work_list.setUniformItemSizes(True)
        self.work_list.setStyleSheet(
            "QListView#setupWorkList { border: none; outline: none; padding: 8px; }"
            " QListView#setupWorkList::item { background: transparent; border: none; }"
        )
        self._work_model = QStandardItemModel(self)
        self._work_delegate = SetupCatalogDelegate(
            self.work_list,
            headers=self._row_headers,
            compact_mode=False,
        )
        self.work_list.setModel(self._work_model)
        self.work_list.setItemDelegate(self._work_delegate)
        self.work_list.selectionModel().currentChanged.connect(self._on_selection_changed)
        self.work_list.selectionModel().selectionChanged.connect(self._on_multi_selection_changed)
        self.work_list.doubleClicked.connect(self._on_item_double_clicked)
        self.work_list.installEventFilter(self)
        self.work_list.viewport().installEventFilter(self)

        list_shell = QFrame()
        list_shell.setObjectName("setupWorkShell")
        list_shell.setProperty("catalogShell", True)
        list_shell_layout = QVBoxLayout(list_shell)
        list_shell_layout.setContentsMargins(0, 0, 8, 0)
        list_shell_layout.setSpacing(0)
        list_shell_layout.addWidget(self.work_list)

        list_shell_container = QWidget()
        list_shell_container_layout = QVBoxLayout(list_shell_container)
        list_shell_container_layout.setContentsMargins(0, 0, 0, 0)
        list_shell_container_layout.setSpacing(0)
        list_shell_container_layout.addWidget(list_shell)
        list_shell_container.setMinimumWidth(self._min_list_panel_width)
        splitter.addWidget(list_shell_container)

        splitter.setChildrenCollapsible(False)
        splitter.setCollapsible(0, False)
        root.addWidget(splitter, 1)

        button_bar = QFrame()
        button_bar.setProperty("bottomBar", True)
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(10, 10, 10, 6)
        button_layout.setSpacing(8)
        button_layout.addStretch(1)

        self.new_btn.setProperty("panelActionButton", True)
        self.new_btn.setProperty("primaryAction", True)
        self.edit_btn.setProperty("panelActionButton", True)
        self.copy_btn.setProperty("panelActionButton", True)
        self.delete_btn.setProperty("panelActionButton", True)
        self.delete_btn.setProperty("dangerAction", True)

        self.selection_count_label = QLabel("")
        self.selection_count_label.setProperty("detailHint", True)
        self.selection_count_label.setStyleSheet("background: transparent; border: none;")
        self.selection_count_label.hide()
        button_layout.addWidget(self.selection_count_label, 0, Qt.AlignBottom)
        button_layout.addWidget(self.new_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.edit_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.delete_btn, 0, Qt.AlignBottom)
        button_layout.addWidget(self.copy_btn, 0, Qt.AlignBottom)
        root.addWidget(button_bar)

        self.refresh_works()

        self._external_refs_timer = QTimer(self)
        self._external_refs_timer.setInterval(1500)
        self._external_refs_timer.timeout.connect(self._on_external_references_maybe_changed)
        self._external_refs_timer.start()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _safe_mtime(path) -> float | None:
        try:
            p = Path(path)
            return p.stat().st_mtime if p.exists() else None
        except Exception:
            return None

    def _on_external_references_maybe_changed(self):
        tool_mtime = self._safe_mtime(self.draw_service.tool_db_path)
        jaw_mtime = self._safe_mtime(self.draw_service.jaw_db_path)
        changed = (tool_mtime != self._tool_db_mtime) or (jaw_mtime != self._jaw_db_mtime)
        if not changed:
            return

        self._tool_db_mtime = tool_mtime
        self._jaw_db_mtime = jaw_mtime

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None):
        if translate is not None:
            self._translate = translate
        self._row_headers = {
            "work_id": self._t("setup_page.row.work_id", "Work ID"),
            "drawing": self._t("setup_page.row.drawing", "Drawing"),
            "description": self._t("setup_page.row.description", "Description"),
            "last_run": self._t("setup_page.row.last_run", "Last run"),
        }
        if hasattr(self, "_work_delegate"):
            self._work_delegate.set_headers(self._row_headers)
        self.search_toggle_btn.setToolTip(self._t("setup_page.search_toggle_tip", "Show/hide search"))
        self.search_input.setPlaceholderText(self._t("setup_page.search_placeholder", "Search works..."))
        self.make_logbook_entry_btn.setText(self._t("setup_page.make_logbook_entry", "Make logbook entry"))
        self.new_btn.setText(self._t("setup_page.new_work", "New Work"))
        self.edit_btn.setText(self._t("setup_page.edit_work", "Edit Work"))
        self.delete_btn.setText(self._t("setup_page.delete_work", "Delete Work"))
        self.copy_btn.setText(self._t("setup_page.duplicate", "Duplicate"))
        self.print_btn.setText(self._t("setup_page.view_setup_card", "View Setup Card"))
        self._update_selection_count_label()
        self.refresh_works()

    def refresh_works(self):
        search = self.search_input.text().strip()
        works = self.work_service.list_works(search)
        self.latest_entries_by_work = self.logbook_service.latest_entries_by_work_ids(
            [work.get("work_id") for work in works]
        )
        previous_id = self.current_work_id
        restored = False

        blocker = QSignalBlocker(self.work_list.selectionModel())
        self._work_model.clear()
        restored_index = QModelIndex()
        for work in works:
            work_id = work.get("work_id", "")
            drawing_id = work.get("drawing_id", "")
            description = (work.get("description") or "").strip()
            latest_entry = self.latest_entries_by_work.get(work_id)
            latest_text = ""
            if latest_entry:
                latest_text = (
                    f"{latest_entry.get('date', '')}  |  {latest_entry.get('batch_serial', '')}"
                )
            row_data = {
                "work_id": work_id,
                "drawing_id": drawing_id,
                "description": description,
                "latest_text": latest_text or self._t("setup_page.row.no_runs", "No runs yet"),
            }
            item = QStandardItem()
            item.setData(work_id, ROLE_WORK_ID)
            item.setData(row_data, ROLE_WORK_DATA)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._work_model.appendRow(item)

            if previous_id and work_id == previous_id:
                restored_index = self._work_model.index(self._work_model.rowCount() - 1, 0)
                restored = True

        if not restored:
            self.current_work_id = None
            self.work_list.selectionModel().clearSelection()
            self.work_list.setCurrentIndex(QModelIndex())

        del blocker

        self._sync_work_row_widths()
        QTimer.singleShot(0, self._sync_work_row_widths)

        if restored:
            self.current_work_id = previous_id
            self.work_list.setCurrentIndex(restored_index)
            self.work_list.scrollTo(restored_index)
            self._set_selected_card(self.current_work_id)
            selected_work = self.work_service.get_work(self.current_work_id)
            self._emit_library_launch_context(selected_work)
        else:
            self._set_selected_card(None)
            self._emit_library_launch_context(None)

    def _selected_work_id(self):
        index = self.work_list.currentIndex()
        return index.data(ROLE_WORK_ID) if index.isValid() else None

    def _selected_work_ids(self) -> list[str]:
        model = self.work_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        work_ids: list[str] = []
        for index in indexes:
            work_id = (index.data(ROLE_WORK_ID) or "").strip()
            if work_id and work_id not in work_ids:
                work_ids.append(work_id)
        return work_ids

    def _on_multi_selection_changed(self, _selected, _deselected):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        count = len(self._selected_work_ids())
        if count > 1:
            self.selection_count_label.setText(
                self._t("setup_page.selection.count", "{count} selected", count=count)
            )
            self.selection_count_label.show()
            return
        self.selection_count_label.hide()

    def _batch_edit_works(self, work_ids: list[str]):
        from ui.setup_page_support.batch_actions import batch_edit_works
        batch_edit_works(self, work_ids)

    def _group_edit_works(self, work_ids: list[str]):
        from ui.setup_page_support.batch_actions import group_edit_works
        group_edit_works(self, work_ids)

    def _toggle_search(self):
        show = self.search_toggle_btn.isChecked()
        self._search_visible = show
        self.search_input.setVisible(show)
        self.search_toggle_btn.setIcon(self.close_icon if show else self.search_icon)
        if show:
            self.search_input.setFocus()
            return
        # Match Tool Library behavior: closing search clears the filter.
        self.search_input.clear()
        self.refresh_works()

    def _set_current_item_by_work_id(self, work_id):
        for row in range(self._work_model.rowCount()):
            index = self._work_model.index(row, 0)
            if index.data(ROLE_WORK_ID) == work_id:
                self.work_list.setCurrentIndex(index)
                self.work_list.scrollTo(index)
                return index
        return QModelIndex()

    def eventFilter(self, obj, event):
        if obj is self.work_list.viewport() and event.type() == QEvent.Resize:
            self._sync_work_row_widths()
            QTimer.singleShot(0, self._sync_work_row_widths)
        if obj in (self.work_list, self.work_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                # Track which mouse button was pressed for double-click handling
                self._last_mouse_button = event.button()
                if not self.work_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _clear_selection(self):
        self.work_list.selectionModel().clearSelection()
        self.work_list.setCurrentIndex(QModelIndex())
        self.current_work_id = None
        self._update_selection_count_label()
        self._set_selected_card(None)
        self._update_open_library_viewer_visibility(None)
        self._emit_library_launch_context(None)

    def _on_selection_changed(self, current, _previous):
        work_id = current.data(ROLE_WORK_ID) if current and current.isValid() else None
        self.current_work_id = work_id
        self._update_selection_count_label()
        self._set_selected_card(work_id)
        selected_work = self.work_service.get_work(work_id) if work_id else None
        self._update_open_library_viewer_visibility(selected_work)
        self._emit_library_launch_context(selected_work)

    def _on_item_double_clicked(self, item):
        """Handle double-click on setup card to open filtered libraries."""
        work_id = item.data(ROLE_WORK_ID) if item and item.isValid() else None
        if not work_id:
            return
        
        work = self.work_service.get_work(work_id)
        if not work:
            return
        
        tool_ids, jaw_ids = self._collect_library_filter_ids(work)
        
        # Determine which button was pressed based on last recorded mouse button
        if self._last_mouse_button == Qt.RightButton:
            # Right double-click: open Jaws Library
            self.openLibraryWithModuleRequested.emit(tool_ids, jaw_ids, "jaws")
        else:
            # Left double-click (default): open Tools Library
            self.openLibraryWithModuleRequested.emit(tool_ids, jaw_ids, "tools")
        
        self._last_mouse_button = None

    def _set_selected_card(self, work_id):
        _ = work_id
        self.work_list.viewport().update()

    def _sync_work_row_modes(self):
        compact = False
        self._work_delegate.set_compact_mode(compact)
        self._sync_work_row_widths()
        QTimer.singleShot(0, self._sync_work_row_widths)

    def _sync_work_row_widths(self):
        if not hasattr(self, "work_list"):
            return
        self.work_list.doItemsLayout()
        self.work_list.viewport().update()

    def _update_open_library_viewer_visibility(self, work=None):
        tool_ids, jaw_ids = collect_library_filter_ids(work)
        return bool(tool_ids or jaw_ids)

    def _collect_library_filter_ids(self, work):
        return collect_library_filter_ids(work)

    def _emit_library_launch_context(self, work=None):
        self.libraryLaunchContextChanged.emit(build_library_launch_context_payload(work))

    def _create_db_backup(self, tag: str):
        backup_path = create_db_backup(Path(self.work_service.db.path), tag)
        return backup_path

    def _open_library_viewer(self):
        if not self.current_work_id:
            return
        work = self.work_service.get_work(self.current_work_id)
        if not work:
            return
        tool_ids, jaw_ids = self._collect_library_filter_ids(work)

        self.openLibraryMasterFilterRequested.emit(tool_ids, jaw_ids)

    # ------------------------------------------------------------------
    # CRUD actions
    # ------------------------------------------------------------------

    def create_work(self):
        dialog = WorkEditorDialog(self.draw_service, parent=self, translate=self._t, drawings_enabled=self.drawings_enabled)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.work_service.save_work(dialog.get_work_data())
            self.refresh_works()
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.save_failed", "Save failed"), str(exc))

    def edit_work(self):
        selected_ids = self._selected_work_ids()
        if not selected_ids:
            return
        if len(selected_ids) > 1:
            mode = ask_multi_edit_mode(self, len(selected_ids), self._t)
            if mode == "batch":
                self._batch_edit_works(selected_ids)
            elif mode == "group":
                self._group_edit_works(selected_ids)
            return

        work_id = selected_ids[0]
        work = self.work_service.get_work(work_id)
        if not work:
            QMessageBox.warning(
                self,
                self._t("setup_page.message.missing_title", "Missing"),
                self._t("setup_page.message.work_no_longer_exists", "Work no longer exists."),
            )
            self.refresh_works()
            return

        dialog = WorkEditorDialog(self.draw_service, work=work, parent=self, translate=self._t, drawings_enabled=self.drawings_enabled)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.work_service.save_work(dialog.get_work_data())
            self.refresh_works()
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.save_failed", "Save failed"), str(exc))

    def delete_work(self):
        work_id = self._selected_work_id()
        if not work_id:
            return

        logbook_count = self.logbook_service.count_entries_for_work(work_id)

        # Always take a backup before any destructive action.
        try:
            self._create_db_backup("work_delete")
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._t("setup_page.message.backup_failed_title", "Backup failed"),
                self._t(
                    "setup_page.message.backup_failed_body",
                    "Could not create a backup before deleting:\n{error}",
                    error=str(exc),
                ),
            )
            return

        # Primary confirmation: delete the work.
        answer = QMessageBox.question(
            self,
            self._t("setup_page.message.delete_work_title", "Delete work"),
            self._t("setup_page.message.delete_work_prompt", "Delete work '{work_id}'?", work_id=work_id),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        # If logbook entries exist, ask what to do with them.
        delete_logbook = False
        if logbook_count > 0:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle(self._t("setup_page.message.delete_logbook_title", "Delete logbook entries?"))
            box.setText(
                self._t(
                    "setup_page.message.delete_logbook_body",
                    "Work '{work_id}' has {count} logbook entr{plural}.\n\nDo you also want to delete those logbook entries?",
                    work_id=work_id,
                    count=logbook_count,
                    plural="y" if logbook_count == 1 else "ies",
                )
            )
            yes_btn = box.addButton(
                self._t("setup_page.message.delete_logbook_yes", "Delete entries"),
                QMessageBox.DestructiveRole,
            )
            keep_btn = box.addButton(
                self._t("setup_page.message.delete_logbook_keep", "Keep entries"),
                QMessageBox.AcceptRole,
            )
            cancel_btn = box.addButton(
                self._t("common.cancel", "Cancel"),
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
                return
            delete_logbook = box.clickedButton() is yes_btn

        self.work_service.delete_work(work_id)
        if delete_logbook:
            self.logbook_service.delete_entries_for_work(work_id)
        self.refresh_works()

    def duplicate_work(self):
        work_id = self._selected_work_id()
        if not work_id:
            return
        new_id, ok = QInputDialog.getText(
            self,
            self._t("setup_page.message.duplicate_work_title", "Duplicate work"),
            self._t("setup_page.message.new_work_id", "New work ID"),
        )
        if not ok or not (new_id or "").strip():
            return
        desc, _ = QInputDialog.getText(
            self,
            self._t("setup_page.field.description", "Description"),
            self._t("setup_page.message.new_description_optional", "New description (optional)"),
        )
        try:
            self.work_service.duplicate_work(work_id, new_id.strip(), desc.strip())
            self.refresh_works()
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.duplicate_failed", "Duplicate failed"), str(exc))

    def add_log_entry(self):
        work_id = self._selected_work_id()
        if not work_id:
            QMessageBox.information(
                self,
                self._t("setup_page.message.no_work_title", "No work"),
                self._t("setup_page.message.select_work_first", "Select a work first."),
            )
            return

        try:
            next_serial = self.logbook_service.generate_next_serial(work_id, date.today().year)
        except Exception:
            next_serial = ""

        dialog = LogEntryDialog(work_id, next_serial, self, translate=self._t)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.get_data()
        try:
            created_entry = self.logbook_service.add_entry(
                work_id=work_id,
                order_number=payload["order_number"],
                quantity=payload["quantity"],
                notes=payload["notes"],
                custom_serial=payload["custom_serial"],
                entry_date=payload["entry_date"],
            )
            self.refresh_works()
            self.logbookChanged.emit()
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.save_failed", "Save failed"), str(exc))
            return

        if dialog.should_print_card():
            try:
                work = self.work_service.get_work(work_id)
                if not work:
                    QMessageBox.warning(
                        self,
                        self._t("setup_page.message.print_card_title", "Lava card"),
                        self._t(
                            "setup_page.message.entry_saved_missing_work",
                            "Entry saved, but the related work record could not be loaded.",
                        ),
                    )
                    QMessageBox.information(
                        self,
                        self._t("setup_page.message.saved_title", "Saved"),
                        self._t("setup_page.message.logbook_created", "Logbook entry created."),
                    )
                    return
                preview_dir = USER_DATA_DIR / "setup_cards"
                preview_dir.mkdir(parents=True, exist_ok=True)
                date_stamp = datetime.now().strftime('%d-%m-%Y')
                output_path = preview_dir / f"lava-kortti__{date_stamp}.pdf"
                self.print_service.generate_logbook_entry_card(work, created_entry, output_path)
                saved_notice = QMessageBox(self)
                saved_notice.setIcon(QMessageBox.Information)
                saved_notice.setWindowTitle(self._t("setup_page.message.saved_title", "Saved"))
                saved_notice.setText(
                    self._t("setup_page.message.logbook_created_opening", "Logbook entry created. Opening card preview...")
                )
                saved_notice.setStandardButtons(QMessageBox.NoButton)
                saved_notice.setModal(False)
                saved_notice.show()

                def _open_card_after_delay():
                    try:
                        saved_notice.close()
                        saved_notice.deleteLater()
                    except Exception:
                        pass
                    if not self.draw_service.open_drawing(output_path):
                        QMessageBox.warning(
                            self,
                            self._t("setup_page.message.open_failed", "Open failed"),
                            self._t(
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
                    self,
                    self._t("setup_page.message.print_card_title", "Lava card"),
                    self._t(
                        "setup_page.message.entry_saved_card_generation_failed",
                        "Entry saved, but Lava card generation failed:\n{error}",
                        error=exc,
                    ),
                )
                QMessageBox.information(
                    self,
                    self._t("setup_page.message.saved_title", "Saved"),
                    self._t("setup_page.message.logbook_created", "Logbook entry created."),
                )
            return

        QMessageBox.information(
            self,
            self._t("setup_page.message.saved_title", "Saved"),
            self._t("setup_page.message.logbook_created", "Logbook entry created."),
        )

    def view_setup_card(self):
        work_id = self._selected_work_id()
        if not work_id:
            QMessageBox.information(
                self,
                self._t("setup_page.message.no_work_title", "No work"),
                self._t("setup_page.message.select_work_first", "Select a work first."),
            )
            return

        work = self.work_service.get_work(work_id)
        if not work:
            QMessageBox.warning(
                self,
                self._t("setup_page.message.missing_title", "Missing"),
                self._t("setup_page.message.work_no_longer_exists", "Work no longer exists."),
            )
            return

        entries = self.logbook_service.list_entries(filters={"work_id": work_id})
        entry = entries[0] if entries else None
        if not entry:
            answer = QMessageBox.question(
                self,
                self._t("setup_page.message.no_logbook_entry_title", "No logbook entry"),
                self._t(
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
            self.print_service.generate_setup_card(work, entry, output_path)
            if not self.draw_service.open_drawing(output_path):
                QMessageBox.warning(
                    self,
                    self._t("setup_page.message.open_failed", "Open failed"),
                    self._t(
                        "setup_page.message.setup_card_created_not_opened",
                        "Setup card created but could not be opened:\n{path}",
                        path=output_path,
                    ),
                )
        except Exception as exc:
            QMessageBox.critical(self, self._t("setup_page.message.view_failed", "View failed"), str(exc))


from typing import Callable

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from machine_profiles import NTX_MACHINE_PROFILE, load_profile
from ui.work_editor_support import (
    WorkEditorJawSelectorPanel,
    WorkEditorOrderedToolList,
    WorkEditorPayloadAdapter,
    WorkEditorToolRemoveDropButton,
    SelectorSessionBridge,
    apply_jaw_selector_result,
    apply_tool_selector_result,
    build_general_tab_ui,
    build_initial_jaw_assignments,
    build_notes_tab_ui,
    build_spindles_tab_ui,
    build_tools_tab_ui,
    build_zeros_tab_ui,
    collect_unresolved_reference_messages,
    current_tools_head_value,
    default_jaw_selector_spindle,
    default_pot_for_assignment,
    default_selector_head,
    default_selector_spindle,
    effective_active_tool_list,
    ensure_selector_callback_server,
    jaw_ref_key,
    merge_jaw_refs,
    merge_tool_refs,
    normalize_selector_head,
    normalize_selector_spindle,
    on_tool_list_interaction,
    open_combined_tools_jaws_selector_session,
    open_external_selector_session_for_dialog,
    open_jaw_selector_session,
    open_pot_editor_dialog,
    open_tool_selector_session,
    parse_optional_int,
    populate_default_pots,
    refresh_external_refs,
    refresh_tool_head_widgets,
    remove_dragged_tool_assignments,
    selector_initial_tool_assignment_buckets,
    selector_initial_tool_assignments,
    selector_target_ordered_list,
    set_active_tool_list,
    set_tools_head_value,
    shared_add_tool_comment,
    shared_delete_tool_comment,
    shared_move_tool_down,
    shared_move_tool_up,
    shared_remove_selected_tool,
    show_selector_warning_for_dialog,
    shutdown_selector_bridge,
    sync_tool_head_view,
    toggle_tools_head_view,
    tool_icon_for_type_in_spindle,
    tool_ref_key,
    head_label,
    spindle_label,
    toolbar_icon,
    update_shared_tool_actions,
    update_tools_head_switch_text,
    visible_tool_lists,
    build_spindle_zero_group,
    make_zero_axis_input,
    set_coord_combo,
    set_zero_xy_visibility,
)
from config import (
    SHARED_UI_PREFERENCES_PATH,
    TOOL_LIBRARY_EXE_CANDIDATES,
    TOOL_LIBRARY_MAIN_PATH,
    TOOL_LIBRARY_PROJECT_DIR,
    TOOL_LIBRARY_SERVER_NAME,
)
from shared.services.ui_preferences_service import UiPreferencesService
from ui.work_editor_support.dialog_lifecycle import (
    apply_secondary_button_theme,
    finalize_ui,
    setup_button_row,
    setup_tabs,
)
from ui.widgets.common import apply_tool_library_combo_style, clear_focused_dropdown_on_outside_click
try:
    from shared.ui.helpers.editor_helpers import (
        ResponsiveColumnsHost,
        apply_shared_checkbox_style,
        apply_titled_section_style,
        create_titled_section,
    )
except ModuleNotFoundError:
    from editor_helpers import ResponsiveColumnsHost, apply_shared_checkbox_style, apply_titled_section_style, create_titled_section


WORK_COORDINATES = ["G54", "G55", "G56", "G57", "G58", "G59"]
ZERO_AXES = ("z", "x", "y", "c")


def _noop_translate(_key: str, default: str | None = None, **_kwargs) -> str:
    return default or ""


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("sectionTitle", True)
    return lbl


class WorkEditorDialog(QDialog):
    def __init__(
        self,
        draw_service,
        work=None,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
        batch_label: str | None = None,
        group_edit_mode: bool = False,
        group_count: int | None = None,
        drawings_enabled: bool = True,
    ):
        super().__init__(parent)
        self.draw_service = draw_service
        self.work = dict(work or {})
        self.is_edit = bool(work)
        self._translate = translate or _noop_translate
        self._batch_label = (batch_label or "").strip()
        self._group_edit_mode = bool(group_edit_mode)
        self._group_count = int(group_count or 0)
        self._drawings_enabled = drawings_enabled
        try:
            prefs_service = UiPreferencesService(SHARED_UI_PREFERENCES_PATH, include_setup_db_path=True)
            profile_key = prefs_service.get_machine_profile_key()
            self.machine_profile = load_profile(profile_key)
        except Exception:
            self.machine_profile = NTX_MACHINE_PROFILE
        self._payload_adapter = WorkEditorPayloadAdapter(self.machine_profile)
        self._zero_axes = tuple(self.machine_profile.zero_axes)
        self._head_profiles = {head.key: head for head in self.machine_profile.heads}
        self._spindle_profiles = {spindle.key: spindle for spindle in self.machine_profile.spindles}
        self._zero_axis_widgets = {axis: [] for axis in self._zero_axes}
        self._zero_axis_inputs: dict[str, list[QLineEdit]] = {axis: [] for axis in self._zero_axes}
        self._zero_coord_inputs: dict[tuple[str, str], QComboBox] = {}
        self._zero_axis_input_map: dict[tuple[str, str, str], QLineEdit] = {}
        self._jaw_selectors: dict[str, WorkEditorJawSelectorPanel] = {}
        self._ordered_tool_lists: dict[str, WorkEditorOrderedToolList] = {}
        self._tool_column_lists: dict[str, dict[str, WorkEditorOrderedToolList]] = {}
        self._all_tool_list_widgets: list[WorkEditorOrderedToolList] = []
        self._active_tool_list: WorkEditorOrderedToolList | None = None
        self._syncing_tool_list_state = False
        self._sub_program_inputs: dict[str, QLineEdit] = {}
        self._tool_cache_by_head: dict[str, list[dict]] = {}
        self._tool_cache_all: list[dict] = []
        self._jaw_cache: list[dict] = []

        self.setWindowTitle(self._dialog_title())
        self.resize(960, 680)
        self.setMinimumSize(760, 560)
        self.setSizeGripEnabled(True)
        self.setProperty("workEditorDialog", True)
        self._zero_point_grids: list[QGridLayout] = []
        self._zero_coord_combos: list[QComboBox] = []
        self._zero_row_spacers: list[QLabel] = []
        self._zero_grids_with_groups: list[tuple] = []
        self._selector_bridge = SelectorSessionBridge(
            parent=self,
            translate=self._t,
            show_warning=self._show_selector_warning,
            normalize_head=self._normalize_selector_head,
            normalize_spindle=self._normalize_selector_spindle,
            default_spindle=self._default_selector_spindle,
            initial_tool_assignment_buckets=self._selector_initial_tool_assignment_buckets,
            apply_tool_result=self._apply_tool_selector_result,
            apply_jaw_result=self._apply_jaw_selector_result,
            open_jaw_selector=self._open_jaw_selector,
            tool_library_server_name=TOOL_LIBRARY_SERVER_NAME,
            tool_library_main_path=TOOL_LIBRARY_MAIN_PATH,
            tool_library_project_dir=TOOL_LIBRARY_PROJECT_DIR,
            tool_library_exe_candidates=TOOL_LIBRARY_EXE_CANDIDATES,
            tools_db_path=str(draw_service.tool_db_path),
            jaws_db_path=str(draw_service.jaw_db_path),
        )

        setup_tabs(self)

        self._build_general_tab()
        self._build_zeros_tab()
        self._build_tools_tab()
        self._build_notes_tab()

        setup_button_row(self)

        # Keep dialog actions visually consistent with secondary gray buttons.
        self._set_secondary_button_theme()

        self._load_external_refs()
        self._load_work()

        finalize_ui(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and isinstance(obj, QWidget):
            if obj is self or self.isAncestorOf(obj):
                return True
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def closeEvent(self, event):
        self._shutdown_selector_bridge()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _head_label(self, head_key: str, fallback: str | None = None) -> str:
        return head_label(self, head_key, fallback)

    def _spindle_label(self, spindle_key: str, fallback: str | None = None) -> str:
        return spindle_label(self, spindle_key, fallback)

    @staticmethod
    def _normalize_selector_head(value: str | None) -> str:
        return normalize_selector_head(value)

    @staticmethod
    def _normalize_selector_spindle(value: str | None) -> str:
        return normalize_selector_spindle(value)

    def _selector_target_ordered_list(self, head_key: str):
        return selector_target_ordered_list(self, head_key)

    def _default_selector_spindle(self) -> str:
        return default_selector_spindle(self)

    def _current_tools_head_value(self) -> str:
        return current_tools_head_value(self)

    def _update_tools_head_switch_text(self):
        update_tools_head_switch_text(self)

    def _set_tools_head_value(self, head: str):
        set_tools_head_value(self, head)

    def _toggle_tools_head_view(self):
        toggle_tools_head_view(self)

    def _default_selector_head(self) -> str:
        return default_selector_head(self)

    def _default_jaw_selector_spindle(self) -> str:
        return default_jaw_selector_spindle(self)

    def _show_selector_warning(self, title: str, body: str):
        show_selector_warning_for_dialog(self, title, body)

    def _ensure_selector_callback_server(self) -> bool:
        return ensure_selector_callback_server(self)

    def _shutdown_selector_bridge(self):
        shutdown_selector_bridge(self)

    def _open_external_selector_session(
        self,
        *,
        kind: str,
        head: str | None = None,
        spindle: str | None = None,
        follow_up: dict | None = None,
        initial_assignments: list[dict] | None = None,
    ) -> bool:
        return open_external_selector_session_for_dialog(
            self,
            kind=kind,
            head=head,
            spindle=spindle,
            follow_up=follow_up,
            initial_assignments=initial_assignments,
        )

    @staticmethod
    def _parse_optional_int(value) -> int | None:
        return parse_optional_int(value)

    @staticmethod
    def _tool_ref_key(tool: dict | None) -> str:
        return tool_ref_key(tool)

    @staticmethod
    def _jaw_ref_key(jaw: dict | None) -> str:
        return jaw_ref_key(jaw)

    def _merge_tool_refs(self, head_key: str, selected_items: list[dict]):
        merge_tool_refs(self, head_key, selected_items)

    def _merge_jaw_refs(self, selected_items: list[dict]):
        merge_jaw_refs(self, selected_items)

    def _apply_tool_selector_result(self, request: dict, selected_items: list[dict]) -> bool:
        return apply_tool_selector_result(self, request, selected_items)

    def _apply_jaw_selector_result(self, request: dict, selected_items: list[dict]) -> bool:
        return apply_jaw_selector_result(self, request, selected_items)

    def _on_jaw_dropped_in_selector_panel(self, jaw: dict, spindle_key: str = "main") -> None:
        """Handle jaw dropped onto a selector panel from Tools library.
        
        Args:
            jaw: The jaw dict from the drop event
            spindle_key: The spindle key ("main" or "sub") this panel corresponds to
        """
        if not isinstance(jaw, dict):
            return
        # Get the selector for this spindle
        selector = self._jaw_selectors.get(spindle_key)
        if selector is None:
            return
        # Extract jaw ID
        jaw_id = str(jaw.get("jaw_id") or jaw.get("id") or "").strip()
        if not jaw_id:
            return
        # Update the cache with the new jaw reference
        self._merge_jaw_refs([jaw])
        # Set  the value on the selector panel
        selector.set_value(jaw_id)

    def _dialog_title(self) -> str:
        if self._group_edit_mode:
            if self._group_count > 1:
                return self._t(
                    "work_editor.window_title.group",
                    "Group Edit ({count} items)",
                    count=self._group_count,
                )
            return self._t("work_editor.window_title.group", "Group Edit")
        if self.is_edit:
            base = self._t("work_editor.window_title.edit", "Edit Work")
        else:
            base = self._t("work_editor.window_title.new", "New Work")
        if self._batch_label:
            return f"{base} ({self._batch_label})"
        return base

    def _set_secondary_button_theme(self):
        apply_secondary_button_theme(self)

    def _apply_coord_combo_popup_style(self, combo: QComboBox):
        apply_tool_library_combo_style(combo)

    def _make_axis_input(self, value_attr_name: str, axis: str) -> QLineEdit:
        return make_zero_axis_input(self, value_attr_name, axis)

    def _set_zero_xy_visibility(self, show_xy: bool) -> None:
        set_zero_xy_visibility(self, show_xy)

    def _build_spindle_zero_group(self, title: str, spindle_key: str) -> QGroupBox:
        return build_spindle_zero_group(
            self,
            title,
            spindle_key,
            create_titled_section_fn=create_titled_section,
            work_coordinates=WORK_COORDINATES,
        )

    def _set_coord_combo(self, combo: QComboBox, value: str, default: str):
        set_coord_combo(combo, value, default)

    def _apply_machine_profile_to_jaw_selectors(self):
        """Sync jaw selector affordances from the active machine profile."""
        for spindle_key, selector in self._jaw_selectors.items():
            profile = self._spindle_profiles.get(spindle_key)
            if profile is None:
                selector.setVisible(False)
                continue
            selector._spindle_side_filter = profile.jaw_filter

    def _build_general_tab(self):
        build_general_tab_ui(self, create_titled_section_fn=create_titled_section)

    def _build_spindles_tab(self):
        build_spindles_tab_ui(self, jaw_selector_panel_cls=WorkEditorJawSelectorPanel)

    def _build_zeros_tab(self):
        build_zeros_tab_ui(
            self,
            jaw_selector_panel_cls=WorkEditorJawSelectorPanel,
            create_titled_section_fn=create_titled_section,
        )

    def _build_tools_tab(self):
        WorkEditorOrderedToolList.configure_dependencies(
            toolbar_icon_resolver=toolbar_icon,
            tool_icon_for_spindle_resolver=tool_icon_for_type_in_spindle,
            default_pot_for_assignment_resolver=self._default_pot_for_assignment,
            combo_popup_styler=apply_tool_library_combo_style,
        )
        build_tools_tab_ui(
            self,
            ordered_tool_list_cls=WorkEditorOrderedToolList,
            remove_drop_button_cls=WorkEditorToolRemoveDropButton,
            section_label_factory=_section_label,
        )

    def _visible_tool_lists(self) -> list[WorkEditorOrderedToolList]:
        return visible_tool_lists(self)

    def _effective_active_tool_list(self) -> WorkEditorOrderedToolList | None:
        return effective_active_tool_list(self)

    def _on_tool_list_interaction(self, ordered_list: WorkEditorOrderedToolList):
        on_tool_list_interaction(self, ordered_list)

    def _set_active_tool_list(self, ordered_list: WorkEditorOrderedToolList | None):
        set_active_tool_list(self, ordered_list)

    def _update_shared_tool_actions(self):
        update_shared_tool_actions(self)

    def _shared_move_tool_up(self):
        shared_move_tool_up(self)

    def _shared_move_tool_down(self):
        shared_move_tool_down(self)

    def _shared_remove_selected_tool(self):
        shared_remove_selected_tool(self)

    def _shared_add_tool_comment(self):
        shared_add_tool_comment(self)

    def _shared_delete_tool_comment(self):
        shared_delete_tool_comment(self)

    def _remove_dragged_tool_assignments(self, dropped_items: list[dict]):
        remove_dragged_tool_assignments(self, dropped_items)

    def _refresh_tool_head_widgets(self, head_key: str):
        refresh_tool_head_widgets(self, head_key)

    def _sync_tool_head_view(self):
        sync_tool_head_view(self)

    def _on_print_pots_toggled(self, checked: bool):
        if checked:
            self._populate_default_pots()
        for ordered_list in self._all_tool_list_widgets:
            ordered_list._show_pot = checked
            ordered_list._render_current_spindle()

    @staticmethod
    def _default_pot_for_assignment(ordered_list, assignment: dict) -> str:
        return default_pot_for_assignment(ordered_list, assignment)

    def _populate_default_pots(self):
        populate_default_pots(self)

    def _open_pot_editor(self):
        open_pot_editor_dialog(self)

    def _open_tool_selector_for_bucket(self, head_key: str, spindle: str):
        self._open_tool_selector(
            initial_head=head_key,
            initial_spindle=spindle,
            initial_assignments=self._selector_initial_tool_assignments(head_key, spindle),
        )

    def _selector_initial_tool_assignments(self, head_key: str, spindle: str) -> list[dict]:
        target_head = self._normalize_selector_head(head_key)
        ordered_list = self._selector_target_ordered_list(target_head)
        return selector_initial_tool_assignments(ordered_list, spindle)

    def _selector_initial_tool_assignment_buckets(self) -> dict[str, list[dict]]:
        return selector_initial_tool_assignment_buckets(
            self._ordered_tool_lists,
            tuple(self._head_profiles.keys()),
            tuple(self._spindle_profiles.keys()),
        )

    def _open_tool_selector(
        self,
        initial_head: str | None = None,
        initial_spindle: str | None = None,
        initial_assignments: list[dict] | None = None,
    ) -> bool:
        return open_tool_selector_session(
            self,
            initial_head=initial_head,
            initial_spindle=initial_spindle,
            initial_assignments=initial_assignments,
        )

    def _selector_initial_jaw_assignments(self) -> list[dict]:
        return build_initial_jaw_assignments(self)

    def _open_jaw_selector(self, initial_spindle: str | None = None) -> bool:
        return open_jaw_selector_session(self, initial_spindle=initial_spindle)

    def _open_combined_tools_jaws_selector(self):
        open_combined_tools_jaws_selector_session(self)

    def _build_notes_tab(self):
        build_notes_tab_ui(self, create_titled_section_fn=create_titled_section)

    # ------------------------------------------------------------------
    # IO helpers
    # ------------------------------------------------------------------

    def _browse_drawing(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("work_editor.dialog.select_drawing", "Select drawing"),
            "",
            self._t("work_editor.dialog.pdf_filter", "PDF Files (*.pdf)"),
        )
        if path:
            self.drawing_path_input.setText(path)

    def _load_external_refs(self):
        refresh_external_refs(self)

    def _load_work(self):
        if not self.work:
            return
        self._payload_adapter.populate_dialog(self, self.work)
        for head_key in self._head_profiles.keys():
            self._refresh_tool_head_widgets(head_key)
        self._sync_tool_head_view()

    def get_work_data(self) -> dict:
        return self._payload_adapter.collect_payload(
            self,
            persisted_work=self.work,
            drawings_enabled=self._drawings_enabled,
        )

    def _on_save(self):
        work_id = self.work_id_input.text().strip()
        if not work_id and not self._group_edit_mode:
            QMessageBox.warning(
                self,
                self._t("work_editor.message.missing_id_title", "Missing ID"),
                self._t("work_editor.message.work_id_required", "Work ID is required."),
            )
            self.tabs.setCurrentWidget(self.general_tab)
            self.work_id_input.setFocus()
            return

        missing = collect_unresolved_reference_messages(self)

        if missing:
            answer = QMessageBox.question(
                self,
                self._t("work_editor.message.unresolved_title", "Unresolved references"),
                self._t(
                    "work_editor.message.unresolved_body",
                    "Some IDs were not found in master databases:\n\n{missing}\n\nSave anyway?",
                    missing="\n".join(missing),
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return

        self.accept()













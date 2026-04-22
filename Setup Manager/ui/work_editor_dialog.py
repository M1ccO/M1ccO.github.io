import logging
from typing import Callable
from uuid import UUID, uuid4

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
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
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from machine_profiles import NTX_MACHINE_PROFILE, load_profile, resolve_profile_key
from ui.work_editor_support import (
    WorkEditorJawSelectorPanel,
    WorkEditorOrderedToolList,
    WorkEditorPayloadAdapter,
    WorkEditorToolRemoveDropButton,
    build_general_tab_ui,
    build_machining_center_zeros_tab_ui,
    build_notes_tab_ui,
    build_spindles_tab_ui,
    build_tools_tab_ui,
    build_zeros_tab_ui,
    collect_unresolved_reference_messages,
    default_pot_for_assignment,
    effective_active_tool_list,
    normalize_selector_head,
    normalize_selector_spindle,
    on_tool_list_interaction,
    open_pot_editor_dialog,
    populate_default_pots,
    refresh_external_refs,
    refresh_tool_head_widgets,
    remove_dragged_tool_assignments,
    selector_target_ordered_list,
    set_active_tool_list,
    shared_move_tool_down,
    shared_move_tool_up,
    shared_remove_selected_tool,
    sync_tool_head_view,
    tool_icon_for_type_in_spindle,
    head_label,
    spindle_label,
    toolbar_icon,
    update_shared_tool_actions,
    visible_tool_lists,
    build_spindle_zero_group,
    make_zero_axis_input,
    set_coord_combo,
    set_zero_xy_visibility,
)
from config import (
    SHARED_UI_PREFERENCES_PATH,
    STYLE_PATH,
)
from shared.services.ui_preferences_service import UiPreferencesService
from shared.ui.theme import compile_app_stylesheet
from shared.selector.payloads import (
    SelectionBatch,
    ToolBucket,
)
from ui.work_editor_support.dialog_lifecycle import (
    apply_secondary_button_theme,
    finalize_ui,
    setup_button_row,
    setup_tabs,
)
from ui.work_editor_support.selector_session_controller import WorkEditorSelectorController
from ui.work_editor_support.selector_adapter import merge_jaw_refs
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
    WORK_COORDINATES = WORK_COORDINATES
    _SELECTOR_MIN_WIDTH = 1100
    _SELECTOR_EXPAND_DELTA = 480
    _SELECTOR_DIALOG_DEFAULT_WIDTH = 1500
    _SELECTOR_DIALOG_DEFAULT_HEIGHT = 860
    _SELECTOR_DIALOG_WIDTH_PAD = 420
    _SELECTOR_DIALOG_HEIGHT_PAD = 180
    _RESIZE_FOR_SELECTOR_MODE = True
    _SELECTOR_OPEN_REVEAL_MS = 0
    _SELECTOR_LOCAL_FADE_MS = 0
    _SELECTOR_TRANSITION_SHIELD_DELAY_MS = 0
    _LOGGER = logging.getLogger(__name__)

    def __init__(
        self,
        draw_service,
        work=None,
        parent=None,
        style_host: QWidget | None = None,
        translate: Callable[[str, str | None], str] | None = None,
        batch_label: str | None = None,
        group_edit_mode: bool = False,
        group_count: int | None = None,
        drawings_enabled: bool = True,
        machine_profile_key: str | None = None,
    ):
        super().__init__(parent)
        self.draw_service = draw_service
        self.work = dict(work or {})
        self.is_edit = bool(work)
        self._explicit_style_host = style_host if isinstance(style_host, QWidget) else None
        self._translate = translate or _noop_translate
        self._batch_label = (batch_label or "").strip()
        self._group_edit_mode = bool(group_edit_mode)
        self._group_count = int(group_count or 0)
        self._drawings_enabled = drawings_enabled
        try:
            prefs_service = UiPreferencesService(SHARED_UI_PREFERENCES_PATH, include_setup_db_path=True)
            _prefs_data = prefs_service.load()

            raw_machine_profile_key = str(machine_profile_key or "").strip()
            raw_prefs_profile_key = str(_prefs_data.get("machine_profile_key") or "").strip()

            if raw_machine_profile_key:
                profile_key = resolve_profile_key(raw_machine_profile_key)
                profile_source = "parameter"
            elif raw_prefs_profile_key:
                profile_key = resolve_profile_key(raw_prefs_profile_key)
                profile_source = "preferences"
            else:
                profile_key = "ntx_2sp_2h"
                profile_source = "default"

            base_profile = load_profile(profile_key)
            try:
                from machine_profiles import apply_machining_center_overrides
                self.machine_profile = apply_machining_center_overrides(
                    base_profile,
                    fourth_axis_letter=_prefs_data.get("mc_fourth_axis_letter"),
                    fifth_axis_letter=_prefs_data.get("mc_fifth_axis_letter"),
                    has_turning_option=_prefs_data.get("mc_has_turning_option"),
                )
            except Exception:
                self.machine_profile = base_profile
            self._op20_jaws_enabled = bool(_prefs_data.get("op20_jaws_default", False))
            self._op20_tools_enabled = bool(_prefs_data.get("op20_tools_default", False))
            self._LOGGER.info(
                "work_editor.profile_resolved source=%s resolved=%s raw_param=%s raw_prefs=%s",
                profile_source,
                profile_key,
                raw_machine_profile_key,
                raw_prefs_profile_key,
            )
        except Exception:
            self.machine_profile = NTX_MACHINE_PROFILE
            self._op20_jaws_enabled = False
            self._op20_tools_enabled = False
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
        self._selector_ctrl = WorkEditorSelectorController(self)
        self._selector_cache_merge_enabled = False
        self._host_visual_style_applied = False
        self._raw_part_combo_popup_allowed = False
        self._raw_part_combo_popup_window: QWidget | None = None
        self.setUpdatesEnabled(False)
        try:
            setup_tabs(self)
            self.tabs.currentChanged.connect(self._on_tabs_current_changed)

            self._build_general_tab()
            self._build_notes_tab()

            setup_button_row(self)

            self._load_external_refs()
            self._load_work()
            self._initialize_family_shell()

            # Apply stylesheet after the full initial hierarchy exists so the
            # first visible paint is not chasing late subtree polish work.
            self._apply_host_visual_style()

            # Keep dialog actions visually consistent with secondary gray buttons.
            self._set_secondary_button_theme()

            finalize_ui(self)
            self._close_transient_combo_popups()
            self._setup_raw_part_combo_popup_guard()
            self._install_local_event_filters()
        finally:
            self.setUpdatesEnabled(True)

    def _initialize_family_shell(self) -> None:
        """Build zeros and tools tabs eagerly during construction."""
        self._build_zeros_tab()
        self._apply_work_payload_to_zeros_tab()
        self._build_tools_tab()
        self._apply_work_payload_to_tools_tab()
        for head_key in self._head_profiles.keys():
            self._refresh_tool_head_widgets(head_key)
        self._sync_tool_head_view()

    def _close_transient_combo_popups(self) -> None:
        """Defensively close any combo popups opened during startup wiring."""
        for combo in self.findChildren(QComboBox):
            try:
                combo.hidePopup()
            except Exception:
                pass

    @staticmethod
    def _is_true_popup_window(widget: QWidget | None) -> bool:
        if not isinstance(widget, QWidget):
            return False
        return (widget.windowFlags() & Qt.WindowType_Mask) == Qt.Popup

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._host_visual_style_applied:
            self._apply_host_visual_style()
        ctrl = getattr(self, "_selector_ctrl", None)
        if ctrl is not None:
            ctrl._sync_overlay_geometry()
            ctrl._sync_shield_geometry()

    def _on_tabs_current_changed(self, index: int) -> None:
        pass

    def _apply_work_payload_to_zeros_tab(self) -> None:
        if not self.work:
            return
        payload = self.work
        if hasattr(self, "main_program_input"):
            self.main_program_input.setText(payload.get("main_program", ""))
        for spindle in self.machine_profile.spindles:
            selector = self._jaw_selectors.get(spindle.key)
            if selector is None:
                continue
            selector.set_value(payload.get(self._payload_adapter.jaw_field(spindle.key), ""))
            selector.set_stop_screws(payload.get(self._payload_adapter.stop_screws_field(spindle.key), ""))

        if self.machine_profile.spindle_count == 1:
            _sub_sel = self._jaw_selectors.get("sub")
            if _sub_sel is not None:
                _sub_sel.set_value(payload.get(self._payload_adapter.jaw_field("sub"), ""))
                _sub_sel.set_stop_screws(payload.get(self._payload_adapter.stop_screws_field("sub"), ""))

        for head in self.machine_profile.heads:
            program_input = self._sub_program_inputs.get(head.key)
            if program_input is not None:
                program_input.setText(payload.get(self._payload_adapter.sub_program_field(head.key), ""))

            for spindle in self.machine_profile.spindles:
                combo = self._zero_coord_inputs.get((head.key, spindle.key))
                if combo is not None:
                    self._set_coord_combo(
                        combo,
                        payload.get(
                            self._payload_adapter.coord_field(head.key, spindle.key),
                            payload.get(self._payload_adapter.legacy_zero_field(head.key), ""),
                        ),
                        head.default_coord,
                    )
                for axis in self.machine_profile.zero_axes:
                    widget = self._zero_axis_input_map.get((head.key, spindle.key, axis))
                    if widget is not None:
                        widget.setText(payload.get(self._payload_adapter.axis_field(head.key, spindle.key, axis), ""))

        if hasattr(self, "sub_pickup_z_input"):
            self.sub_pickup_z_input.setText(payload.get("sub_pickup_z", ""))

        if hasattr(self, "op20_jaws_checkbox"):
            self.op20_jaws_checkbox.setChecked(bool(self._op20_jaws_enabled))



    def _apply_work_payload_to_tools_tab(self) -> None:
        if not self.work:
            return
        for head_key in self._head_profiles.keys():
            seen_widget_ids: set[int] = set()
            for ordered_list in (self._tool_column_lists.get(head_key) or {}).values():
                if ordered_list is None:
                    continue
                widget_id = id(ordered_list)
                if widget_id in seen_widget_ids:
                    continue
                seen_widget_ids.add(widget_id)
                ordered_list.set_tool_assignments(
                    self.work.get(self._payload_adapter.tool_assignment_field(head_key), [])
                )
        if hasattr(self, "print_pots_checkbox"):
            self.print_pots_checkbox.setChecked(bool(self.work.get("print_pots", False)))



    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        ctrl = getattr(self, "_selector_ctrl", None)
        if ctrl is not None:
            ctrl._sync_overlay_geometry()
            ctrl._sync_shield_geometry()

    def _resolve_style_host(self) -> QWidget | None:
        explicit_host = getattr(self, "_explicit_style_host", None)
        if isinstance(explicit_host, QWidget):
            return explicit_host

        candidates: list[QWidget] = []

        parent_widget = self.parentWidget()
        if isinstance(parent_widget, QWidget):
            parent_window = parent_widget.window()
            if isinstance(parent_window, QWidget) and parent_window is not self:
                candidates.append(parent_window)

        active_window = QApplication.activeWindow()
        if isinstance(active_window, QWidget) and active_window is not self:
            candidates.append(active_window)

        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QWidget) and widget is not self:
                candidates.append(widget)

        unique_candidates: list[QWidget] = []
        seen_ids: set[int] = set()
        for widget in candidates:
            widget_id = id(widget)
            if widget_id in seen_ids:
                continue
            seen_ids.add(widget_id)
            unique_candidates.append(widget)

        styled_candidates = [widget for widget in unique_candidates if str(widget.styleSheet() or "").strip()]
        if styled_candidates:
            return max(styled_candidates, key=lambda widget: len(str(widget.styleSheet() or "")))
        return unique_candidates[0] if unique_candidates else None

    def _load_work_editor_style_sheet_from_disk(self) -> str:
        try:
            prefs = UiPreferencesService(
                SHARED_UI_PREFERENCES_PATH,
                include_setup_db_path=True,
            ).load()
            return compile_app_stylesheet(STYLE_PATH, prefs)
        except Exception:
            return ""

    def _apply_host_visual_style(self) -> None:
        for widget in (
            self,
            getattr(self, "_normal_page", None),
            getattr(self, "_selector_page", None),
            getattr(self, "_selector_overlay_container", None),
            getattr(self, "_selector_transition_shield", None),
        ):
            if isinstance(widget, QWidget):
                widget.setAttribute(Qt.WA_StyledBackground, True)

        host = self._resolve_style_host()
        style_sheet = ""
        if isinstance(host, QWidget):
            style_sheet = str(host.styleSheet() or "")
            self.setPalette(host.palette())
            self.setFont(host.font())

        if not style_sheet.strip():
            style_sheet = self._load_work_editor_style_sheet_from_disk()

        if style_sheet.strip():
            current = str(self.styleSheet() or "")
            if current != style_sheet:
                self.setStyleSheet(style_sheet)
                self.style().unpolish(self)
                self.style().polish(self)
        # Flag latches unconditionally so showEvent never re-enters this path
        # after __init__, preventing a post-map polish repaint on first open.
        self._host_visual_style_applied = True

    def _setup_raw_part_combo_popup_guard(self) -> None:
        """Allow RAW PART dropdown popup only after explicit user interaction."""
        combo = getattr(self, "raw_part_kind_combo", None)
        if not isinstance(combo, QComboBox):
            return
        try:
            popup_window = combo.view().window()
        except Exception:
            popup_window = None
        if isinstance(popup_window, QWidget) and self._is_true_popup_window(popup_window):
            self._raw_part_combo_popup_window = popup_window
            popup_window.installEventFilter(self)

    def _resolve_selector_transport_mode(self) -> str:
        return self._selector_ctrl._transport_mode

    def _log_selector_event(self, event: str, **fields) -> None:
        self._selector_ctrl._log(event, **fields)

    def _selector_host_uses_overlay_mode(self) -> bool:
        return self._selector_ctrl._host_uses_overlay_mode()

    def _selector_current_mount_container(self) -> QWidget:
        return self._selector_ctrl._current_mount_container()

    def _install_selector_transition_trace_filters(self) -> None:
        self._selector_ctrl.install_trace_filters()

    def _trace_selector_surface_event(self, obj, event) -> None:
        self._selector_ctrl.trace_surface_event(obj, event)

    def _install_local_event_filters(self) -> None:
        """Scope event filtering to this dialog tree (no app-wide filter)."""
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)
        self._install_selector_transition_trace_filters()

    def eventFilter(self, obj, event):
        self._trace_selector_surface_event(obj, event)
        combo = getattr(self, "raw_part_kind_combo", None)
        if isinstance(combo, QComboBox):
            if obj is combo and event.type() in (QEvent.MouseButtonPress, QEvent.KeyPress):
                self._raw_part_combo_popup_allowed = True
            popup_window = self._raw_part_combo_popup_window
            if (
                popup_window is not None
                and obj is popup_window
                and event.type() == QEvent.Show
                and self._is_true_popup_window(popup_window)
            ):
                if not self._raw_part_combo_popup_allowed:
                    QTimer.singleShot(0, combo.hidePopup)
                    return True

        if event.type() == QEvent.ToolTip and isinstance(obj, QWidget):
            if obj is self or self.isAncestorOf(obj):
                return True
        if event.type() == QEvent.MouseButtonPress:
            clear_focused_dropdown_on_outside_click(obj, self)
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self._selector_ctrl.force_shutdown()
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
        merge_jaw_refs(self, [jaw])
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
            parent=getattr(self, "zero_points_host", None),
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
        self._build_family_zeros_tab()

    def _build_tools_tab(self):
        WorkEditorOrderedToolList.configure_dependencies(
            toolbar_icon_resolver=toolbar_icon,
            tool_icon_for_spindle_resolver=tool_icon_for_type_in_spindle,
            default_pot_for_assignment_resolver=self._default_pot_for_assignment,
            combo_popup_styler=apply_tool_library_combo_style,
            direct_tool_ref_resolver=self._resolve_tool_reference_for_assignment,
        )
        self._build_family_tools_tab()

    def _build_family_zeros_tab(self) -> None:
        build_zeros_tab_ui(
            self,
            jaw_selector_panel_cls=WorkEditorJawSelectorPanel,
            create_titled_section_fn=create_titled_section,
        )

    def _build_family_tools_tab(self) -> None:
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

    def _resolve_tool_reference_for_assignment(self, assignment: dict) -> dict | None:
        if not isinstance(assignment, dict):
            return None

        tool_id = str(assignment.get("tool_id") or assignment.get("id") or "").strip()
        resolved = self._resolve_tool_ref_via_resolver(tool_id)
        if isinstance(resolved, dict) and str(resolved.get("tool_type") or "").strip():
            return resolved

        tool_uid = assignment.get("tool_uid", assignment.get("uid"))
        try:
            if tool_uid is not None and str(tool_uid).strip():
                ref = self.draw_service.get_tool_ref_by_uid(tool_uid)
                if isinstance(ref, dict) and str(ref.get("id") or "").strip():
                    if isinstance(resolved, dict):
                        merged = dict(resolved)
                        merged.update({k: v for k, v in ref.items() if v not in (None, "")})
                        return merged
                    return ref
        except Exception:
            pass

        if tool_id:
            try:
                ref = self.draw_service.get_tool_ref(tool_id)
                if isinstance(ref, dict) and str(ref.get("id") or "").strip():
                    if isinstance(resolved, dict):
                        merged = dict(resolved)
                        merged.update({k: v for k, v in ref.items() if v not in (None, "")})
                        return merged
                    return ref
            except Exception:
                pass

        if isinstance(resolved, dict):
            return resolved
        if not tool_id:
            return None
        return None

    def _resolve_tool_ref_via_resolver(self, tool_id: str) -> dict | None:
        try:
            from shared.ui.resolvers import get_resolver
            from shared.selector.payloads import ToolBucket
            resolver = get_resolver("tool")
            resolved = resolver.resolve_tool(tool_id, bucket=ToolBucket.MAIN)
            if resolved is None:
                return None
            metadata = getattr(resolved, "metadata", None) or {}
            tool_type = str(
                metadata.get("tool_type")
                or metadata.get("type")
                or ""
            ).strip()
            spindle_orientation = str(metadata.get("spindle_orientation") or "").strip()
            return {
                "id": resolved.tool_id,
                "description": resolved.display_name,
                "tool_type": tool_type,
                "spindle_orientation": spindle_orientation,
                "pot_number": getattr(resolved, "pot_number", None),
                "default_pot": str(getattr(resolved, "pot_number", "") or "").strip(),
            }
        except Exception:
            return None

    def _populate_default_pots(self):
        populate_default_pots(self)

    def _open_pot_editor(self):
        open_pot_editor_dialog(self)

    def _open_tool_selector_for_bucket(self, head_key: str, spindle: str):
        self._selector_ctrl.open_tools_for_bucket(head_key, spindle)

    def _open_tool_selector(
        self,
        initial_head: str | None = None,
        initial_spindle: str | None = None,
        initial_assignments: list[dict] | None = None,
    ) -> bool:
        return self._selector_ctrl.open_tools(
            initial_head=initial_head,
            initial_spindle=initial_spindle,
            initial_assignments=initial_assignments,
        )

    def _open_jaw_selector(self, initial_spindle: str | None = None) -> bool:
        return self._selector_ctrl.open_jaws(initial_spindle=initial_spindle)

    def _open_fixture_selector(self, operation_key: str | None = None) -> bool:
        return self._selector_ctrl.open_fixtures(operation_key=operation_key)

    def _detach_active_embedded_selector_widget(self) -> None:
        self._selector_ctrl._detach_active_embedded_widget()

    def _receive_ipc_selector_result(self, payload: dict) -> None:
        self._selector_ctrl.receive_ipc_result(payload)

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
        # For single-spindle profiles: auto-enable OP20 sections when the saved
        # work already contains sub jaw or sub tool data.
        if self.machine_profile.spindle_count == 1:
            _has_sub_jaw = bool(str(self.work.get("sub_jaw_id") or "").strip())
            _has_sub_tools = any(
                bool(self.work.get(self._payload_adapter.tool_assignment_field(hk), []))
                for hk in self._head_profiles
            )
            if _has_sub_jaw or _has_sub_tools:
                self._op20_jaws_enabled = True
                self._op20_tools_enabled = True
                if hasattr(self, "op20_jaws_checkbox"):
                    self.op20_jaws_checkbox.setChecked(True)
                if hasattr(self, "op20_tools_checkbox"):
                    self.op20_tools_checkbox.setChecked(True)
        for head_key in self._head_profiles.keys():
            self._refresh_tool_head_widgets(head_key)
        self._sync_tool_head_view()

    def get_work_data(self) -> dict:
        if hasattr(self, '_sync_mc_tools_operation_payload'):
            try:
                self._sync_mc_tools_operation_payload()
            except Exception:
                pass
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

















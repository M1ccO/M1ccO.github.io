import logging
from pathlib import Path
from typing import Callable
from uuid import UUID

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
from machine_profiles import NTX_MACHINE_PROFILE, is_machining_center, load_profile, resolve_profile_key
from ui.work_editor_support import (
    WorkEditorJawSelectorPanel,
    WorkEditorOrderedToolList,
    WorkEditorPayloadAdapter,
    WorkEditorSelectorHost,
    WorkEditorToolRemoveDropButton,
    apply_fixture_selector_result,
    apply_jaw_selector_result,
    apply_tool_selector_result,
    build_general_tab_ui,
    build_initial_jaw_assignments,
    build_machining_center_zeros_tab_ui,
    build_notes_tab_ui,
    build_spindles_tab_ui,
    build_tools_tab_ui,
    build_zeros_tab_ui,
    collect_unresolved_reference_messages,
    default_pot_for_assignment,
    effective_active_tool_list,
    merge_jaw_refs,
    normalize_selector_head,
    normalize_selector_spindle,
    on_tool_list_interaction,
    open_pot_editor_dialog,
    populate_default_pots,
    refresh_external_refs,
    refresh_tool_head_widgets,
    remove_dragged_tool_assignments,
    selector_initial_tool_assignment_buckets,
    selector_initial_tool_assignments,
    selector_target_ordered_list,
    set_active_tool_list,
    shared_add_tool_comment,
    shared_delete_tool_comment,
    shared_move_tool_down,
    shared_move_tool_up,
    shared_remove_selected_tool,
    show_selector_warning_for_dialog,
    sync_tool_head_view,
    tool_icon_for_type_in_spindle,
    head_label,
    spindle_label,
    toolbar_icon,
    update_shared_tool_actions,
    visible_tool_lists,
    build_spindle_zero_group,
    build_fixture_selector_request,
    build_jaw_selector_request,
    build_tool_selector_request,
    build_embedded_selector_parity_widget,
    dispose_embedded_selector_runtime,
    warmup_embedded_selector_runtime,
    make_zero_axis_input,
    set_coord_combo,
    set_zero_xy_visibility,
)
from config import (
    SHARED_UI_PREFERENCES_PATH,
    STYLE_PATH,
    WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND,
    WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE,
    WORK_EDITOR_SELECTOR_TRACE_PAINT,
)
from shared.services.ui_preferences_service import UiPreferencesService
from shared.selector.payloads import (
    JawSelectionPayload,
    SelectionBatch,
    SpindleKey,
    ToolBucket,
    ToolSelectionPayload,
)
from services.selector_session import (
    InvalidSelectorTransitionError,
    SelectorSessionBusyError,
    SelectorSessionCoordinator,
    SessionState,
    SessionTransition,
    make_file_trace_listener,
)
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
_SELECTOR_TRACE_EVENT_NAMES = {
    QEvent.Show: "Show",
    QEvent.Hide: "Hide",
    QEvent.Paint: "Paint",
    QEvent.UpdateRequest: "UpdateRequest",
    QEvent.Resize: "Resize",
    QEvent.LayoutRequest: "LayoutRequest",
}


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
    _RESIZE_FOR_SELECTOR_MODE = False
    _SELECTOR_TRANSITION_SHIELD_DELAY_MS = 32
    _LOGGER = logging.getLogger(__name__)
    _SELECTORS_TEMPORARILY_DISABLED = False

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
        self._selector_transport_mode = self._resolve_selector_transport_mode()
        self._selector_mode_active = False
        self._selector_open_requested = False
        self._selector_cache_merge_enabled = False
        self._selector_session_serial = 0
        self._selector_session_id: int | None = None
        self._selector_session_uuid: UUID | None = None
        self._selector_session_kind: str = ""
        self._selector_session_phase = "idle"
        self._selector_session_coordinator = self._create_selector_session_coordinator()
        self._host_visual_style_applied = False
        self._zeros_tab_pending_build = True
        self._zeros_tab_built = False
        self._tools_tab_pending_build = True
        self._tools_tab_built = False
        self._selector_restore_state: dict | None = None
        self._selector_hidden_editor_widgets: list[QWidget] = []
        self._selector_transition_shield_pending_hide = False
        self._embedded_selector_host: WorkEditorSelectorHost | None = None
        self._selector_trace_widgets: dict[int, tuple[str, QWidget]] = {}
        self._raw_part_combo_popup_allowed = False
        self._raw_part_combo_popup_window: QWidget | None = None
        self.setUpdatesEnabled(False)
        try:
            setup_tabs(self)
            self.tabs.currentChanged.connect(self._on_tabs_current_changed)

            self._build_general_tab()
            self._build_notes_tab()

            setup_button_row(self)
            self._embedded_selector_host = WorkEditorSelectorHost(
                dialog=self,
                mount_container=self._selector_mount_container,
                auto_close_on_widget_signals=False,
                parent=self,
            )
            self._selector_coordinator().add_batch_listener(self._on_selector_batch_emitted)
            self._selector_coordinator().add_transition_listener(self._on_selector_transition)

            self._load_external_refs()
            self._load_work()
            self._initialize_family_shell()
            try:
                warmup_embedded_selector_runtime(self)
            except Exception:
                self._LOGGER.debug("work_editor.selector warmup skipped", exc_info=True)
                dispose_embedded_selector_runtime(self)

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

    def _create_selector_session_coordinator(self) -> SelectorSessionCoordinator:
        trace_path = Path(__file__).resolve().parent.parent / "temp" / "selector_session_trace.log"
        return SelectorSessionCoordinator(
            name="work-editor",
            trace_listener=make_file_trace_listener(trace_path),
        )

    def _selector_coordinator(self) -> SelectorSessionCoordinator:
        coordinator = getattr(self, "_selector_session_coordinator", None)
        if isinstance(coordinator, SelectorSessionCoordinator):
            return coordinator
        coordinator = self._create_selector_session_coordinator()
        setattr(self, "_selector_session_coordinator", coordinator)
        return coordinator

    def _on_selector_batch_emitted(self, batch: SelectionBatch) -> None:
        self._log_selector_event(
            "session.batch.emitted",
            session_id=str(batch.session_id),
            tools=len(batch.tools),
            jaws=len(batch.jaws),
        )

    @staticmethod
    def _selector_phase_from_state(state: SessionState) -> str:
        if state is SessionState.IDLE:
            return "idle"
        if state is SessionState.OPENING:
            return "requested"
        if state is SessionState.ACTIVE:
            return "active"
        if state is SessionState.CLOSING:
            return "closing"
        if state is SessionState.CANCELLED:
            return "cancelled"
        return "idle"

    def _on_selector_transition(self, transition: SessionTransition) -> None:
        session_uuid = getattr(self, "_selector_session_uuid", None)
        if session_uuid is not None and transition.session_id != session_uuid:
            return
        self._selector_session_phase = self._selector_phase_from_state(transition.to_state)
        self._log_selector_event(
            "session.transition",
            session_uuid=str(transition.session_id),
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
            caller=transition.caller,
        )

    def _initialize_family_shell(self) -> None:
        """Shell hook for family-specific startup sequencing."""
        build_zeros_flag = getattr(self, "_startup_prime_zeros_tab", None)
        if build_zeros_flag is None:
            build_zeros = bool(is_machining_center(self.machine_profile))
        else:
            build_zeros = bool(build_zeros_flag)

        build_tools_flag = getattr(self, "_startup_prime_tools_tab", None)
        build_tools = bool(build_tools_flag) if build_tools_flag is not None else False

        self._prime_startup_tabs(
            build_zeros=build_zeros,
            build_tools=build_tools,
        )

    def _prime_startup_tabs(self, *, build_zeros: bool, build_tools: bool) -> None:
        if not build_zeros and not build_tools:
            return
        was_enabled = self.updatesEnabled()
        if was_enabled:
            self.setUpdatesEnabled(False)
        try:
            if build_zeros:
                self._ensure_zeros_tab_ready()
            if build_tools:
                self._ensure_tools_tab_ready()
        finally:
            if was_enabled:
                self.setUpdatesEnabled(True)

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
        self._sync_selector_overlay_geometry()
        self._sync_selector_transition_shield_geometry()

    def _on_tabs_current_changed(self, index: int) -> None:
        if index == self.tabs.indexOf(self.zeros_tab):
            self._ensure_zeros_tab_ready()
        if index == self.tabs.indexOf(self.tools_tab):
            self._ensure_zeros_tab_ready()
            self._ensure_tools_tab_ready()

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

    def _ensure_zeros_tab_ready(self) -> None:
        if self._zeros_tab_built:
            return
        was_enabled = self.updatesEnabled()
        if was_enabled:
            self.setUpdatesEnabled(False)
        try:
            self._build_zeros_tab()
            self._zeros_tab_built = True
            self._zeros_tab_pending_build = False
            self._apply_work_payload_to_zeros_tab()
            finalize_ui(self)
            self._install_local_event_filters()
        finally:
            if was_enabled:
                self.setUpdatesEnabled(True)

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

    def _ensure_tools_tab_ready(self) -> None:
        if self._tools_tab_built:
            return
        self._ensure_zeros_tab_ready()
        was_enabled = self.updatesEnabled()
        if was_enabled:
            self.setUpdatesEnabled(False)
        try:
            self._build_tools_tab()
            self._tools_tab_built = True
            self._tools_tab_pending_build = False
            self._apply_work_payload_to_tools_tab()
            for head_key in self._head_profiles.keys():
                self._refresh_tool_head_widgets(head_key)
            self._sync_tool_head_view()
            finalize_ui(self)
            self._install_local_event_filters()
        finally:
            if was_enabled:
                self.setUpdatesEnabled(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_selector_overlay_geometry()
        self._sync_selector_transition_shield_geometry()

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

    @staticmethod
    def _resolve_asset_urls(qss: str) -> str:
        assets_dir = (Path(STYLE_PATH).parent.parent / "assets").resolve().as_posix()
        return qss.replace('url("assets/', f'url("{assets_dir}/').replace("url('assets/", f"url('{assets_dir}/")

    def _load_work_editor_style_sheet_from_disk(self) -> str:
        style_dir = Path(STYLE_PATH).parent
        modules_dir = style_dir / "modules"
        merged: list[str] = []
        if modules_dir.is_dir():
            for module_path in sorted(modules_dir.glob("*.qss")):
                try:
                    merged.append(self._resolve_asset_urls(module_path.read_text(encoding="utf-8")))
                except Exception:
                    continue
        if merged:
            return "\n".join(merged)
        try:
            return self._resolve_asset_urls(Path(STYLE_PATH).read_text(encoding="utf-8"))
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
        """Selectors are embedded-only after parity migration completion."""
        return "embedded"

    def _log_selector_event(self, event: str, **fields) -> None:
        payload = {
            "event": event,
            "transport": self._selector_transport_mode,
        }
        payload.update({key: value for key, value in fields.items() if value not in (None, "")})
        self._LOGGER.info("work_editor.selector %s", payload, extra={"selector": payload})

    def _selector_host_uses_overlay_mode(self) -> bool:
        mode = str(WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE or "").strip().lower()
        if mode == "overlay":
            return True
        return False

    def _selector_current_mount_container(self) -> QWidget:
        if self._selector_host_uses_overlay_mode():
            return self._selector_overlay_mount_container
        return self._selector_mount_container

    def _sync_selector_overlay_geometry(self) -> None:
        overlay = getattr(self, "_selector_overlay_container", None)
        normal_page = getattr(self, "_normal_page", None)
        if not isinstance(overlay, QWidget) or not isinstance(normal_page, QWidget):
            return
        overlay.setGeometry(normal_page.rect())
        overlay.raise_()

    def _set_selector_overlay_visible(self, visible: bool) -> None:
        overlay = getattr(self, "_selector_overlay_container", None)
        if not isinstance(overlay, QWidget):
            return
        self._sync_selector_overlay_geometry()
        overlay.setVisible(bool(visible))
        if visible:
            overlay.raise_()

    def _set_normal_editor_surface_hidden_for_selector(self, hidden: bool) -> None:
        widgets: list[QWidget] = []
        tabs = getattr(self, "tabs", None)
        if isinstance(tabs, QWidget):
            widgets.append(tabs)
        dialog_buttons = getattr(self, "_dialog_buttons", None)
        if isinstance(dialog_buttons, QWidget):
            widgets.append(dialog_buttons)

        if hidden:
            retained: list[QWidget] = []
            for widget in widgets:
                if not widget.isHidden():
                    widget.setVisible(False)
                    retained.append(widget)
            self._selector_hidden_editor_widgets = retained
            return

        for widget in getattr(self, "_selector_hidden_editor_widgets", []):
            if isinstance(widget, QWidget):
                widget.setVisible(True)
        self._selector_hidden_editor_widgets = []

    def _selector_session_uses_transition_shield(self) -> bool:
        return self._selector_host_uses_overlay_mode()

    def _sync_selector_transition_shield_geometry(self) -> None:
        shield = getattr(self, "_selector_transition_shield", None)
        root_stack = getattr(self, "_root_stack", None)
        if not isinstance(shield, QWidget) or not isinstance(root_stack, QWidget):
            return
        shield.setGeometry(root_stack.geometry())
        shield.raise_()

    def _hide_selector_transition_shield(self) -> None:
        shield = getattr(self, "_selector_transition_shield", None)
        if not isinstance(shield, QWidget):
            return
        self._selector_transition_shield_pending_hide = False
        shield.setVisible(False)

    def _set_selector_transition_shield_visible(self, visible: bool) -> None:
        shield = getattr(self, "_selector_transition_shield", None)
        if not isinstance(shield, QWidget):
            return
        self._sync_selector_transition_shield_geometry()
        if visible:
            self._selector_transition_shield_pending_hide = True
            shield.setVisible(True)
            shield.raise_()
            return
        self._hide_selector_transition_shield()

    def _install_selector_transition_trace_filters(self) -> None:
        if not WORK_EDITOR_SELECTOR_TRACE_PAINT:
            self._selector_trace_widgets = {}
            return
        trace_targets = {
            "dialog": self,
            "root_stack": getattr(self, "_root_stack", None),
            "normal_page": getattr(self, "_normal_page", None),
            "selector_page": getattr(self, "_selector_page", None),
            "selector_mount_container": getattr(self, "_selector_mount_container", None),
            "selector_overlay_container": getattr(self, "_selector_overlay_container", None),
            "selector_overlay_mount_container": getattr(self, "_selector_overlay_mount_container", None),
            "selector_transition_shield": getattr(self, "_selector_transition_shield", None),
        }
        watched: dict[int, tuple[str, QWidget]] = {}
        for label, widget in trace_targets.items():
            if not isinstance(widget, QWidget):
                continue
            widget.installEventFilter(self)
            watched[id(widget)] = (label, widget)
        self._selector_trace_widgets = watched
        self._log_selector_event(
            "trace.enabled",
            diagnostic_kind=WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND,
            host_diagnostic_mode=WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE,
            targets=list(trace_targets.keys()),
        )

    def _trace_selector_surface_event(self, obj, event) -> None:
        if not WORK_EDITOR_SELECTOR_TRACE_PAINT:
            return
        watched = getattr(self, "_selector_trace_widgets", {})
        entry = watched.get(id(obj))
        if entry is None:
            return
        event_name = _SELECTOR_TRACE_EVENT_NAMES.get(event.type())
        if event_name is None:
            return
        label, widget = entry
        geometry = widget.geometry()
        self._log_selector_event(
            "surface.event",
            watched=label,
            qt_event=event_name,
            visible=bool(widget.isVisible()),
            updates_enabled=bool(widget.updatesEnabled()),
            current_page=(
                "overlay"
                if self._selector_host_uses_overlay_mode() and getattr(self, "_selector_overlay_container", None) is not None
                and self._selector_overlay_container.isVisible()
                else "selector"
                if getattr(self, "_root_stack", None) is not None
                and getattr(self, "_selector_page", None) is not None
                and self._root_stack.currentWidget() is self._selector_page
                else "normal"
            ),
            x=geometry.x(),
            y=geometry.y(),
            width=geometry.width(),
            height=geometry.height(),
        )

    def _is_embedded_selector_mode_enabled(self) -> bool:
        return True

    def _begin_selector_session_request(self, *, kind: str) -> int | None:
        host = self._embedded_selector_host
        if self._selector_session_id is not None or self._selector_mode_active:
            self._LOGGER.warning(
                "work_editor.selector request ignored while session is active kind=%s session_id=%s phase=%s",
                kind,
                self._selector_session_id,
                self._selector_session_phase,
            )
            return None
        if host is not None and host.active_widget is not None:
            self._LOGGER.warning("work_editor.selector request ignored because host still has an active widget kind=%s", kind)
            return None
        coordinator = self._selector_coordinator()
        try:
            session_uuid = coordinator.request_open(caller=f"request_open:{kind}")
        except SelectorSessionBusyError:
            self._LOGGER.warning(
                "work_editor.selector request rejected by coordinator kind=%s state=%s",
                kind,
                coordinator.state.value,
            )
            return None

        self._selector_session_serial += 1
        self._selector_session_id = self._selector_session_serial
        self._selector_session_uuid = session_uuid
        self._selector_session_kind = str(kind or "").strip().lower()
        self._selector_session_phase = "requested"
        self._selector_open_requested = True
        self._log_selector_event(
            "session.requested",
            kind=kind,
            session_id=self._selector_session_id,
            session_uuid=str(session_uuid),
            diagnostic_kind=WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND,
        )
        return self._selector_session_id

    def _mark_selector_session_phase(self, session_id: int, phase: str) -> bool:
        if session_id != self._selector_session_id:
            self._LOGGER.warning(
                "work_editor.selector ignoring stale session transition session_id=%s current=%s phase=%s",
                session_id,
                self._selector_session_id,
                phase,
            )
            return False
        self._selector_session_phase = phase
        return True

    def _begin_selector_session_close(
        self,
        *,
        session_id: int,
        reason: str,
        batch: SelectionBatch | None = None,
    ) -> bool:
        if not self._mark_selector_session_phase(session_id, "closing"):
            return False
        coordinator = self._selector_coordinator()
        try:
            if batch is not None:
                coordinator.confirm(batch, caller=f"close:{reason}")
            else:
                coordinator.cancel(caller=f"close:{reason}")
        except InvalidSelectorTransitionError:
            self._LOGGER.warning(
                "work_editor.selector close rejected by coordinator session_id=%s reason=%s state=%s",
                session_id,
                reason,
                coordinator.state.value,
            )
            return False
        self._log_selector_event("session.closing", session_id=session_id, reason=reason)
        return True

    def _clear_selector_session_request(self, session_id: int | None = None) -> None:
        if session_id is not None and session_id != self._selector_session_id:
            return
        self._selector_session_id = None
        self._selector_session_uuid = None
        self._selector_session_kind = ""
        self._selector_session_phase = "idle"
        self._selector_open_requested = False

    def _capture_selector_restore_state(self) -> dict:
        return {
            "geometry": self.geometry(),
            "minimum_size": self.minimumSize(),
            "maximum_size": self.maximumSize(),
        }

    def _restore_from_selector_state(self) -> None:
        state = self._selector_restore_state
        if not isinstance(state, dict):
            return

        min_size = state.get("minimum_size")
        if isinstance(min_size, QSize):
            self.setMinimumSize(min_size)

        max_size = state.get("maximum_size")
        if isinstance(max_size, QSize):
            self.setMaximumSize(max_size)

        geometry = state.get("geometry")
        if geometry is not None:
            self.setGeometry(geometry)

    def _enter_selector_mode(self) -> None:
        if self._selector_mode_active:
            return
        if not isinstance(getattr(self, "_root_stack", None), QStackedWidget):
            return
        if not getattr(self, "_selector_open_requested", True):
            self._LOGGER.warning("work_editor.selector_mode ignored because no selector request is active")
            return

        # Batch page switch + resize to avoid intermediate repaint flash.
        was_enabled = self.updatesEnabled()
        if was_enabled:
            self.setUpdatesEnabled(False)
        try:
            self._selector_restore_state = self._capture_selector_restore_state()
            self._selector_mode_active = True
            if self._selector_session_id is not None:
                self._selector_session_phase = "active"
            self._log_selector_event(
                "selector_mode.enter.begin",
                session_id=self._selector_session_id,
                diagnostic_kind=WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND,
                host_diagnostic_mode=WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE,
            )
            if self._selector_session_uses_transition_shield():
                self._set_selector_transition_shield_visible(True)
            if self._selector_host_uses_overlay_mode():
                self._set_normal_editor_surface_hidden_for_selector(True)
                self._set_selector_overlay_visible(True)
            else:
                self._root_stack.setCurrentWidget(self._selector_page)
            if self._RESIZE_FOR_SELECTOR_MODE:
                self._expand_for_selector_mode()
        finally:
            if was_enabled:
                self.setUpdatesEnabled(True)
        self._log_selector_event(
            "selector_mode.enter.end",
            session_id=self._selector_session_id,
            current_page="overlay" if self._selector_host_uses_overlay_mode() else "selector",
        )
        if self._selector_transition_shield_pending_hide:
            QTimer.singleShot(self._SELECTOR_TRANSITION_SHIELD_DELAY_MS, self._hide_selector_transition_shield)

    def _exit_selector_mode(self) -> None:
        session_id = self._selector_session_id
        session_phase = self._selector_session_phase
        coordinator = self._selector_coordinator()

        was_enabled = self.updatesEnabled()
        if was_enabled:
            self.setUpdatesEnabled(False)
        try:
            if self._selector_mode_active and isinstance(getattr(self, "_root_stack", None), QStackedWidget):
                self._log_selector_event(
                    "selector_mode.exit.begin",
                    session_id=session_id,
                    current_page="overlay" if self._selector_host_uses_overlay_mode() else "selector",
                )
                if self._selector_host_uses_overlay_mode():
                    self._set_selector_overlay_visible(False)
                    self._set_normal_editor_surface_hidden_for_selector(False)
                else:
                    self._root_stack.setCurrentWidget(self._normal_page)
                if self._selector_session_uses_transition_shield():
                    self._set_selector_transition_shield_visible(False)

            if self._selector_mode_active:
                self._restore_from_selector_state()
            self._selector_restore_state = None
            self._selector_mode_active = False
            try:
                if coordinator.state in (SessionState.CLOSING, SessionState.CANCELLED):
                    coordinator.mark_teardown_complete(caller="host.exit")
                elif coordinator.state in (SessionState.OPENING, SessionState.ACTIVE):
                    coordinator.force_shutdown(caller="host.exit")
            except Exception:
                self._LOGGER.debug("work_editor.selector coordinator teardown failed", exc_info=True)
            self._clear_selector_session_request(session_id)
        finally:
            if was_enabled:
                self.setUpdatesEnabled(True)
        if session_id is not None:
            self._log_selector_event("session.closed", session_id=session_id, previous_phase=session_phase)

    def _expand_for_selector_mode(self) -> None:
        target_width = max(self.width() + self._SELECTOR_EXPAND_DELTA, self._SELECTOR_MIN_WIDTH)
        screen = self.screen()
        available = screen.availableGeometry() if screen is not None else None
        if available is not None:
            target_width = min(target_width, available.width())

        target_height = self.height()
        if available is not None:
            target_height = min(target_height, available.height())

        self.resize(target_width, target_height)
        if available is not None:
            geom = self.geometry()
            x = min(max(geom.x(), available.left()), available.right() - geom.width() + 1)
            y = min(max(geom.y(), available.top()), available.bottom() - geom.height() + 1)
            self.move(x, y)

    def _install_local_event_filters(self) -> None:
        """Scope event filtering to this dialog tree (no app-wide filter)."""
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)
        self._install_selector_transition_trace_filters()

    def _close_embedded_selector_host_widget(self) -> None:
        host = getattr(self, "_embedded_selector_host", None)
        if host is None:
            return
        was_enabled = self.updatesEnabled()
        if was_enabled:
            self.setUpdatesEnabled(False)
        try:
            host.close_active_widget()
            self._exit_selector_mode()
        finally:
            if was_enabled:
                self.setUpdatesEnabled(True)

    def _mount_selector_widget_for_session(self, widget: QWidget, mount_container: QWidget) -> None:
        """Prepare and mount selector widget so first reveal is already stable."""
        host = self._embedded_selector_host
        if host is None:
            return
        was_enabled = self.updatesEnabled()
        if was_enabled:
            self.setUpdatesEnabled(False)
        try:
            widget.setVisible(False)
            ensure_polished = getattr(widget, "ensurePolished", None)
            if callable(ensure_polished):
                ensure_polished()

            host.open_widget(widget, mount_container=mount_container)
            self._enter_selector_mode()

            widget_layout = widget.layout()
            if widget_layout is not None:
                widget_layout.activate()
            mount_layout = mount_container.layout()
            if mount_layout is not None:
                mount_layout.activate()
            widget.updateGeometry()
            mount_container.updateGeometry()
            mount_parent = mount_container.parentWidget()
            if mount_parent is not None:
                mount_parent.updateGeometry()
            widget.setVisible(True)
            self._log_selector_event(
                "host.open.prepared",
                dialog_updates_enabled=bool(self.updatesEnabled()),
            )
        finally:
            if was_enabled:
                self.setUpdatesEnabled(True)

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
        host = getattr(self, "_embedded_selector_host", None)
        if host is not None:
            try:
                self._close_embedded_selector_host_widget()
            except Exception:
                self._LOGGER.debug("Failed closing active embedded selector during dialog shutdown", exc_info=True)
        try:
            self._selector_coordinator().force_shutdown(caller="dialog.closeEvent")
        except Exception:
            self._LOGGER.debug("Failed forcing selector coordinator shutdown during dialog close", exc_info=True)
        dispose_embedded_selector_runtime(self)
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
        if not self._tools_tab_built:
            return
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
        if not self._tools_tab_built:
            return
        refresh_tool_head_widgets(self, head_key)

    def _sync_tool_head_view(self):
        if not self._tools_tab_built:
            return
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

        tool_uid = assignment.get("tool_uid", assignment.get("uid"))
        try:
            if tool_uid is not None and str(tool_uid).strip():
                ref = self.draw_service.get_tool_ref_by_uid(tool_uid)
                if isinstance(ref, dict) and str(ref.get("id") or "").strip():
                    return ref
        except Exception:
            pass

        tool_id = str(assignment.get("tool_id") or assignment.get("id") or "").strip()
        if tool_id:
            try:
                ref = self.draw_service.get_tool_ref(tool_id)
                if isinstance(ref, dict) and str(ref.get("id") or "").strip():
                    return ref
            except Exception:
                pass

        resolved = self._resolve_tool_ref_via_resolver(tool_id)
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
            tool_type = ""
            icon_key = str(getattr(resolved, "icon_key", "") or "").strip()
            if icon_key.startswith("tool/"):
                # Resolver icon keys are normalized lowercase identifiers, not
                # the canonical Work Editor tool_type values needed for icon lookup.
                tool_type = ""
            return {
                "id": resolved.tool_id,
                "description": resolved.display_name,
                "tool_type": tool_type,
                "default_pot": str(getattr(resolved, "pot_number", "") or "").strip(),
            }
        except Exception:
            return None

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
        ordered_list = selector_target_ordered_list(self, target_head)
        return selector_initial_tool_assignments(ordered_list, spindle)

    def _selector_initial_tool_assignment_buckets(self) -> dict[str, list[dict]]:
        return selector_initial_tool_assignment_buckets(
            self._tool_column_lists,
            tuple(self._head_profiles.keys()),
            tuple(self._spindle_profiles.keys()),
        )

    def _open_tool_selector(
        self,
        initial_head: str | None = None,
        initial_spindle: str | None = None,
        initial_assignments: list[dict] | None = None,
    ) -> bool:
        if self._SELECTORS_TEMPORARILY_DISABLED:
            show_selector_warning_for_dialog(
                self,
                self._t("work_editor.selector.disabled.title", "Selectors temporarily disabled"),
                self._t(
                    "work_editor.selector.disabled.body",
                    "Tool/Jaw/Fixture selectors are temporarily disabled for troubleshooting.",
                ),
            )
            return False
        if hasattr(self, '_sync_mc_tools_operation_payload'):
            try:
                self._sync_mc_tools_operation_payload()
            except Exception:
                pass
        request = build_tool_selector_request(
            self,
            initial_head=initial_head,
            initial_spindle=initial_spindle,
            initial_assignments=initial_assignments,
        )
        self._log_selector_event(
            "open",
            kind="tools",
            head=request.get("head"),
            spindle=request.get("spindle"),
        )
        return self._open_embedded_selector_session(
            kind=str(request.get("kind") or "tools"),
            head=str(request.get("head") or ""),
            spindle=str(request.get("spindle") or ""),
            initial_assignments=list(request.get("initial_assignments") or []),
            initial_assignment_buckets=dict(request.get("initial_assignment_buckets") or {}),
        )

    def _selector_initial_jaw_assignments(self) -> list[dict]:
        return build_initial_jaw_assignments(self)

    def _open_jaw_selector(self, initial_spindle: str | None = None) -> bool:
        if self._SELECTORS_TEMPORARILY_DISABLED:
            show_selector_warning_for_dialog(
                self,
                self._t("work_editor.selector.disabled.title", "Selectors temporarily disabled"),
                self._t(
                    "work_editor.selector.disabled.body",
                    "Tool/Jaw/Fixture selectors are temporarily disabled for troubleshooting.",
                ),
            )
            return False
        request = build_jaw_selector_request(self, initial_spindle=initial_spindle)
        self._log_selector_event("open", kind="jaws", spindle=request.get("spindle"))
        return self._open_embedded_selector_session(
            kind=str(request.get("kind") or "jaws"),
            spindle=str(request.get("spindle") or ""),
            initial_assignments=list(request.get("initial_assignments") or []),
        )

    def _open_fixture_selector(self, operation_key: str | None = None) -> bool:
        if self._SELECTORS_TEMPORARILY_DISABLED:
            show_selector_warning_for_dialog(
                self,
                self._t("work_editor.selector.disabled.title", "Selectors temporarily disabled"),
                self._t(
                    "work_editor.selector.disabled.body",
                    "Tool/Jaw/Fixture selectors are temporarily disabled for troubleshooting.",
                ),
            )
            return False
        request = build_fixture_selector_request(self, operation_key=operation_key)
        target_key = str((request.get("follow_up") or {}).get("target_key") or "").strip()
        self._log_selector_event("open", kind="fixtures", target_key=target_key)
        return self._open_embedded_selector_session(
            kind=str(request.get("kind") or "fixtures"),
            follow_up=dict(request.get("follow_up") or {}),
            initial_assignments=list(request.get("initial_assignments") or []),
            initial_assignment_buckets=dict(request.get("initial_assignment_buckets") or {}),
        )

    def _open_embedded_selector_session(
        self,
        *,
        kind: str,
        head: str | None = None,
        spindle: str | None = None,
        follow_up: dict | None = None,
        initial_assignments: list[dict] | None = None,
        initial_assignment_buckets: dict[str, list[dict]] | None = None,
    ) -> bool:
        """Phase-3 shared-widget embedded path to validate mode and geometry flow."""
        host = self._embedded_selector_host
        if host is None:
            return False
        kind_key = str(kind or "").strip().lower()
        if not self.isVisible():
            self._LOGGER.warning("work_editor.selector blocked before dialog is visible kind=%s", kind_key)
            return False
        session_id = self._begin_selector_session_request(kind=kind_key)
        if session_id is None:
            return False

        request = {
            "kind": kind_key,
            "head": str(head or ""),
            "spindle": str(spindle or ""),
            "target_key": str((follow_up or {}).get("target_key") or ""),
        }

        def _finalize_embedded_submit(payload: dict, req: dict = request, current_session_id: int = session_id) -> None:
            try:
                batch = self._build_selection_batch(req, payload)
            except Exception:
                self._LOGGER.exception("work_editor.selector failed to build SelectionBatch")
                return
            if not self._begin_selector_session_close(
                session_id=current_session_id,
                reason="submit",
                batch=batch,
            ):
                return
            try:
                self._handle_embedded_selector_submit(req, payload)
            except Exception:
                self._LOGGER.exception(
                    "work_editor.selector submit handling failed kind=%s session_id=%s",
                    kind_key,
                    current_session_id,
                )
            finally:
                self._close_embedded_selector_host_widget()

        def _finalize_embedded_cancel(current_session_id: int = session_id) -> None:
            if not self._begin_selector_session_close(session_id=current_session_id, reason="cancel"):
                return
            try:
                self._handle_embedded_selector_cancel()
            except Exception:
                self._LOGGER.exception(
                    "work_editor.selector cancel handling failed kind=%s session_id=%s",
                    kind_key,
                    current_session_id,
                )
            finally:
                self._close_embedded_selector_host_widget()

        try:
            container = build_embedded_selector_parity_widget(
                self,
                mount_container=self._selector_current_mount_container(),
                kind=kind_key,
                head=head,
                spindle=spindle,
                follow_up=follow_up,
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
                on_submit=_finalize_embedded_submit,
                on_cancel=_finalize_embedded_cancel,
            )
        except Exception as exc:
            self._LOGGER.exception("Failed to open embedded selector kind=%s", kind_key)
            self._clear_selector_session_request(session_id)
            dispose_embedded_selector_runtime(self)
            show_selector_warning_for_dialog(
                self,
                self._t("work_editor.selector.open_failed.title", "Selector unavailable"),
                self._t(
                    "work_editor.selector.open_failed.body",
                    "Could not open embedded selector: {error}",
                    error=str(exc),
                ),
            )
            return False
        if container is None:
            self._clear_selector_session_request(session_id)
            return False
        container.setProperty("selectorContext", True)
        container.setProperty("selectorSessionId", session_id)
        self._mark_selector_session_phase(session_id, "mounting")

        self._log_selector_event(
            "open.embedded",
            kind=kind,
            head=head,
            spindle=spindle,
            session_id=session_id,
            target_key=str((follow_up or {}).get("target_key") or ""),
        )
        mount_container = self._selector_current_mount_container()
        self._mount_selector_widget_for_session(container, mount_container)
        try:
            self._selector_coordinator().mark_mount_complete(caller=f"mount:{kind_key}")
        except InvalidSelectorTransitionError:
            self._LOGGER.warning(
                "work_editor.selector mount completion rejected kind=%s session_id=%s state=%s",
                kind_key,
                session_id,
                self._selector_coordinator().state.value,
            )
            dispose_embedded_selector_runtime(self)
            self._close_embedded_selector_host_widget()
            self._clear_selector_session_request(session_id)
            return False
        if not self._selector_mode_active:
            self._LOGGER.warning(
                "work_editor.selector failed to enter selector mode after mounting kind=%s session_id=%s",
                kind_key,
                session_id,
            )
            dispose_embedded_selector_runtime(self)
            self._close_embedded_selector_host_widget()
            self._clear_selector_session_request(session_id)
            return False
        return True

    @staticmethod
    def _tool_bucket_for_spindle(spindle: str) -> ToolBucket:
        normalized_spindle = normalize_selector_spindle(spindle)
        return ToolBucket.SUB if normalized_spindle == "sub" else ToolBucket.MAIN

    def _build_selection_batch(self, request: dict, payload: dict) -> SelectionBatch:
        session_uuid = self._selector_session_uuid or self._selector_coordinator().session_id
        if session_uuid is None:
            raise RuntimeError("cannot build SelectionBatch without live session UUID")

        kind = str((payload or {}).get("kind") or request.get("kind") or "").strip().lower()
        source_rev_raw = (payload or {}).get("source_library_rev", 0)
        try:
            source_rev = max(int(source_rev_raw), 0)
        except Exception:
            source_rev = 0

        selected_items = [item for item in list((payload or {}).get("selected_items") or []) if isinstance(item, dict)]
        tool_entries: list[ToolSelectionPayload] = []
        jaw_entries: list[JawSelectionPayload] = []

        if kind == "tools":
            seen_tools: set[tuple[ToolBucket, str, str]] = set()
            buckets_by_target = (payload or {}).get("assignment_buckets_by_target")
            if isinstance(buckets_by_target, dict) and buckets_by_target:
                for raw_target, raw_bucket_items in buckets_by_target.items():
                    target = str(raw_target or "").strip()
                    if ":" not in target:
                        continue
                    head_key_raw, spindle_raw = target.split(":", 1)
                    head_key = normalize_selector_head(head_key_raw)
                    bucket = self._tool_bucket_for_spindle(spindle_raw)
                    for item in list(raw_bucket_items or []):
                        if not isinstance(item, dict):
                            continue
                        tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
                        if not tool_id:
                            continue
                        dedupe_key = (bucket, head_key, tool_id)
                        if dedupe_key in seen_tools:
                            continue
                        seen_tools.add(dedupe_key)
                        tool_entries.append(
                            ToolSelectionPayload(
                                bucket=bucket,
                                head_key=head_key,
                                tool_id=tool_id,
                                source_library_rev=source_rev,
                            )
                        )
            else:
                head_key = normalize_selector_head(request.get("head"))
                bucket = self._tool_bucket_for_spindle(str(request.get("spindle") or ""))
                for item in selected_items:
                    tool_id = str(item.get("tool_id") or item.get("id") or "").strip()
                    if not tool_id:
                        continue
                    dedupe_key = (bucket, head_key, tool_id)
                    if dedupe_key in seen_tools:
                        continue
                    seen_tools.add(dedupe_key)
                    tool_entries.append(
                        ToolSelectionPayload(
                            bucket=bucket,
                            head_key=head_key,
                            tool_id=tool_id,
                            source_library_rev=source_rev,
                        )
                    )

        if kind == "jaws":
            default_spindle = normalize_selector_spindle(request.get("spindle"))
            seen_jaws: set[tuple[SpindleKey, str]] = set()
            for item in selected_items:
                jaw_id = str(item.get("jaw_id") or item.get("id") or "").strip()
                if not jaw_id:
                    continue
                spindle_raw = str(item.get("spindle") or item.get("slot") or default_spindle)
                spindle_key = SpindleKey.SUB if normalize_selector_spindle(spindle_raw) == "sub" else SpindleKey.MAIN
                dedupe_key = (spindle_key, jaw_id)
                if dedupe_key in seen_jaws:
                    continue
                seen_jaws.add(dedupe_key)
                jaw_entries.append(
                    JawSelectionPayload(
                        spindle=spindle_key,
                        jaw_id=jaw_id,
                        source_library_rev=source_rev,
                    )
                )

        return SelectionBatch(
            session_id=session_uuid,
            tools=tuple(tool_entries),
            jaws=tuple(jaw_entries),
        )

    def _handle_embedded_selector_submit(self, request: dict, payload: dict) -> None:
        kind = str((payload or {}).get("kind") or request.get("kind") or "").strip().lower()
        selected_items = list((payload or {}).get("selected_items") or [])

        selector_request = {
            "head": request.get("head") or (payload or {}).get("selector_head") or "",
            "spindle": request.get("spindle") or (payload or {}).get("selector_spindle") or "",
            "target_key": request.get("target_key") or (payload or {}).get("target_key") or "",
            "assignment_buckets_by_target": (payload or {}).get("assignment_buckets_by_target") or {},
        }

        applied = False
        if kind == "tools":
            applied = apply_tool_selector_result(self, selector_request, selected_items)
        elif kind == "jaws":
            applied = apply_jaw_selector_result(self, selector_request, selected_items)
        elif kind == "fixtures":
            applied = apply_fixture_selector_result(self, selector_request, selected_items)

        self._log_selector_event(
            "submit.embedded.applied",
            kind=kind,
            applied=bool(applied),
            selected_count=len(selected_items),
        )

    def _handle_embedded_selector_cancel(self) -> None:
        self._log_selector_event("cancel.embedded.request")

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
        if self._tools_tab_built:
            for head_key in self._head_profiles.keys():
                self._refresh_tool_head_widgets(head_key)
            self._sync_tool_head_view()

    def get_work_data(self) -> dict:
        if not is_machining_center(self.machine_profile):
            self._ensure_zeros_tab_ready()
            self._ensure_tools_tab_ready()
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

















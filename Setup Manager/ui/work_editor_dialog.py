import logging
from pathlib import Path
from typing import Callable

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
    apply_fixture_selection_to_operation,
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
    current_tools_head_value,
    default_jaw_selector_spindle,
    default_pot_for_assignment,
    default_selector_head,
    default_selector_spindle,
    effective_active_tool_list,
    jaw_ref_key,
    merge_jaw_refs,
    merge_tool_refs,
    normalize_selector_head,
    normalize_selector_spindle,
    on_tool_list_interaction,
    open_pot_editor_dialog,
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
    build_fixture_selector_request,
    build_jaw_selector_request,
    build_tool_selector_request,
    build_embedded_selector_parity_widget,
    release_tool_library_namespace_aliases,
    warmup_embedded_selector_runtime,
    make_zero_axis_input,
    set_coord_combo,
    set_zero_xy_visibility,
)
from config import (
    SHARED_UI_PREFERENCES_PATH,
    STYLE_PATH,
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
    WORK_COORDINATES = WORK_COORDINATES
    _SELECTOR_MIN_WIDTH = 1100
    _SELECTOR_EXPAND_DELTA = 480
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
        self._selector_session_serial = 0
        self._selector_session_id: int | None = None
        self._selector_session_phase = "idle"
        self._host_visual_style_applied = False
        self._zeros_tab_pending_build = True
        self._zeros_tab_built = False
        self._tools_tab_pending_build = True
        self._tools_tab_built = False
        self._selector_restore_state: dict | None = None
        self._embedded_selector_host: WorkEditorSelectorHost | None = None
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
                enter_selector_mode=self._enter_selector_mode,
                exit_selector_mode=self._exit_selector_mode,
                auto_close_on_widget_signals=False,
                parent=self,
            )

            self._load_external_refs()
            self._load_work()
            self._initialize_family_shell()
            try:
                warmup_embedded_selector_runtime(self)
            except Exception:
                self._LOGGER.debug("work_editor.selector warmup skipped", exc_info=True)

            # Apply stylesheet after the full initial hierarchy exists so the
            # first visible paint is not chasing late subtree polish work.
            self._apply_host_visual_style()
            self._prime_selector_host_surface()

            # Keep dialog actions visually consistent with secondary gray buttons.
            self._set_secondary_button_theme()

            finalize_ui(self)
            self._close_transient_combo_popups()
            self._setup_raw_part_combo_popup_guard()
            self._install_local_event_filters()
        finally:
            self.setUpdatesEnabled(True)

    def _prime_selector_host_surface(self) -> None:
        """Prime selector host subtree while still in startup batch mode."""
        selector_page = getattr(self, "_selector_page", None)
        mount = getattr(self, "_selector_mount_container", None)
        root_stack = getattr(self, "_root_stack", None)

        for widget in (root_stack, selector_page, mount):
            if isinstance(widget, QWidget):
                widget.setAttribute(Qt.WA_StyledBackground, True)
                ensure_polished = getattr(widget, "ensurePolished", None)
                if callable(ensure_polished):
                    ensure_polished()
                layout = widget.layout()
                if layout is not None:
                    layout.activate()

    def _initialize_family_shell(self) -> None:
        """Shell hook for family-specific startup sequencing."""
        self._prime_startup_tabs(
            build_zeros=bool(getattr(self, "_startup_prime_zeros_tab", False)),
            build_tools=bool(getattr(self, "_startup_prime_tools_tab", False)),
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
            ordered_list = self._ordered_tool_lists.get(head_key)
            if ordered_list is not None:
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
        for widget in (self, getattr(self, "_normal_page", None), getattr(self, "_selector_page", None)):
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

        self._selector_session_serial += 1
        self._selector_session_id = self._selector_session_serial
        self._selector_session_phase = "requested"
        self._selector_open_requested = True
        self._log_selector_event(
            "session.requested",
            kind=kind,
            session_id=self._selector_session_id,
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

    def _begin_selector_session_close(self, *, session_id: int, reason: str) -> bool:
        if not self._mark_selector_session_phase(session_id, "closing"):
            return False
        self._log_selector_event("session.closing", session_id=session_id, reason=reason)
        return True

    def _clear_selector_session_request(self, session_id: int | None = None) -> None:
        if session_id is not None and session_id != self._selector_session_id:
            return
        self._selector_session_id = None
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
            self._root_stack.setCurrentWidget(self._selector_page)
            self._expand_for_selector_mode()
        finally:
            if was_enabled:
                self.setUpdatesEnabled(True)

    def _exit_selector_mode(self) -> None:
        session_id = self._selector_session_id
        session_phase = self._selector_session_phase

        was_enabled = self.updatesEnabled()
        if was_enabled:
            self.setUpdatesEnabled(False)
        try:
            if self._selector_mode_active and isinstance(getattr(self, "_root_stack", None), QStackedWidget):
                self._root_stack.setCurrentWidget(self._normal_page)

            if self._selector_mode_active:
                self._restore_from_selector_state()
            self._selector_restore_state = None
            self._selector_mode_active = False
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

    def eventFilter(self, obj, event):
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
        release_tool_library_namespace_aliases(self)
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

    def _apply_fixture_selector_result(self, request: dict, selected_items: list[dict]) -> bool:
        return apply_fixture_selector_result(self, request, selected_items)

    def _apply_jaw_selector_result(self, request: dict, selected_items: list[dict]) -> bool:
        return apply_jaw_selector_result(self, request, selected_items)

    def _apply_fixture_selection_to_operation(self, operation_key: str, selected_items: list[dict]) -> bool:
        return apply_fixture_selection_to_operation(self, operation_key, selected_items)

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
        if self._SELECTORS_TEMPORARILY_DISABLED:
            self._show_selector_warning(
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
            self._show_selector_warning(
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
            self._show_selector_warning(
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
            if not self._begin_selector_session_close(session_id=current_session_id, reason="submit"):
                return
            self._handle_embedded_selector_submit(req, payload)
            release_tool_library_namespace_aliases(self)
            host.close_active_widget()

        def _finalize_embedded_cancel(current_session_id: int = session_id) -> None:
            if not self._begin_selector_session_close(session_id=current_session_id, reason="cancel"):
                return
            self._handle_embedded_selector_cancel()
            release_tool_library_namespace_aliases(self)
            host.close_active_widget()

        try:
            container = build_embedded_selector_parity_widget(
                self,
                mount_container=self._selector_mount_container,
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
            release_tool_library_namespace_aliases(self)
            self._show_selector_warning(
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
        host.open_widget(container)
        if not self._selector_mode_active:
            self._LOGGER.warning(
                "work_editor.selector failed to enter selector mode after mounting kind=%s session_id=%s",
                kind_key,
                session_id,
            )
            release_tool_library_namespace_aliases(self)
            host.close_active_widget()
            self._clear_selector_session_request(session_id)
            return False
        return True

    def _handle_embedded_selector_submit(self, request: dict, payload: dict) -> None:
        kind = str((payload or {}).get("kind") or request.get("kind") or "").strip().lower()
        selected_items = list((payload or {}).get("selected_items") or [])

        selector_request = {
            "head": request.get("head") or (payload or {}).get("selector_head") or "",
            "spindle": request.get("spindle") or (payload or {}).get("selector_spindle") or "",
            "target_key": request.get("target_key") or (payload or {}).get("target_key") or "",
        }

        applied = False
        if kind == "tools":
            applied = self._apply_tool_selector_result(selector_request, selected_items)
        elif kind == "jaws":
            applied = self._apply_jaw_selector_result(selector_request, selected_items)
        elif kind == "fixtures":
            applied = self._apply_fixture_selector_result(selector_request, selected_items)

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

















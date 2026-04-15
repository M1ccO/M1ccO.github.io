from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from shared.ui.helpers.editor_helpers import ResponsiveColumnsHost, apply_shared_checkbox_style
except ModuleNotFoundError:
    from editor_helpers import ResponsiveColumnsHost, apply_shared_checkbox_style
from machine_profiles import is_machining_center
from .machining_center import build_machining_center_zeros_tab_ui


def _setup_jaw_selectors(
    dialog: Any,
    *,
    jaw_selector_panel_cls: type,
    main_title: str,
    sub_title: str,
    main_filter_placeholder: tuple[str, str] | None = None,
    sub_filter_placeholder: tuple[str, str] | None = None,
    main_spindle_side_filter: str | None = None,
    sub_spindle_side_filter: str | None = None,
) -> None:
    """Create and register jaw selector panels with machine-profile visibility."""
    main_kwargs = {"translate": dialog._t}
    sub_kwargs = {"translate": dialog._t}
    if main_filter_placeholder:
        main_kwargs["filter_placeholder_key"] = main_filter_placeholder[0]
        main_kwargs["filter_placeholder_default"] = main_filter_placeholder[1]
    if sub_filter_placeholder:
        sub_kwargs["filter_placeholder_key"] = sub_filter_placeholder[0]
        sub_kwargs["filter_placeholder_default"] = sub_filter_placeholder[1]
    if main_spindle_side_filter:
        main_kwargs["spindle_side_filter"] = main_spindle_side_filter
    if sub_spindle_side_filter:
        sub_kwargs["spindle_side_filter"] = sub_spindle_side_filter

    dialog.main_jaw_selector = jaw_selector_panel_cls(main_title, **main_kwargs)
    dialog.sub_jaw_selector = jaw_selector_panel_cls(sub_title, **sub_kwargs)
    dialog.main_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    dialog.sub_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    dialog._jaw_selectors["main"] = dialog.main_jaw_selector
    dialog._jaw_selectors["sub"] = dialog.sub_jaw_selector
    dialog.sub_jaw_selector.setVisible("sub" in dialog._spindle_profiles)
    
    # Connect jaw drop signals to allow drag-and-drop from Tools library jaw cards
    dialog.main_jaw_selector.jawDropped.connect(
        lambda jaw: dialog._on_jaw_dropped_in_selector_panel(jaw, spindle_key="main")
    )
    dialog.sub_jaw_selector.jawDropped.connect(
        lambda jaw: dialog._on_jaw_dropped_in_selector_panel(jaw, spindle_key="sub")
    )
    
    dialog._apply_machine_profile_to_jaw_selectors()


def build_general_tab_ui(
    dialog: Any,
    *,
    create_titled_section_fn: Callable[[str], object],
) -> None:
    layout = QVBoxLayout(dialog.general_tab)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    dialog.work_id_input = QLineEdit()
    dialog.drawing_id_input = QLineEdit()
    dialog.description_input = QLineEdit()
    dialog.raw_part_od_input = QLineEdit()
    dialog.raw_part_id_input = QLineEdit()
    dialog.raw_part_length_input = QLineEdit()
    dialog.raw_part_side_input = QLineEdit()
    dialog.raw_part_square_length_input = QLineEdit()
    dialog.raw_part_custom_fields_input = QPlainTextEdit()
    dialog.raw_part_custom_fields_input.setPlaceholderText("name=value\ndiameter=25.4")
    dialog.raw_part_custom_fields_input.setFixedHeight(90)
    dialog.raw_part_kind_combo = QComboBox()
    dialog.raw_part_kind_combo.addItem(dialog._t("work_editor.raw_part.kind.bar", "Bar"), "bar")
    dialog.raw_part_kind_combo.addItem(dialog._t("work_editor.raw_part.kind.square", "Square"), "square")
    dialog.raw_part_kind_combo.addItem(dialog._t("work_editor.raw_part.kind.custom", "Custom"), "custom")

    drawing_row = QWidget()
    drawing_layout = QHBoxLayout(drawing_row)
    drawing_layout.setContentsMargins(0, 0, 0, 0)
    dialog.drawing_path_input = QLineEdit()
    browse_btn = QPushButton(dialog._t("work_editor.action.browse", "Browse"))
    browse_btn.clicked.connect(dialog._browse_drawing)
    drawing_layout.addWidget(dialog.drawing_path_input, 1)
    drawing_layout.addWidget(browse_btn)

    general_group = create_titled_section_fn(dialog._t("work_editor.general.section.general", "General"))
    general_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    general_form = QFormLayout(general_group)
    general_form.setSpacing(8)
    general_form.addRow(dialog._t("setup_page.field.work_id", "Work ID"), dialog.work_id_input)
    general_form.addRow(dialog._t("setup_page.field.drawing_id", "Drawing ID"), dialog.drawing_id_input)
    general_form.addRow(dialog._t("setup_page.field.description", "Description"), dialog.description_input)
    dialog._drawing_row = drawing_row
    dialog._drawing_row_label = dialog._t("work_editor.field.drawing_path", "Drawing path")
    if dialog._drawings_enabled:
        general_form.addRow(dialog._drawing_row_label, drawing_row)

    raw_part_group = create_titled_section_fn(dialog._t("work_editor.general.section.raw_part", "Raw Part"))
    raw_part_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    raw_form = QFormLayout(raw_part_group)
    raw_form.setSpacing(8)
    raw_form.addRow(
        dialog._t("work_editor.general.raw_kind", "Kind"),
        dialog.raw_part_kind_combo,
    )

    dialog._raw_part_mode_stack = QStackedWidget()

    bar_page = QWidget()
    bar_form = QFormLayout(bar_page)
    bar_form.setContentsMargins(0, 0, 0, 0)
    bar_form.setSpacing(8)
    bar_form.addRow(
        dialog._t("work_editor.general.raw_outer_diameter", "Outer diameter"),
        dialog.raw_part_od_input,
    )
    bar_form.addRow(
        dialog._t("work_editor.general.raw_inner_diameter", "Inner diameter"),
        dialog.raw_part_id_input,
    )
    bar_form.addRow(
        dialog._t("work_editor.general.raw_length", "Length"),
        dialog.raw_part_length_input,
    )
    dialog._raw_part_mode_stack.addWidget(bar_page)

    square_page = QWidget()
    square_form = QFormLayout(square_page)
    square_form.setContentsMargins(0, 0, 0, 0)
    square_form.setSpacing(8)
    square_form.addRow(
        dialog._t("work_editor.general.raw_side", "Side"),
        dialog.raw_part_side_input,
    )
    square_form.addRow(
        dialog._t("work_editor.general.raw_length", "Length"),
        dialog.raw_part_square_length_input,
    )
    dialog._raw_part_mode_stack.addWidget(square_page)

    custom_page = QWidget()
    custom_form = QFormLayout(custom_page)
    custom_form.setContentsMargins(0, 0, 0, 0)
    custom_form.setSpacing(8)
    custom_form.addRow(
        dialog._t("work_editor.general.raw_custom_fields", "Custom fields"),
        dialog.raw_part_custom_fields_input,
    )
    dialog._raw_part_mode_stack.addWidget(custom_page)

    raw_form.addRow(dialog._raw_part_mode_stack)

    def _on_raw_kind_changed(index: int) -> None:
        dialog._raw_part_mode_stack.setCurrentIndex(max(0, index))

    dialog.raw_part_kind_combo.currentIndexChanged.connect(_on_raw_kind_changed)
    _on_raw_kind_changed(dialog.raw_part_kind_combo.currentIndex())

    layout.addWidget(general_group)
    layout.addWidget(raw_part_group)

    layout.addStretch(1)


def build_spindles_tab_ui(
    dialog: Any,
    *,
    jaw_selector_panel_cls: type,
) -> None:
    layout = QVBoxLayout(dialog.spindles_tab)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    selector_row = QHBoxLayout()
    selector_row.setContentsMargins(0, 0, 0, 0)
    selector_row.setSpacing(8)
    dialog.open_jaw_selector_btn = QPushButton(
        dialog._t("work_editor.selector.jaws_button", "Select Jaws")
    )
    dialog.open_jaw_selector_btn.setProperty("panelActionButton", True)
    dialog.open_jaw_selector_btn.clicked.connect(dialog._open_jaw_selector)
    selector_row.addWidget(dialog.open_jaw_selector_btn, 0)
    selector_row.addStretch(1)
    layout.addLayout(selector_row)

    # Resolve jaw selector titles and filters from the machine profile so
    # single-spindle (OP terminology) and custom profiles get correct labels.
    _main_sp = dialog.machine_profile.spindle("main")
    _sub_sp = dialog.machine_profile.spindle("sub")

    _main_jaw_title = dialog._t(
        _main_sp.jaw_title_key if _main_sp else "work_editor.spindles.sp1_jaw",
        _main_sp.jaw_title_default if _main_sp else "Pääkara",
    )
    _sub_jaw_title = dialog._t(
        _sub_sp.jaw_title_key if _sub_sp else "work_editor.spindles.sp2_jaw",
        _sub_sp.jaw_title_default if _sub_sp else "Vastakara",
    )
    _main_filter_ph = (
        (_main_sp.jaw_filter_placeholder_key if _main_sp else "work_editor.jaw.filter_sp1_placeholder"),
        (_main_sp.jaw_filter_placeholder_default if _main_sp else "Suodata Pääkara-leukoja..."),
    )
    _sub_filter_ph = (
        (_sub_sp.jaw_filter_placeholder_key if _sub_sp else "work_editor.jaw.filter_sp2_placeholder"),
        (_sub_sp.jaw_filter_placeholder_default if _sub_sp else "Suodata Vastakara-leukoja..."),
    )
    _main_side_filter = _main_sp.jaw_filter if _main_sp else "Main spindle"
    _sub_side_filter = _sub_sp.jaw_filter if _sub_sp else "Sub spindle"

    _setup_jaw_selectors(
        dialog,
        jaw_selector_panel_cls=jaw_selector_panel_cls,
        main_title=_main_jaw_title,
        sub_title=_sub_jaw_title,
        main_filter_placeholder=_main_filter_ph,
        sub_filter_placeholder=_sub_filter_ph,
        main_spindle_side_filter=_main_side_filter,
        sub_spindle_side_filter=_sub_side_filter,
    )

    host = ResponsiveColumnsHost(switch_width=860, separator_property="jawColumnSeparator")
    host.add_widget(dialog.main_jaw_selector, 1)
    if "sub" in dialog._spindle_profiles:
        host.add_widget(dialog.sub_jaw_selector, 1)
    layout.addWidget(host, 1)


def build_zeros_tab_ui(
    dialog: Any,
    *,
    jaw_selector_panel_cls: type,
    create_titled_section_fn: Callable[[str], object],
) -> None:
    if is_machining_center(dialog.machine_profile):
        build_machining_center_zeros_tab_ui(
            dialog,
            create_titled_section_fn=create_titled_section_fn,
            work_coordinates=dialog.WORK_COORDINATES if hasattr(dialog, 'WORK_COORDINATES') else ('G54', 'G55', 'G56', 'G57', 'G58', 'G59'),
        )
        return

    dialog.zeros_tab.setProperty("zeroPointsSurface", True)
    layout = QVBoxLayout(dialog.zeros_tab)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    content = QWidget()
    content.setProperty("zeroPointsSurface", True)
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(12)
    scroll.setWidget(content)
    layout.addWidget(scroll, 1)

    programs_group = create_titled_section_fn(dialog._t("work_editor.zeros.nc_programs", "NC Programs"))
    programs_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    programs_form = QFormLayout(programs_group)
    programs_form.setSpacing(8)
    dialog.main_program_input = QLineEdit()
    programs_form.addRow(dialog._t("setup_page.field.main_program", "Main program"), dialog.main_program_input)
    for head in dialog.machine_profile.heads:
        sub_program_input = QLineEdit()
        dialog._sub_program_inputs[head.key] = sub_program_input
        setattr(dialog, f"{head.key.lower()}_sub_program_input", sub_program_input)
        programs_form.addRow(
            dialog._t(
                f"setup_page.field.sub_programs_{head.key.lower()}",
                f"Sub program {head.label_default}",
            ),
            sub_program_input,
        )
    content_layout.addWidget(programs_group)

    # Keep these on the historical main/sub attributes so payload adapters and
    # selector merge logic remain schema-compatible with existing saved works.
    # Resolve titles from profile so single-spindle (OP) profiles get correct labels.
    _zp_main_sp = dialog.machine_profile.spindle("main")
    _zp_sub_sp = dialog.machine_profile.spindle("sub")
    _zp_main_title = dialog._t(
        _zp_main_sp.jaw_title_key if _zp_main_sp else "work_editor.jaw.main_spindle_jaws",
        _zp_main_sp.jaw_title_default if _zp_main_sp else "Pääkaran leuat",
    )
    if dialog.machine_profile.spindle_count == 1:
        # Single-spindle machine: use OP20 terminology for the optional sub jaw panel.
        _zp_sub_title = dialog._t("work_editor.spindles.op20_jaws", "OP20 Jaws")
    else:
        _zp_sub_title = dialog._t(
            _zp_sub_sp.jaw_title_key if _zp_sub_sp else "work_editor.jaw.sub_spindle_jaws",
            _zp_sub_sp.jaw_title_default if _zp_sub_sp else "Vastakaran leuat",
        )
    _setup_jaw_selectors(
        dialog,
        jaw_selector_panel_cls=jaw_selector_panel_cls,
        main_title=_zp_main_title,
        sub_title=_zp_sub_title,
        main_spindle_side_filter=(_zp_main_sp.jaw_filter if _zp_main_sp else "Main spindle"),
        sub_spindle_side_filter=(_zp_sub_sp.jaw_filter if _zp_sub_sp else "Sub spindle"),
    )

    controls_row = QHBoxLayout()
    controls_row.setContentsMargins(2, 0, 2, 0)
    controls_row.setSpacing(10)
    dialog.open_jaw_selector_btn = QPushButton(
        dialog._t("work_editor.selector.jaws_button", "Select Jaws")
    )
    dialog.open_jaw_selector_btn.setProperty("panelActionButton", True)
    dialog.open_jaw_selector_btn.setMinimumWidth(176)
    dialog.open_jaw_selector_btn.setMaximumWidth(220)
    dialog.open_jaw_selector_btn.setFixedHeight(32)
    dialog.open_jaw_selector_btn.clicked.connect(dialog._open_jaw_selector)
    controls_row.addWidget(dialog.open_jaw_selector_btn, 0)

    if dialog.machine_profile.spindle_count == 1:
        dialog.op20_jaws_checkbox = QCheckBox(
            dialog._t("work_editor.zeros.include_op20", "Include OP20")
        )
        apply_shared_checkbox_style(dialog.op20_jaws_checkbox, indicator_size=16)
        dialog.op20_jaws_checkbox.setChecked(getattr(dialog, '_op20_jaws_enabled', False))

        def _apply_op20_jaws(checked: bool, _d=dialog):
            _d._op20_jaws_enabled = checked
            if hasattr(_d, '_op20_zero_group_widget'):
                _d._op20_zero_group_widget.setVisible(checked)
            _sub_sel = _d._jaw_selectors.get("sub")
            if _sub_sel is not None:
                _sub_sel.setVisible(checked)

        dialog.op20_jaws_checkbox.toggled.connect(_apply_op20_jaws)
        controls_row.addWidget(dialog.op20_jaws_checkbox, 0, Qt.AlignVCenter)

    dialog.zero_show_xy_checkbox = QCheckBox(
        dialog._t("work_editor.zeros.show_xy", "Show X/Y columns")
    )
    apply_shared_checkbox_style(dialog.zero_show_xy_checkbox, indicator_size=16)
    dialog.zero_show_xy_checkbox.setChecked(dialog.machine_profile.default_zero_xy_visible)
    dialog.zero_show_xy_checkbox.toggled.connect(dialog._set_zero_xy_visibility)
    dialog.zero_show_xy_checkbox.setVisible(dialog.machine_profile.supports_zero_xy_toggle)
    controls_row.addWidget(dialog.zero_show_xy_checkbox, 0, Qt.AlignVCenter)
    controls_row.addStretch(1)
    content_layout.addLayout(controls_row)

    dialog.zero_points_host = ResponsiveColumnsHost(switch_width=1320)
    for spindle_key in dialog._spindle_profiles.keys():
        # Use the profile label directly — no hardcoded English fallback so that
        # single-spindle profiles render "OP10" and dual-spindle profiles render
        # their own translated labels (e.g. "Main spindle" / "Sub spindle").
        title = dialog._spindle_label(spindle_key)
        dialog.zero_points_host.add_widget(
            dialog._build_spindle_zero_group(title, spindle_key),
            1,
        )
    if dialog.machine_profile.spindle_count == 1:
        # Build OP20 zero-point group using the "sub" storage key but keep it
        # hidden until the user enables OP20 via the checkbox.
        _op20_zero_title = dialog._t("work_editor.zeros.op20_group", "OP20")
        _op20_zero_grp = dialog._build_spindle_zero_group(_op20_zero_title, "sub")
        _op20_zero_grp.setVisible(getattr(dialog, '_op20_jaws_enabled', False))
        dialog._op20_zero_group_widget = _op20_zero_grp
        dialog.zero_points_host.add_widget(_op20_zero_grp, 1)
    content_layout.addWidget(dialog.zero_points_host)

    jaw_row_host = QWidget()
    jaw_row = QHBoxLayout(jaw_row_host)
    jaw_row.setContentsMargins(0, 0, 0, 0)
    jaw_row.setSpacing(12)
    dialog.main_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    jaw_row.addWidget(dialog.main_jaw_selector, 1)
    if "sub" in dialog._spindle_profiles:
        dialog.sub_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        jaw_row.addWidget(dialog.sub_jaw_selector, 1)
    elif dialog.machine_profile.spindle_count == 1:
        # Single-spindle: add OP20 jaw selector to the row but start it hidden.
        dialog.sub_jaw_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        dialog.sub_jaw_selector.setVisible(getattr(dialog, '_op20_jaws_enabled', False))
        jaw_row.addWidget(dialog.sub_jaw_selector, 1)
    else:
        jaw_row.addStretch(1)
    content_layout.addWidget(jaw_row_host, 0)

    dialog._set_zero_xy_visibility(dialog.zero_show_xy_checkbox.isChecked())

    if dialog.machine_profile.supports_sub_pickup:
        sub_group = create_titled_section_fn(dialog._t("setup_page.field.sp2", "SP2"))
        sub_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sub_form = QFormLayout(sub_group)
        sub_form.setSpacing(8)
        dialog.sub_pickup_z_input = QLineEdit()
        sub_form.addRow(dialog._t("setup_page.field.sub_pickup_z", "Pickup Z"), dialog.sub_pickup_z_input)
        content_layout.addWidget(sub_group)
    content_layout.addStretch(1)


def build_notes_tab_ui(
    dialog: Any,
    *,
    create_titled_section_fn: Callable[[str], object],
) -> None:
    layout = QVBoxLayout(dialog.notes_tab)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(8)
    dialog.notes_input = QTextEdit()
    dialog.robot_info_input = QTextEdit()
    dialog.notes_input.setMinimumHeight(150)
    dialog.robot_info_input.setMaximumHeight(96)

    notes_group = create_titled_section_fn(dialog._t("setup_page.field.notes", "Notes"))
    notes_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    notes_group_layout = QVBoxLayout(notes_group)
    notes_group_layout.setContentsMargins(10, 8, 10, 10)
    notes_group_layout.addWidget(dialog.notes_input, 1)
    layout.addWidget(notes_group, 1)

    robot_group = create_titled_section_fn(dialog._t("setup_page.field.robot_info", "Robot info"))
    robot_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    robot_group_layout = QVBoxLayout(robot_group)
    robot_group_layout.setContentsMargins(10, 8, 10, 10)
    robot_group_layout.addWidget(dialog.robot_info_input, 0)
    layout.addWidget(robot_group, 0)


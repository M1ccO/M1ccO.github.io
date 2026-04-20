from __future__ import annotations

from machine_profiles import KNOWN_HEAD_KEYS, KNOWN_SPINDLE_KEYS, MachineProfile, is_machining_center
from .machining_center import collect_machining_center_payload, load_machining_center_payload


def _tool_assignment_widgets_for_head(dialog, head_key: str):
    columns = getattr(dialog, "_tool_column_lists", {}).get(head_key, {})
    if isinstance(columns, dict) and columns:
        seen: set[int] = set()
        widgets = []
        for ordered_list in columns.values():
            if ordered_list is None:
                continue
            widget_id = id(ordered_list)
            if widget_id in seen:
                continue
            seen.add(widget_id)
            widgets.append(ordered_list)
        if widgets:
            return widgets

    ordered_list = getattr(dialog, "_ordered_tool_lists", {}).get(head_key)
    return [ordered_list] if ordered_list is not None else []


def _collect_head_tool_assignments(dialog, head_key: str) -> list[dict]:
    """Collect one merged assignment list for a head across all visible widgets.

    Main/sub columns usually share one backing assignment map, but this helper
    tolerates split widget state and always returns both spindle buckets.
    """
    widgets = [w for w in _tool_assignment_widgets_for_head(dialog, head_key) if w is not None]
    if not widgets:
        return []

    merged_by_spindle: dict[str, list[dict]] = {"main": [], "sub": []}

    for spindle in ("main", "sub"):
        spindle_values: list[dict] = []
        for widget in widgets:
            try:
                candidate_items = (getattr(widget, "_assignments_by_spindle", {}) or {}).get(spindle, [])
            except Exception:
                candidate_items = []
            clean_items = [dict(item) for item in candidate_items if isinstance(item, dict)]
            if clean_items:
                spindle_values = clean_items
                break

        if not spindle_values:
            for widget in widgets:
                getter = getattr(widget, "get_tool_assignments", None)
                if not callable(getter):
                    continue
                try:
                    candidate = [
                        dict(item)
                        for item in (getter() or [])
                        if isinstance(item, dict) and str(item.get("spindle") or "main").strip().lower() == spindle
                    ]
                except Exception:
                    candidate = []
                if candidate:
                    spindle_values = candidate
                    break

        merged_by_spindle[spindle] = spindle_values

    return [*merged_by_spindle["main"], *merged_by_spindle["sub"]]


class WorkEditorPayloadAdapter:
    """Bridge the profile-driven dialog UI to the legacy work payload shape.

    The database schema still stores NTX-era field names like ``head1_main_z``.
    This adapter keeps that contract stable while letting the UI decide which
    stations, spindles, and axes are actually visible for the active machine.
    """

    def __init__(self, profile: MachineProfile):
        self.profile = profile

    @staticmethod
    def _head_prefix(head_key: str) -> str:
        return str(head_key or "").strip().lower()

    def coord_field(self, head_key: str, spindle_key: str) -> str:
        return f"{self._head_prefix(head_key)}_{str(spindle_key).strip().lower()}_coord"

    def axis_field(self, head_key: str, spindle_key: str, axis: str) -> str:
        return f"{self._head_prefix(head_key)}_{str(spindle_key).strip().lower()}_{str(axis).strip().lower()}"

    def tool_assignment_field(self, head_key: str) -> str:
        return f"{self._head_prefix(head_key)}_tool_assignments"

    def tool_ids_field(self, head_key: str) -> str:
        return f"{self._head_prefix(head_key)}_tool_ids"

    def sub_program_field(self, head_key: str) -> str:
        return f"{self._head_prefix(head_key)}_sub_program"

    def legacy_zero_field(self, head_key: str) -> str:
        return f"{self._head_prefix(head_key)}_zero"

    @staticmethod
    def jaw_field(spindle_key: str) -> str:
        return f"{str(spindle_key).strip().lower()}_jaw_id"

    @staticmethod
    def stop_screws_field(spindle_key: str) -> str:
        return f"{str(spindle_key).strip().lower()}_stop_screws"

    def populate_dialog(self, dialog, work: dict):
        payload = dict(work or {})
        is_mc = is_machining_center(self.profile)
        dialog.work_id_input.setText(payload.get("work_id", ""))
        dialog.work_id_input.setEnabled(not bool(payload.get("work_id")))
        dialog.drawing_id_input.setText(payload.get("drawing_id", ""))
        dialog.description_input.setText(payload.get("description", ""))
        dialog.drawing_path_input.setText(payload.get("drawing_path", ""))
        dialog.raw_part_od_input.setText(payload.get("raw_part_od", ""))
        dialog.raw_part_id_input.setText(payload.get("raw_part_id", ""))
        dialog.raw_part_length_input.setText(payload.get("raw_part_length", ""))
        dialog.raw_part_side_input.setText(payload.get("raw_part_side", ""))
        dialog.raw_part_square_length_input.setText(payload.get("raw_part_square_length", ""))
        dialog.raw_part_custom_fields_input.setPlainText(payload.get("raw_part_custom_fields", ""))
        _kind = str(payload.get("raw_part_kind", "bar") or "bar").strip().lower()
        if _kind not in {"bar", "square", "custom"}:
            _kind = "bar"
        if not is_mc:
            _kind = "bar"
        _kind_idx = {"bar": 0, "square": 1, "custom": 2}[_kind]
        dialog.raw_part_kind_combo.setCurrentIndex(_kind_idx)

        for spindle in self.profile.spindles:
            selector = dialog._jaw_selectors.get(spindle.key)
            if selector is None:
                continue
            selector.set_value(payload.get(self.jaw_field(spindle.key), ""))
            selector.set_stop_screws(payload.get(self.stop_screws_field(spindle.key), ""))

        # For single-spindle profiles the "sub" (OP20) jaw selector is not part of
        # profile.spindles, but it still needs to be pre-populated so that opening
        # an existing work with OP20 data shows the correct jaw.
        if self.profile.spindle_count == 1:
            _sub_sel = dialog._jaw_selectors.get("sub")
            if _sub_sel is not None:
                _sub_sel.set_value(payload.get(self.jaw_field("sub"), ""))
                _sub_sel.set_stop_screws(payload.get(self.stop_screws_field("sub"), ""))

        if hasattr(dialog, "main_program_input"):
            dialog.main_program_input.setText(payload.get("main_program", ""))

        if is_mc:
            load_machining_center_payload(dialog, payload)

        for head in self.profile.heads:
            program_input = dialog._sub_program_inputs.get(head.key)
            if program_input is not None:
                program_input.setText(payload.get(self.sub_program_field(head.key), ""))

            for spindle in self.profile.spindles:
                combo = dialog._zero_coord_inputs.get((head.key, spindle.key))
                if combo is None:
                    continue
                dialog._set_coord_combo(
                    combo,
                    payload.get(
                        self.coord_field(head.key, spindle.key),
                        payload.get(self.legacy_zero_field(head.key), ""),
                    ),
                    head.default_coord,
                )
                for axis in self.profile.zero_axes:
                    widget = dialog._zero_axis_input_map.get((head.key, spindle.key, axis))
                    if widget is not None:
                        widget.setText(payload.get(self.axis_field(head.key, spindle.key, axis), ""))

            if not is_mc:
                assignments = payload.get(self.tool_assignment_field(head.key), [])
                for ordered_list in _tool_assignment_widgets_for_head(dialog, head.key):
                    ordered_list.set_tool_assignments(assignments)

        if hasattr(dialog, "sub_pickup_z_input"):
            dialog.sub_pickup_z_input.setText(payload.get("sub_pickup_z", ""))

        if hasattr(dialog, "print_pots_checkbox"):
            dialog.print_pots_checkbox.setChecked(bool(payload.get("print_pots", False)))

        dialog.robot_info_input.setPlainText(payload.get("robot_info", ""))
        dialog.notes_input.setPlainText(payload.get("notes", ""))

    def collect_payload(self, dialog, *, persisted_work: dict | None = None, drawings_enabled: bool = True) -> dict:
        is_mc = is_machining_center(self.profile)
        # Start from the persisted row so fields hidden by the active machine
        # profile keep their previous values instead of being erased on save.
        payload = dict(persisted_work or {})
        payload.update(
            {
                "work_id": dialog.work_id_input.text().strip(),
                "drawing_id": dialog.drawing_id_input.text().strip(),
                "description": dialog.description_input.text().strip(),
                "drawing_path": (
                    dialog.drawing_path_input.text().strip()
                    if drawings_enabled
                    else (persisted_work or {}).get("drawing_path", "")
                ),
                "raw_part_kind": (dialog.raw_part_kind_combo.currentData() or "bar"),
                "raw_part_od": dialog.raw_part_od_input.text().strip(),
                "raw_part_id": dialog.raw_part_id_input.text().strip(),
                "raw_part_length": dialog.raw_part_length_input.text().strip(),
                "raw_part_side": dialog.raw_part_side_input.text().strip(),
                "raw_part_square_length": dialog.raw_part_square_length_input.text().strip(),
                "raw_part_custom_fields": dialog.raw_part_custom_fields_input.toPlainText().strip(),
                "main_program": (
                    dialog.main_program_input.text().strip()
                    if hasattr(dialog, "main_program_input")
                    else (persisted_work or {}).get("main_program", "")
                ),
                "robot_info": dialog.robot_info_input.toPlainText().strip(),
                "notes": dialog.notes_input.toPlainText().strip(),
                "print_pots": bool(getattr(dialog, "print_pots_checkbox", None) and dialog.print_pots_checkbox.isChecked()),
            }
        )

        if not is_mc:
            payload["raw_part_kind"] = "bar"
            payload["raw_part_side"] = ""
            payload["raw_part_square_length"] = ""
            payload["raw_part_custom_fields"] = ""

        if is_mc:
            mc_operation_count, mc_operations = collect_machining_center_payload(dialog)
            payload["mc_operation_count"] = mc_operation_count
            payload["mc_operations"] = mc_operations

        if hasattr(dialog, "sub_pickup_z_input"):
            payload["sub_pickup_z"] = dialog.sub_pickup_z_input.text().strip()

        for spindle_key in KNOWN_SPINDLE_KEYS:
            selector = dialog._jaw_selectors.get(spindle_key)
            if selector is None:
                continue
            payload[self.jaw_field(spindle_key)] = selector.get_value()
            payload[self.stop_screws_field(spindle_key)] = selector.get_stop_screws()

        for head_key in KNOWN_HEAD_KEYS:
            ordered_widgets = _tool_assignment_widgets_for_head(dialog, head_key)
            if ordered_widgets and not is_mc:
                assignments = _collect_head_tool_assignments(dialog, head_key)
                payload[self.tool_assignment_field(head_key)] = assignments
                payload[self.tool_ids_field(head_key)] = [
                    str(item.get("tool_id") or "").strip()
                    for item in assignments
                    if isinstance(item, dict) and str(item.get("tool_id") or "").strip()
                ]

            program_input = dialog._sub_program_inputs.get(head_key)
            if program_input is not None:
                payload[self.sub_program_field(head_key)] = program_input.text().strip()

            head_profile = self.profile.head(head_key)
            main_combo = dialog._zero_coord_inputs.get((head_key, "main"))
            if main_combo is not None:
                payload[self.legacy_zero_field(head_key)] = main_combo.currentText().strip()
            elif head_profile is not None:
                payload.setdefault(self.legacy_zero_field(head_key), head_profile.default_coord)

            for spindle_key in KNOWN_SPINDLE_KEYS:
                combo = dialog._zero_coord_inputs.get((head_key, spindle_key))
                if combo is not None:
                    payload[self.coord_field(head_key, spindle_key)] = combo.currentText().strip()
                for axis in self.profile.zero_axes:
                    widget = dialog._zero_axis_input_map.get((head_key, spindle_key, axis))
                    if widget is not None:
                        payload[self.axis_field(head_key, spindle_key, axis)] = widget.text().strip()

        return payload

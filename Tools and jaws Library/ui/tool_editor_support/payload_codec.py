from __future__ import annotations

import json
from typing import Callable

from .components import component_items_from_rows, normalized_component_items, normalized_support_parts, spare_parts_from_rows
from .tool_type_rules import build_tool_type_field_state


class ToolEditorPayloadCodec:
    """Encode/decode bridge between dialog widgets and persisted tool payload shape."""

    def __init__(
        self,
        *,
        translate: Callable[[str, str | None], str],
        localized_cutting_type: Callable[[str], str],
        tool_id_editor_value: Callable[[str], str],
        tool_id_storage_value: Callable[[str], str],
        turning_tool_types: tuple[str, ...] | list[str],
        milling_tool_types: tuple[str, ...] | list[str],
    ):
        self._translate = translate
        self._localized_cutting_type = localized_cutting_type
        self._tool_id_editor_value = tool_id_editor_value
        self._tool_id_storage_value = tool_id_storage_value
        self._turning_tool_types = tuple(turning_tool_types)
        self._milling_tool_types = tuple(milling_tool_types)

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _parse_float(value, field_name: str, translate: Callable[[str, str | None], str]) -> float:
        text = value.text().strip()
        if not text:
            return 0.0
        try:
            return float(text.replace(",", "."))
        except ValueError as exc:
            raise ValueError(
                translate("tool_editor.error.must_be_number", "{field_name} must be a number.", field_name=field_name)
            ) from exc

    @staticmethod
    def _parse_int(value, field_name: str, translate: Callable[[str, str | None], str]) -> int:
        text = value.text().strip().replace(",", ".")
        if not text:
            return 0
        try:
            return int(text)
        except ValueError:
            try:
                numeric_value = float(text)
                if numeric_value.is_integer():
                    return int(numeric_value)
            except ValueError:
                pass
            raise ValueError(
                translate("tool_editor.error.must_be_integer", "{field_name} must be an integer.", field_name=field_name)
            )

    def load_into_dialog(self, dialog, tool: dict) -> None:
        if not tool:
            return

        dialog.tool_id.setText(self._tool_id_editor_value(tool.get("id", "")))
        dialog._set_tool_head_value(tool.get("tool_head", "HEAD1"))
        dialog._set_spindle_orientation_value(tool.get("spindle_orientation", "main"))
        dialog._set_combo_by_data(dialog.tool_type, tool.get("tool_type", "O.D Turning"))
        dialog.description.setText(tool.get("description", ""))
        dialog.geom_x.setText(str(tool.get("geom_x", "")))
        dialog.geom_z.setText(str(tool.get("geom_z", "")))
        dialog.b_axis_angle.setText(str(tool.get("b_axis_angle", "0")))
        dialog.radius.setText(str(tool.get("radius", "")))
        dialog.nose_corner_radius.setText(str(tool.get("nose_corner_radius", "")))
        dialog.holder_code.setText(tool.get("holder_code", ""))
        dialog.holder_link.setText(tool.get("holder_link", ""))
        dialog.holder_add_element.setText(tool.get("holder_add_element", ""))
        dialog.holder_add_element_link.setText(tool.get("holder_add_element_link", ""))
        dialog._set_combo_by_data(dialog.cutting_type, tool.get("cutting_type", "Insert"))
        dialog.cutting_code.setText(tool.get("cutting_code", ""))
        dialog.cutting_link.setText(tool.get("cutting_link", ""))
        dialog.cutting_add_element.setText(tool.get("cutting_add_element", ""))
        dialog.cutting_add_element_link.setText(tool.get("cutting_add_element_link", ""))
        dialog.notes.setPlainText(str(tool.get("notes", tool.get("spare_parts", "")) or ""))
        dialog.default_pot.setText(tool.get("default_pot", ""))
        dialog.drill_nose_angle.setText(str(tool.get("drill_nose_angle", "")))
        dialog.mill_cutting_edges.setText(str(tool.get("mill_cutting_edges", "")))

        for item in normalized_component_items(
            tool,
            translate=self._translate,
            localized_cutting_type=self._localized_cutting_type,
        ):
            if not isinstance(item, dict):
                continue
            role = (item.get("role") or "").strip().lower()
            code = (item.get("code") or "").strip()
            if role not in {"holder", "cutting", "support"} or not code:
                continue
            dialog.parts_table.add_empty_row(
                [
                    role,
                    (item.get("label") or "").strip() or self._t("tool_library.field.part", "Part"),
                    code,
                    (item.get("link") or "").strip(),
                    (item.get("group") or "").strip(),
                ]
            )

        for part in normalized_support_parts(tool):
            dialog._add_spare_part_row(part)
        dialog._refresh_spare_component_dropdowns()

        stl_data = tool.get("stl_path", "")
        model_parts = []
        if isinstance(stl_data, str) and stl_data.strip():
            try:
                parsed = json.loads(stl_data)
                if isinstance(parsed, list):
                    model_parts = parsed
                elif isinstance(parsed, str):
                    model_parts = [{"name": self._t("tool_editor.model.default_name", "Model"), "file": parsed, "color": "#9ea7b3"}]
            except Exception:
                model_parts = [{"name": self._t("tool_editor.model.default_name", "Model"), "file": stl_data, "color": "#9ea7b3"}]

        dialog._suspend_preview_refresh = True
        try:
            for part in model_parts:
                dialog._add_model_row(
                    {
                        "name": part.get("name", ""),
                        "file": part.get("file", ""),
                        "color": part.get("color", dialog._default_color_for_part_name(part.get("name", ""))),
                    }
                )
        finally:
            dialog._suspend_preview_refresh = False

        dialog._part_transforms = {}
        dialog._saved_part_transforms = {}
        for index, part in enumerate(model_parts):
            transform = {}
            for src, dst in [("offset_x", "x"), ("offset_y", "y"), ("offset_z", "z"), ("rot_x", "rx"), ("rot_y", "ry"), ("rot_z", "rz")]:
                value = part.get(src, 0)
                if value:
                    transform[dst] = value
            normalized = dialog._normalized_transform_dict(transform)
            compact = dialog._compact_transform_dict(normalized)
            if compact:
                dialog._part_transforms[index] = dict(compact)
                dialog._saved_part_transforms[index] = dict(compact)

        dialog._load_measurement_overlays(tool.get("measurement_overlays", []))

        # Reset so the field-state refresh below can swap geometry meaning cleanly
        # even when combo population order differs between old and new payloads.
        dialog._turning_drill_geometry_mode = False
        tool_type = (tool.get("tool_type", "") or "").strip()
        if build_tool_type_field_state(
            selected_type=tool_type,
            cutting_type=(tool.get("cutting_type", "Insert") or "Insert").strip() or "Insert",
            selected_head=(tool.get("tool_head", "HEAD1") or "HEAD1").strip() or "HEAD1",
            turning_tool_types=self._turning_tool_types,
            milling_tool_types=self._milling_tool_types,
        ).turning_drill_type:
            dialog.nose_corner_radius.setText(str(tool.get("drill_nose_angle", "")))
        elif tool_type in {"Chamfer", "Spot Drill"}:
            angle_text = str(tool.get("drill_nose_angle", "")).strip()
            if angle_text:
                dialog.nose_corner_radius.setText(angle_text)

        dialog._update_tool_type_fields()
        dialog._refresh_models_preview()
        if dialog._assembly_transform_enabled:
            selection_model = dialog.model_table.selectionModel()
            if selection_model is not None:
                rows = sorted(index.row() for index in selection_model.selectedRows())
                if not rows:
                    current_row = dialog.model_table.currentRow()
                    if current_row >= 0:
                        rows = [current_row]
                dialog._selected_part_indices = rows
                dialog._selected_part_index = rows[-1] if rows else -1
            dialog._refresh_transform_selection_state()
            dialog.models_preview.select_parts(dialog._selected_part_indices)

    def collect_from_dialog(self, dialog) -> dict:
        dialog._commit_active_edits()
        dialog._sync_preview_transform_snapshot_for_save()

        tool_id = self._tool_id_storage_value(dialog.tool_id.text())
        if not tool_id and not dialog._group_edit_mode:
            raise ValueError(self._t("tool_editor.error.tool_id_required", "Tool ID is required."))

        cutting_type = (dialog.cutting_type.currentData() or dialog.cutting_type.currentText() or "Insert").strip() or "Insert"
        selected_type = (dialog.tool_type.currentData() or dialog.tool_type.currentText() or "O.D Turning").strip() or "O.D Turning"
        selected_head = dialog._get_tool_head_value()
        field_state = build_tool_type_field_state(
            selected_type=selected_type,
            cutting_type=cutting_type,
            selected_head=selected_head,
            turning_tool_types=self._turning_tool_types,
            milling_tool_types=self._milling_tool_types,
        )

        model_parts = dialog._model_table_to_parts()
        component_items = component_items_from_rows(
            dialog.parts_table.row_dicts(),
            translate=self._translate,
            localized_cutting_type=self._localized_cutting_type,
        )
        spare_rows: list[dict] = []
        for row in range(dialog.spare_parts_table.rowCount()):
            entry = dialog.spare_parts_table.row_dict(row)
            entry["component_key"] = dialog._get_spare_component_key(row)
            spare_rows.append(entry)
        support_parts = spare_parts_from_rows(spare_rows)

        # Collectors intentionally write the normalized component/model payloads
        # even if the loaded row came from older legacy fields.
        return {
            "uid": dialog.original_uid,
            "id": tool_id,
            "tool_head": selected_head,
            "spindle_orientation": dialog._get_spindle_orientation_value() if selected_head == "HEAD2" else "main",
            "tool_type": selected_type,
            "description": dialog.description.text().strip(),
            "geom_x": self._parse_float(dialog.geom_x, self._t("tool_library.field.geom_x", "Geom X"), self._translate),
            "geom_z": self._parse_float(dialog.geom_z, self._t("tool_library.field.geom_z", "Geom Z"), self._translate),
            "b_axis_angle": self._parse_float(dialog.b_axis_angle, self._t("tool_library.field.b_axis_angle", "B-axis angle"), self._translate),
            "radius": self._parse_float(dialog.radius, self._t("tool_library.field.radius", "Radius"), self._translate) if field_state.show_radius else 0.0,
            "nose_corner_radius": self._parse_float(
                dialog.nose_corner_radius,
                self._t("tool_library.field.pitch", "Pitch") if field_state.uses_pitch_label else self._t("tool_library.field.nose_corner_radius", "Nose R / Corner R"),
                self._translate,
            ) if (not field_state.turning_drill_type and not field_state.geometry_uses_nose_angle) else 0.0,
            "holder_code": dialog.holder_code.text().strip(),
            "holder_link": dialog.holder_link.text().strip(),
            "holder_add_element": dialog.holder_add_element.text().strip(),
            "holder_add_element_link": dialog.holder_add_element_link.text().strip(),
            "cutting_type": cutting_type,
            "cutting_code": dialog.cutting_code.text().strip(),
            "cutting_link": dialog.cutting_link.text().strip(),
            "cutting_add_element": dialog.cutting_add_element.text().strip(),
            "cutting_add_element_link": dialog.cutting_add_element_link.text().strip(),
            "notes": dialog.notes.toPlainText().strip(),
            "drill_nose_angle": (
                self._parse_float(dialog.nose_corner_radius, self._t("tool_library.field.nose_angle", "Nose angle"), self._translate)
                if field_state.turning_drill_type or field_state.geometry_uses_nose_angle
                else (
                    self._parse_float(dialog.drill_nose_angle, self._t("tool_library.field.nose_angle", "Nose angle"), self._translate)
                    if cutting_type in {"Drill", "Center drill"} or selected_type == "Chamfer"
                    else 0.0
                )
            ),
            "mill_cutting_edges": self._parse_int(
                dialog.mill_cutting_edges,
                self._t("tool_library.field.number_of_flutes", "Number of flutes"),
                self._translate,
            ) if field_state.show_mill_field else 0,
            "support_parts": support_parts,
            "component_items": component_items,
            "measurement_overlays": dialog._measurement_overlays_from_tables(),
            "stl_path": json.dumps(model_parts) if model_parts else "",
            "default_pot": dialog.default_pot.text().strip(),
        }

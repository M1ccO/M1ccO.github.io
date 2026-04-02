from __future__ import annotations

import math
import re
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from config import (
    JAW_MODELS_ROOT_DEFAULT,
    SHARED_UI_PREFERENCES_PATH,
    TOOL_MODELS_ROOT_DEFAULT,
)
from shared.model_paths import read_model_roots, resolve_model_path

try:
    from OCC.Core.AIS import AIS_Shape, AIS_TextLabel  # type: ignore[import-not-found]
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Transform  # type: ignore[import-not-found]
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeSphere  # type: ignore[import-not-found]
    from OCC.Core.IFSelect import IFSelect_RetDone  # type: ignore[import-not-found]
    from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB  # type: ignore[import-not-found]
    from OCC.Core.STEPControl import STEPControl_Reader  # type: ignore[import-not-found]
    from OCC.Core.StlAPI import StlAPI_Reader  # type: ignore[import-not-found]
    from OCC.Core.TopoDS import TopoDS_Shape  # type: ignore[import-not-found]
    from OCC.Core.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec  # type: ignore[import-not-found]
    from OCC.Display.qtDisplay import qtViewer3d  # type: ignore[import-not-found]

    HAS_OCC = True
except Exception:
    HAS_OCC = False


class OcctPreviewWidget(QWidget):
    """Native OCCT preview widget with API compatibility for the current STL widget.

    This Phase 1 implementation focuses on model loading for STL and STEP while
    preserving the existing dialog integration points.

    TODO(3d-viewer-migration):
    - Make pythonocc-core installation path reproducible in this workspace.
    - Validate OCCT runtime behavior with real STEP/STL samples.
    - Verify PyInstaller packaging of OCC dynamic libraries end-to-end.
    """

    transform_changed = Signal(int, dict)
    part_selected = Signal(int)
    point_picked = Signal(dict)

    _ALLOWED_EXTENSIONS = {".stl", ".step", ".stp"}
    _MAX_FILE_BYTES = 200 * 1024 * 1024

    def __init__(self, stl_path: str | None = None, parent=None):
        super().__init__(parent)

        self._alignment_plane = "XZ"
        self._rotation_deg = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._transform_edit_enabled = False
        self._transform_mode = "translate"
        self._part_transforms_cache = []
        self._selected_part_index = -1
        self._measurement_overlays = []
        self._measurements_visible = False
        self._measurement_filter = None
        self._point_picking_enabled = False
        self._part_items = []
        self._loaded_parts = []
        self._pick_marker_ais = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.hide()

        self._viewer = None
        self._display = None
        self._ais_objects = []
        self._measurement_ais_objects = []

        if not HAS_OCC:
            self._show_error(
                "pythonocc-core is not installed.\n"
                "Install dependency to enable native STL/STEP preview."
            )
            self._layout.addWidget(self._error_label)
            return

        self._viewer = qtViewer3d(self)
        self._layout.addWidget(self._viewer)
        self._layout.addWidget(self._error_label)

        self._viewer.InitDriver()
        self._display = self._viewer._display
        self._viewer.installEventFilter(self)

        if stl_path:
            self.load_stl(stl_path)

    def _show_error(self, message: str):
        self._error_label.setText(message)
        self._error_label.show()
        if self._viewer is not None:
            self._viewer.hide()

    def _show_viewer(self):
        self._error_label.hide()
        if self._viewer is not None:
            self._viewer.show()

    def _safe_model_path(self, path_value: str | Path | None) -> Path | None:
        if not path_value:
            return None

        tools_root, jaws_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )

        model_path = resolve_model_path(str(path_value), tools_root, jaws_root)
        suffix = model_path.suffix.lower()

        if suffix not in self._ALLOWED_EXTENSIONS:
            self._show_error(f"Unsupported model format: {suffix or 'unknown'}")
            return None

        if not model_path.exists():
            self._show_error(f"Model file not found:\n{model_path}")
            return None

        try:
            file_size = model_path.stat().st_size
        except OSError:
            self._show_error(f"Failed to read model file metadata:\n{model_path}")
            return None

        if file_size > self._MAX_FILE_BYTES:
            self._show_error(
                f"Model file is too large ({file_size / (1024 * 1024):.1f} MB)."
            )
            return None

        return model_path

    def _load_shape_from_file(self, model_path: Path) -> TopoDS_Shape | None:
        suffix = model_path.suffix.lower()

        try:
            if suffix == ".stl":
                shape = TopoDS_Shape()
                reader = StlAPI_Reader()
                if not reader.Read(shape, str(model_path)):
                    return None
                return shape

            if suffix in {".step", ".stp"}:
                reader = STEPControl_Reader()
                status = reader.ReadFile(str(model_path))
                if status != IFSelect_RetDone:
                    return None
                reader.TransferRoots()
                return reader.OneShape()
        except Exception:
            return None

        return None

    @staticmethod
    def _parse_color(color_value: str | None):
        text = str(color_value or "").strip().lstrip("#")
        if len(text) != 6:
            return Quantity_Color(0.62, 0.65, 0.70, Quantity_TOC_RGB)

        try:
            r = int(text[0:2], 16) / 255.0
            g = int(text[2:4], 16) / 255.0
            b = int(text[4:6], 16) / 255.0
            return Quantity_Color(r, g, b, Quantity_TOC_RGB)
        except Exception:
            return Quantity_Color(0.62, 0.65, 0.70, Quantity_TOC_RGB)

    @staticmethod
    def _transform_for_part(part: dict):
        tx = float(part.get("offset_x", 0) or 0)
        ty = float(part.get("offset_y", 0) or 0)
        tz = float(part.get("offset_z", 0) or 0)

        rx = math.radians(float(part.get("rot_x", 0) or 0))
        ry = math.radians(float(part.get("rot_y", 0) or 0))
        rz = math.radians(float(part.get("rot_z", 0) or 0))

        t_total = gp_Trsf()
        t_total.SetIdentity()

        if abs(rx) > 1e-9:
            t = gp_Trsf()
            t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), rx)
            t_total = t.Multiplied(t_total)

        if abs(ry) > 1e-9:
            t = gp_Trsf()
            t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), ry)
            t_total = t.Multiplied(t_total)

        if abs(rz) > 1e-9:
            t = gp_Trsf()
            t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), rz)
            t_total = t.Multiplied(t_total)

        if abs(tx) > 1e-9 or abs(ty) > 1e-9 or abs(tz) > 1e-9:
            t = gp_Trsf()
            t.SetTranslation(gp_Vec(tx, ty, tz))
            t_total = t.Multiplied(t_total)

        return t_total

    def _apply_global_transform(self):
        if not self._display:
            return

        ax = math.radians(self._rotation_deg["x"])
        ay = math.radians(self._rotation_deg["y"])
        az = math.radians(self._rotation_deg["z"])

        base = gp_Trsf()
        base.SetIdentity()

        if self._alignment_plane == "XY":
            plane = gp_Trsf()
            plane.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), -math.pi / 2.0)
            base = plane.Multiplied(base)
        elif self._alignment_plane == "YZ":
            plane = gp_Trsf()
            plane.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.pi / 2.0)
            base = plane.Multiplied(base)

        if abs(ax) > 1e-9:
            t = gp_Trsf()
            t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), ax)
            base = t.Multiplied(base)
        if abs(ay) > 1e-9:
            t = gp_Trsf()
            t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), ay)
            base = t.Multiplied(base)
        if abs(az) > 1e-9:
            t = gp_Trsf()
            t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), az)
            base = t.Multiplied(base)

        for ais in self._ais_objects:
            ais.SetLocalTransformation(base)
            self._display.Context.Redisplay(ais, False)

        self._display.Context.UpdateCurrentViewer()
        self._render_measurements()

    @staticmethod
    def _apply_rotation_xyz(point: tuple[float, float, float], rx_deg: float, ry_deg: float, rz_deg: float):
        x, y, z = point
        rx = math.radians(float(rx_deg))
        ry = math.radians(float(ry_deg))
        rz = math.radians(float(rz_deg))

        if abs(rx) > 1e-9:
            cr, sr = math.cos(rx), math.sin(rx)
            y, z = y * cr - z * sr, y * sr + z * cr
        if abs(ry) > 1e-9:
            cr, sr = math.cos(ry), math.sin(ry)
            x, z = x * cr + z * sr, -x * sr + z * cr
        if abs(rz) > 1e-9:
            cr, sr = math.cos(rz), math.sin(rz)
            x, y = x * cr - y * sr, x * sr + y * cr
        return (x, y, z)

    @staticmethod
    def _normalize_vec(vec: tuple[float, float, float], default=(0.0, 1.0, 0.0)):
        x, y, z = vec
        n = math.sqrt(x * x + y * y + z * z)
        if n <= 1e-9:
            return default
        return (x / n, y / n, z / n)

    @staticmethod
    def _cross(a: tuple[float, float, float], b: tuple[float, float, float]):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    @staticmethod
    def _dot(a: tuple[float, float, float], b: tuple[float, float, float]):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    @staticmethod
    def _add(a: tuple[float, float, float], b: tuple[float, float, float]):
        return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

    @staticmethod
    def _sub(a: tuple[float, float, float], b: tuple[float, float, float]):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    @staticmethod
    def _mul(a: tuple[float, float, float], s: float):
        return (a[0] * s, a[1] * s, a[2] * s)

    def _part_transform_values(self, part_name: str):
        name = str(part_name or "").strip().lower()
        if not name:
            return None
        for idx, item in enumerate(self._part_items):
            if str(item.get("name") or "").strip().lower() == name:
                if 0 <= idx < len(self._part_transforms_cache):
                    return self._part_transforms_cache[idx]
        return None

    def _apply_part_transform(self, part_name: str, point: tuple[float, float, float]):
        transform = self._part_transform_values(part_name)
        if not transform:
            return point
        rotated = self._apply_rotation_xyz(
            point,
            float(transform.get("rx", 0) or 0),
            float(transform.get("ry", 0) or 0),
            float(transform.get("rz", 0) or 0),
        )
        return (
            rotated[0] + float(transform.get("x", 0) or 0),
            rotated[1] + float(transform.get("y", 0) or 0),
            rotated[2] + float(transform.get("z", 0) or 0),
        )

    def _apply_global_point_transform(self, point: tuple[float, float, float]):
        x, y, z = point
        if self._alignment_plane == "XY":
            y, z = z, -y
        elif self._alignment_plane == "YZ":
            x, y = -y, x
        return self._apply_rotation_xyz(
            (x, y, z),
            self._rotation_deg["x"],
            self._rotation_deg["y"],
            self._rotation_deg["z"],
        )

    def _resolve_anchor_point(self, part_name: str, xyz_value):
        xyz = self._parse_xyz_value(xyz_value)
        local = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
        part_applied = self._apply_part_transform(part_name, local)
        return self._apply_global_point_transform(part_applied)

    def _resolve_axis_direction(self, part_name: str, axis_xyz):
        axis = self._parse_xyz_value(axis_xyz, default=(0.0, 1.0, 0.0))
        d = self._normalize_vec((float(axis[0]), float(axis[1]), float(axis[2])))
        transform = self._part_transform_values(part_name)
        if transform:
            d = self._apply_rotation_xyz(
                d,
                float(transform.get("rx", 0) or 0),
                float(transform.get("ry", 0) or 0),
                float(transform.get("rz", 0) or 0),
            )
        d = self._apply_global_point_transform(d)
        return self._normalize_vec(d)

    @staticmethod
    def _point_to_gp(point: tuple[float, float, float]):
        return gp_Pnt(float(point[0]), float(point[1]), float(point[2]))

    def _clear_pick_marker(self):
        if self._pick_marker_ais is not None and self._display:
            try:
                self._display.Context.Remove(self._pick_marker_ais, False)
            except Exception:
                pass
        self._pick_marker_ais = None

    def _add_pick_marker(self, point: tuple[float, float, float], radius: float = 0.5):
        try:
            sphere = BRepPrimAPI_MakeSphere(self._point_to_gp(point), radius).Shape()
            ais = AIS_Shape(sphere)
            ais.SetColor(Quantity_Color(1.0, 0.4, 0.0, Quantity_TOC_RGB))
            self._display.Context.Display(ais, False)
            self._display.Context.UpdateCurrentViewer()
            self._pick_marker_ais = ais
        except Exception:
            self._pick_marker_ais = None

    def _add_text_label(self, position: tuple[float, float, float], text: str):
        try:
            label = AIS_TextLabel()
            label.SetText(str(text))
            label.SetPosition(self._point_to_gp(position))
            label.SetHeight(3.0)
            label.SetColor(Quantity_Color(1.0, 0.95, 0.0, Quantity_TOC_RGB))
            self._display.Context.Display(label, False)
            self._measurement_ais_objects.append(label)
        except Exception:
            pass

    def _detect_part_at_view_point(self, x: int, y: int) -> int:
        """Return the index into _ais_objects / _part_items under the cursor, or -1."""
        if not self._display or not self._ais_objects:
            return -1
        try:
            context = self._display.Context
            view = self._display.View
            context.MoveTo(int(x), int(y), view, True)
            if hasattr(context, "HasDetected") and context.HasDetected():
                detected = context.DetectedInteractive()
                for i, ais in enumerate(self._ais_objects):
                    try:
                        if ais == detected:
                            return i
                    except Exception:
                        continue
        except Exception:
            pass
        return -1

    def _add_measurement_line(self, start: tuple[float, float, float], end: tuple[float, float, float]):
        try:
            edge = BRepBuilderAPI_MakeEdge(self._point_to_gp(start), self._point_to_gp(end)).Edge()
            ais = AIS_Shape(edge)
            ais.SetColor(Quantity_Color(0.0, 0.86, 0.0, Quantity_TOC_RGB))
            self._display.Context.Display(ais, False)
            self._measurement_ais_objects.append(ais)
        except Exception:
            return

    def _draw_circle_polyline(self, center, axis, radius, segments=32):
        axis_n = self._normalize_vec(axis)
        ref = (1.0, 0.0, 0.0) if abs(axis_n[1]) > 0.9 else (0.0, 1.0, 0.0)
        u = self._normalize_vec(self._cross(axis_n, ref), default=(1.0, 0.0, 0.0))
        v = self._normalize_vec(self._cross(axis_n, u), default=(0.0, 0.0, 1.0))
        points = []
        for i in range(segments + 1):
            t = (2.0 * math.pi * i) / max(segments, 1)
            p = self._add(
                center,
                self._add(self._mul(u, radius * math.cos(t)), self._mul(v, radius * math.sin(t))),
            )
            points.append(p)
        for i in range(len(points) - 1):
            self._add_measurement_line(points[i], points[i + 1])

    def _render_measurements(self):
        if not self._display:
            return

        for ais in self._measurement_ais_objects:
            self._display.Context.Remove(ais, False)
        self._measurement_ais_objects = []

        if not self._measurements_visible:
            self._display.Context.UpdateCurrentViewer()
            return

        for item in self._measurement_overlays:
            if not isinstance(item, dict):
                continue

            filter_name = str(self._measurement_filter or "").strip().lower()
            if filter_name and str(item.get("name") or "").strip().lower() != filter_name:
                continue

            overlay_type = str(item.get("type") or "").strip().lower()

            if overlay_type == "distance":
                start = self._resolve_anchor_point(item.get("start_part", ""), item.get("start_xyz"))
                end = self._resolve_anchor_point(item.get("end_part", ""), item.get("end_xyz"))
                span = self._sub(end, start)
                axis_name = str(item.get("distance_axis") or "z").strip().lower()
                if axis_name in {"x", "y", "z"}:
                    axis_local = {
                        "x": (1.0, 0.0, 0.0),
                        "y": (0.0, 1.0, 0.0),
                        "z": (0.0, 0.0, 1.0),
                    }[axis_name]
                    axis_dir = self._resolve_axis_direction(item.get("start_part", ""), axis_local)
                    proj = self._dot(span, axis_dir)
                    end = self._add(start, self._mul(axis_dir, proj))
                self._add_measurement_line(start, end)
                d_vec = self._sub(end, start)
                dist_val = math.sqrt(max(0.0, self._dot(d_vec, d_vec)))
                midpoint = self._add(start, self._mul(d_vec, 0.5))
                label_mode = item.get("label_value_mode", "measured")
                custom_val = item.get("label_custom_value", "")
                if label_mode == "custom" and custom_val:
                    label_text = f"{item['name']}: {custom_val}"
                else:
                    label_text = f"{item['name']}: {dist_val:.1f} mm"
                self._add_text_label(midpoint, label_text)

            elif overlay_type == "diameter_ring":
                center = self._resolve_anchor_point(item.get("part", ""), item.get("center_xyz"))
                axis = self._resolve_axis_direction(item.get("part", ""), item.get("axis_xyz"))
                radius = max(0.0, float(item.get("diameter", 0) or 0) / 2.0)
                if radius > 1e-6:
                    self._draw_circle_polyline(center, axis, radius, segments=28)
                    label_pos = self._add(center, self._mul(axis, radius * 1.2))
                    label_text = f"{item['name']}: D={item['diameter']:.1f} mm"
                    self._add_text_label(label_pos, label_text)

            elif overlay_type == "radius":
                center = self._resolve_anchor_point(item.get("part", ""), item.get("center_xyz"))
                axis = self._resolve_axis_direction(item.get("part", ""), item.get("axis_xyz"))
                radius = max(0.0, float(item.get("radius", 0) or 0))
                if radius > 1e-6:
                    ref = (1.0, 0.0, 0.0) if abs(axis[1]) > 0.9 else (0.0, 1.0, 0.0)
                    radial = self._normalize_vec(self._cross(axis, ref), default=(1.0, 0.0, 0.0))
                    edge = self._add(center, self._mul(radial, radius))
                    self._add_measurement_line(center, edge)
                    label_pos = self._add(center, self._mul(radial, radius * 0.5))
                    label_text = f"{item['name']}: R={item['radius']:.1f} mm"
                    self._add_text_label(label_pos, label_text)

            elif overlay_type == "angle":
                center = self._resolve_anchor_point(item.get("part", ""), item.get("center_xyz"))
                start = self._resolve_anchor_point(item.get("part", ""), item.get("start_xyz"))
                end = self._resolve_anchor_point(item.get("part", ""), item.get("end_xyz"))
                self._add_measurement_line(center, start)
                self._add_measurement_line(center, end)
                v1 = self._normalize_vec(self._sub(start, center))
                v2 = self._normalize_vec(self._sub(end, center))
                dot_val = max(-1.0, min(1.0, self._dot(v1, v2)))
                angle_deg = math.degrees(math.acos(dot_val))
                bisector = self._normalize_vec(self._add(v1, v2))
                arm_len = math.sqrt(max(0.0, self._dot(self._sub(start, center), self._sub(start, center))))
                label_pos = self._add(center, self._mul(bisector, arm_len * 0.5)) if arm_len > 1e-9 else center
                label_text = f"{item['name']}: {angle_deg:.1f}\u00b0"
                self._add_text_label(label_pos, label_text)

        self._display.Context.UpdateCurrentViewer()

    def _pick_point_from_view(self, x: int, y: int):
        if not self._display:
            return None

        context = self._display.Context
        view = self._display.View

        try:
            context.MoveTo(int(x), int(y), view, True)
            if hasattr(context, "HasDetected") and context.HasDetected() and hasattr(context, "DetectedPoint"):
                p = context.DetectedPoint()
                return (float(p.X()), float(p.Y()), float(p.Z()))
        except Exception:
            pass

        try:
            converted = view.Convert(int(x), int(y))
            if isinstance(converted, (tuple, list)) and len(converted) >= 3:
                return (float(converted[0]), float(converted[1]), float(converted[2]))
        except Exception:
            pass

        return None

    def eventFilter(self, watched, event):
        if watched is self._viewer and self._point_picking_enabled and event.type() == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                pos = event.position()
                ix, iy = int(pos.x()), int(pos.y())

                detected_index = self._detect_part_at_view_point(ix, iy)
                if detected_index >= 0:
                    part_idx = detected_index
                else:
                    part_idx = int(self._selected_part_index)

                picked = self._pick_point_from_view(ix, iy)
                if picked is not None:
                    part_name = ""
                    if 0 <= part_idx < len(self._part_items):
                        part_name = str(self._part_items[part_idx].get("name") or "")
                    self._clear_pick_marker()
                    self._add_pick_marker(picked)
                    self.point_picked.emit(
                        {
                            "partIndex": part_idx,
                            "partName": part_name,
                            "x": round(float(picked[0]), 4),
                            "y": round(float(picked[1]), 4),
                            "z": round(float(picked[2]), 4),
                        }
                    )
                    return True
        return super().eventFilter(watched, event)

    def clear(self):
        self._part_items = []
        self._loaded_parts = []
        self._part_transforms_cache = []
        self._selected_part_index = -1

        if not self._display:
            return

        self._clear_pick_marker()
        for ais in self._ais_objects:
            self._display.Context.Remove(ais, False)
        self._ais_objects = []
        for ais in self._measurement_ais_objects:
            self._display.Context.Remove(ais, False)
        self._measurement_ais_objects = []
        self._display.Context.UpdateCurrentViewer()

    def load_stl(self, stl_path: str | Path | None, label: str | None = None):
        del label

        self.clear()
        model_path = self._safe_model_path(stl_path)
        if model_path is None:
            return

        if not HAS_OCC:
            self._show_error("pythonocc-core is not available.")
            return

        shape = self._load_shape_from_file(model_path)
        if shape is None:
            self._show_error(f"Failed to load model:\n{model_path}")
            return

        ais = AIS_Shape(shape)
        self._display.Context.Display(ais, False)
        self._ais_objects = [ais]
        self._part_items = [{"name": "", "source": str(model_path)}]
        self._part_transforms_cache = [{"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0}]
        self._show_viewer()
        self._apply_global_transform()
        self._display.FitAll()
        self._render_measurements()

    def load_parts(self, parts: list[dict] | None):
        self.clear()

        if not parts:
            return

        if not HAS_OCC:
            self._show_error("pythonocc-core is not available.")
            return

        self._loaded_parts = [dict(p) for p in parts]
        self._part_items = []
        self._part_transforms_cache = []

        for part in parts:
            model_path = self._safe_model_path(part.get("file"))
            if model_path is None:
                continue

            shape = self._load_shape_from_file(model_path)
            if shape is None:
                continue

            transform = self._transform_for_part(part)
            transformed = BRepBuilderAPI_Transform(shape, transform, True).Shape()

            ais = AIS_Shape(transformed)
            ais.SetColor(self._parse_color(part.get("color")))
            self._display.Context.Display(ais, False)
            self._ais_objects.append(ais)

            self._part_items.append(
                {
                    "name": str(part.get("name") or "").strip(),
                    "source": str(model_path),
                    "file": str(part.get("file") or ""),
                }
            )
            self._part_transforms_cache.append(
                {
                    "x": float(part.get("offset_x", 0) or 0),
                    "y": float(part.get("offset_y", 0) or 0),
                    "z": float(part.get("offset_z", 0) or 0),
                    "rx": float(part.get("rot_x", 0) or 0),
                    "ry": float(part.get("rot_y", 0) or 0),
                    "rz": float(part.get("rot_z", 0) or 0),
                }
            )

        if not self._ais_objects:
            self._show_error("No valid parts could be loaded.")
            return

        self._show_viewer()
        self._apply_global_transform()
        self._display.FitAll()
        self._render_measurements()

    def set_alignment_plane(self, plane: str):
        normalized = (plane or "XZ").strip().upper()
        if normalized not in {"XZ", "XY", "YZ"}:
            normalized = "XZ"
        self._alignment_plane = normalized
        if self._display and self._ais_objects:
            self._apply_global_transform()

    def rotate_model(self, axis: str, degrees: float = 90.0):
        key = (axis or "").strip().lower()
        if key not in {"x", "y", "z"}:
            return

        self._rotation_deg[key] += float(degrees)
        if self._display and self._ais_objects:
            self._apply_global_transform()

    def reset_model_rotation(self):
        self._rotation_deg = {"x": 0.0, "y": 0.0, "z": 0.0}
        if self._display and self._ais_objects:
            self._apply_global_transform()

    def set_preview_transform(self, plane: str, x: float, y: float, z: float):
        del x, y, z
        self.set_alignment_plane(plane)

    def set_transform_edit_enabled(self, enabled: bool):
        self._transform_edit_enabled = bool(enabled)

    def set_transform_mode(self, mode: str):
        if mode in {"translate", "rotate"}:
            self._transform_mode = mode

    def get_part_transforms(self, callback):
        if callable(callback):
            callback(self._part_transforms_cache)

    def set_part_transforms(self, transforms: list[dict]):
        normalized = [
            {
                "x": float(item.get("x", 0) or 0),
                "y": float(item.get("y", 0) or 0),
                "z": float(item.get("z", 0) or 0),
                "rx": float(item.get("rx", 0) or 0),
                "ry": float(item.get("ry", 0) or 0),
                "rz": float(item.get("rz", 0) or 0),
            }
            for item in (transforms or [])
            if isinstance(item, dict)
        ]
        self._part_transforms_cache = normalized

        if self._loaded_parts:
            for idx, part in enumerate(self._loaded_parts):
                if idx >= len(normalized):
                    continue
                t = normalized[idx]
                part["offset_x"] = t["x"]
                part["offset_y"] = t["y"]
                part["offset_z"] = t["z"]
                part["rot_x"] = t["rx"]
                part["rot_y"] = t["ry"]
                part["rot_z"] = t["rz"]
            self.load_parts(self._loaded_parts)

    def select_part(self, index: int):
        self._selected_part_index = int(index)
        self.part_selected.emit(self._selected_part_index)

    def set_selected_part_index(self, index: int):
        self.select_part(index)

    def reset_selected_part_transform(self):
        if 0 <= self._selected_part_index < len(self._part_transforms_cache):
            self._part_transforms_cache[self._selected_part_index] = {
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "rx": 0.0,
                "ry": 0.0,
                "rz": 0.0,
            }
            self.transform_changed.emit(
                self._selected_part_index,
                self._part_transforms_cache[self._selected_part_index],
            )
            self.set_part_transforms(self._part_transforms_cache)

    @staticmethod
    def _parse_xyz_value(value, default=(0.0, 0.0, 0.0)):
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            try:
                return [float(value[0]), float(value[1]), float(value[2])]
            except Exception:
                return [float(default[0]), float(default[1]), float(default[2])]

        text = str(value or "").strip()
        if not text:
            return [float(default[0]), float(default[1]), float(default[2])]

        parts = [token for token in re.split(r"[\s,;]+", text.replace(",", " ")) if token]
        if len(parts) < 3:
            return [float(default[0]), float(default[1]), float(default[2])]
        try:
            return [float(parts[0]), float(parts[1]), float(parts[2])]
        except Exception:
            return [float(default[0]), float(default[1]), float(default[2])]

    @classmethod
    def _normalize_measurement_overlay(cls, overlay, index: int = 0):
        if not isinstance(overlay, dict):
            return None

        overlay_type = str(overlay.get("type") or "").strip().lower()
        if overlay_type == "distance":
            distance_axis = str(overlay.get("distance_axis") or "z").strip().lower()
            if distance_axis not in {"direct", "x", "y", "z"}:
                distance_axis = "z"
            label_value_mode = str(overlay.get("label_value_mode") or "measured").strip().lower()
            if label_value_mode not in {"measured", "custom"}:
                label_value_mode = "measured"
            return {
                "type": "distance",
                "name": str(overlay.get("name") or f"Distance {index + 1}").strip() or f"Distance {index + 1}",
                "start_part": str(overlay.get("start_part") or "").strip(),
                "start_xyz": cls._parse_xyz_value(overlay.get("start_xyz")),
                "end_part": str(overlay.get("end_part") or "").strip(),
                "end_xyz": cls._parse_xyz_value(overlay.get("end_xyz")),
                "distance_axis": distance_axis,
                "label_value_mode": label_value_mode,
                "label_custom_value": str(overlay.get("label_custom_value") or "").strip(),
            }

        if overlay_type == "diameter_ring":
            diameter_raw = overlay.get("diameter", 0)
            try:
                diameter = float(str(diameter_raw).replace(",", "."))
            except Exception:
                diameter = 0.0
            return {
                "type": "diameter_ring",
                "name": str(overlay.get("name") or f"Diameter {index + 1}").strip() or f"Diameter {index + 1}",
                "part": str(overlay.get("part") or "").strip(),
                "center_xyz": cls._parse_xyz_value(overlay.get("center_xyz")),
                "axis_xyz": cls._parse_xyz_value(overlay.get("axis_xyz"), default=(0.0, 1.0, 0.0)),
                "diameter": diameter,
            }

        if overlay_type == "radius":
            radius_raw = overlay.get("radius", 0)
            try:
                radius = float(str(radius_raw).replace(",", "."))
            except Exception:
                radius = 0.0
            return {
                "type": "radius",
                "name": str(overlay.get("name") or f"Radius {index + 1}").strip() or f"Radius {index + 1}",
                "part": str(overlay.get("part") or "").strip(),
                "center_xyz": cls._parse_xyz_value(overlay.get("center_xyz")),
                "axis_xyz": cls._parse_xyz_value(overlay.get("axis_xyz"), default=(0.0, 1.0, 0.0)),
                "radius": radius,
            }

        if overlay_type == "angle":
            return {
                "type": "angle",
                "name": str(overlay.get("name") or f"Angle {index + 1}").strip() or f"Angle {index + 1}",
                "part": str(overlay.get("part") or "").strip(),
                "center_xyz": cls._parse_xyz_value(overlay.get("center_xyz")),
                "start_xyz": cls._parse_xyz_value(overlay.get("start_xyz"), default=(1.0, 0.0, 0.0)),
                "end_xyz": cls._parse_xyz_value(overlay.get("end_xyz"), default=(0.0, 1.0, 0.0)),
            }

        return None

    def set_measurement_overlays(self, overlays):
        normalized = []
        for idx, overlay in enumerate(overlays or []):
            item = self._normalize_measurement_overlay(overlay, idx)
            if item is not None:
                normalized.append(item)
        self._measurement_overlays = normalized
        self._render_measurements()

    def set_measurements_visible(self, visible: bool):
        self._measurements_visible = bool(visible)
        self._render_measurements()

    def set_measurement_filter(self, name: str | None):
        value = str(name or "").strip()
        self._measurement_filter = value or None
        self._render_measurements()

    def set_point_picking_enabled(self, enabled: bool):
        self._point_picking_enabled = bool(enabled)

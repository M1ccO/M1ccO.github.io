import json
import math
import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QGridLayout, QLabel, QVBoxLayout, QWidget
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from config import (
    JAW_MODELS_ROOT_DEFAULT,
    PREVIEW_DIR,
    SHARED_UI_PREFERENCES_PATH,
    TOOL_MODELS_ROOT_DEFAULT,
)
from shared.ui.preview_bridge_adapter import build_js_call, normalize_index_list, parse_title_event
from shared.data.model_paths import read_model_roots, resolve_model_path


class ScrollFriendlyWebView(QWebEngineView):
    """Forward plain wheel scrolling to the surrounding scroll area.

    Ctrl + wheel is reserved for 3D zoom inside the viewer itself.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wheel_zoom_mode = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._find_parent_scroll_area() is not None:
            # Toggle wheel mode only when this view sits inside a scroll area.
            # First click enables 3D zoom, second click returns wheel to page scroll.
            self._wheel_zoom_mode = not self._wheel_zoom_mode
            self.page().runJavaScript(
                f"window.setWheelZoomEnabled && window.setWheelZoomEnabled({str(self._wheel_zoom_mode).lower()});"
            )
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            super().wheelEvent(event)
            return

        if self._wheel_zoom_mode:
            super().wheelEvent(event)
            return

        scroll_area = self._find_parent_scroll_area()
        if scroll_area is None:
            super().wheelEvent(event)
            return

        delta = event.pixelDelta().y()
        if delta == 0:
            delta = event.angleDelta().y()

        if delta:
            scrollbar = scroll_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.value() - delta)
            event.accept()
            return

        event.ignore()

    def reset_wheel_mode(self):
        self._wheel_zoom_mode = False
        self.page().runJavaScript("window.setWheelZoomEnabled && window.setWheelZoomEnabled(false);")

    def _find_parent_scroll_area(self):
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                return parent
            parent = parent.parentWidget()
        return None


class PreviewWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        print(f"[Preview JS] {source_id}:{line_number}: {message}")
        super().javaScriptConsoleMessage(level, message, line_number, source_id)


class StlPreviewWidget(QWidget):
    transform_changed = Signal(int, dict)
    part_selected = Signal(int)
    part_selection_changed = Signal(list)
    point_picked = Signal(dict)
    measurement_updated = Signal(dict)

    def __init__(self, stl_path: str | None = None, parent=None):
        super().__init__(parent)

        self._viewer_html = PREVIEW_DIR / "index.html"

        self._page_ready = False
        self._pending_stl_path = None
        self._pending_label = None
        self._pending_parts = None
        self._loaded_part_files = []
        self._rendering_enabled = True
        self._alignment_plane = 'XZ'
        self._rotation_deg = {'x': 0, 'y': 0, 'z': 0}
        self._transform_edit_enabled = False
        self._transform_mode = 'translate'
        self._fine_transform_enabled = False
        self._part_transforms_cache = []
        self._selected_part_index = -1
        self._selected_part_indices = []
        self._measurement_overlays = []
        self._measurements_visible = False
        self._measurement_filter = None
        self._measurement_drag_enabled = False
        self._point_picking_enabled = False
        self._control_hint_text = ''
        self._axis_orbit_visible = False
        self._selection_caption = ''

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.hide()

        self._view_host = QWidget()
        self._view_layout = QGridLayout(self._view_host)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self._view_layout.setSpacing(0)

        self._web = ScrollFriendlyWebView()
        self._web.setPage(PreviewWebPage(self._web))
        self._view_layout.addWidget(self._web, 0, 0)

        self._selection_caption_wrap = QWidget()
        self._selection_caption_wrap.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._selection_caption_wrap.setStyleSheet('background: transparent;')
        self._selection_caption_wrap.hide()
        self._selection_caption_layout = QVBoxLayout(self._selection_caption_wrap)
        self._selection_caption_layout.setContentsMargins(4, 4, 0, 0)
        self._selection_caption_layout.setSpacing(0)
        self._selection_caption_label = QLabel('')
        self._selection_caption_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._selection_caption_label.setStyleSheet(
            'background-color: rgba(255, 255, 255, 0.86);'
            'border: 1px solid #d7e0e8;'
            'border-radius: 4px;'
            'padding: 2px 6px;'
            'color: #607181;'
            'font-size: 9pt;'
            'font-weight: 500;'
        )
        self._selection_caption_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._selection_caption_label.setWordWrap(False)
        self._selection_caption_layout.addWidget(self._selection_caption_label, 0, Qt.AlignLeft | Qt.AlignTop)
        self._view_layout.addWidget(self._selection_caption_wrap, 0, 0, Qt.AlignLeft | Qt.AlignTop)

        self._layout.addWidget(self._view_host, 1)
        self._layout.addWidget(self._error_label)

        if not self._viewer_html.exists():
            self._show_error(f"Viewer HTML not found:\n{self._viewer_html}")
            return

        self._web.loadFinished.connect(self._on_load_finished)
        self._web.page().titleChanged.connect(self._on_title_changed)
        self._web.load(QUrl.fromLocalFile(str(self._viewer_html)))

        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_application_state_changed)
            app.focusWindowChanged.connect(self._on_focus_window_changed)

        if stl_path:
            self.load_stl(stl_path)

    def _show_error(self, message: str):
        self._web.hide()
        self._selection_caption_wrap.hide()
        self._error_label.setText(message)
        self._error_label.show()

    def _show_web(self):
        self._error_label.hide()
        self._web.show()
        if self._selection_caption:
            self._selection_caption_wrap.show()
            self._selection_caption_wrap.raise_()

    def _call_js(self, function_name: str, *args):
        if not self._page_ready:
            return
        js = build_js_call(function_name, *args)
        self._web.page().runJavaScript(js)

    def _call_js_raw(self, js: str):
        if not self._page_ready:
            return
        self._web.page().runJavaScript(js)

    def _apply_hint_text(self):
        if not self._page_ready:
            return
        self._call_js('setControlHintText', str(self._control_hint_text or ''))

    def _sync_rendering_state(self):
        app = QApplication.instance()
        app_active = True
        if app is not None:
            app_active = app.applicationState() == Qt.ApplicationActive

        host_window = self.window()
        window_ready = True
        is_detached_preview = False
        if host_window is not None:
            # Detached 3D preview should keep rendering while visible even when
            # the main Tool Library window is the active one.
            is_detached_preview = bool(host_window.property('detachedPreviewDialog'))
            if is_detached_preview:
                window_ready = host_window.isVisible()
            else:
                window_ready = host_window.isActiveWindow()

        if is_detached_preview:
            should_render = bool(self.isVisible() and window_ready)
        else:
            should_render = bool(self.isVisible() and app_active and window_ready)
        if should_render == self._rendering_enabled:
            return

        self._rendering_enabled = should_render
        self._call_js('setRenderingEnabled', bool(should_render))

    def _on_application_state_changed(self, _state):
        self._sync_rendering_state()

    def _on_focus_window_changed(self, _window):
        self._sync_rendering_state()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_rendering_state()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_rendering_state()

    def _on_load_finished(self, ok: bool):
        self._page_ready = ok

        if not ok:
            self._show_error("Failed to load viewer HTML.")
            return

        self._show_web()
        self._apply_hint_text()

        if self._pending_parts:
            self._send_parts_to_viewer(self._pending_parts)
        elif self._pending_stl_path:
            self._send_model_to_viewer(self._pending_stl_path, self._pending_label)

        self._apply_preview_transform_state()
        self._apply_transform_editor_state()
        self._apply_measurement_state()
        self._apply_axis_orbit_state()
        self._sync_rendering_state()

    def _send_model_to_viewer(self, stl_path: Path, label: str | None = None):
        stl_url = QUrl.fromLocalFile(str(stl_path)).toString()

        if label:
            js = f"window.loadModel && window.loadModel({json.dumps(stl_url)}, {json.dumps(label)});"
        else:
            js = f"window.loadModel && window.loadModel({json.dumps(stl_url)});"

        self._web.page().runJavaScript(js)

    def _build_parts_payload(self, parts: list[dict] | None) -> list[dict]:
        tools_root, jaws_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        payload = []
        for part in (parts or []):
            file_value = (part.get('file') or '').strip()
            if not file_value:
                continue

            path = resolve_model_path(file_value, tools_root, jaws_root)

            if not path.exists():
                continue

            payload.append({
                'name': part.get('name', ''),
                'file': QUrl.fromLocalFile(str(path)).toString(),
                'color': part.get('color', '#9ea7b3'),
                'offset_x': part.get('offset_x', 0),
                'offset_y': part.get('offset_y', 0),
                'offset_z': part.get('offset_z', 0),
                'rot_x': part.get('rot_x', 0),
                'rot_y': part.get('rot_y', 0),
                'rot_z': part.get('rot_z', 0),
            })

        return payload

    def _send_parts_to_viewer(self, payload: list[dict]):
        self._loaded_part_files = [str(part.get('file') or '') for part in payload]

        js_payload = json.dumps(payload)
        js = f"window.loadAssembly && window.loadAssembly({js_payload});"
        self._call_js_raw(js)

    def _update_parts_in_viewer(self, payload: list[dict]):
        transforms_payload = [
            {
                'x': part.get('offset_x', 0),
                'y': part.get('offset_y', 0),
                'z': part.get('offset_z', 0),
                'rx': part.get('rot_x', 0),
                'ry': part.get('rot_y', 0),
                'rz': part.get('rot_z', 0),
            }
            for part in payload
        ]
        colors_payload = [str(part.get('color') or '#9ea7b3') for part in payload]
        names_payload = [str(part.get('name') or '') for part in payload]

        self._call_js('setPartTransforms', transforms_payload)
        self._call_js('setPartColors', colors_payload)
        self._call_js('setPartNames', names_payload)

    def clear(self):
        self._pending_stl_path = None
        self._pending_label = None
        self._pending_parts = None
        self._loaded_part_files = []
        self._part_transforms_cache = []
        self._selected_part_index = -1
        self._selected_part_indices = []
        self.set_selection_caption(None)
        self._web.reset_wheel_mode()

        if self._page_ready:
            self._call_js('clearModel')

    def load_stl(self, stl_path: str | Path | None, label: str | None = None):
        self._pending_parts = None
        self._loaded_part_files = []
        self._part_transforms_cache = []
        self._selected_part_index = -1
        self._selected_part_indices = []
        self.set_selection_caption(None)
        self._web.reset_wheel_mode()

        if not stl_path:
            self.clear()
            return

        tools_root, jaws_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        stl_path = resolve_model_path(str(stl_path), tools_root, jaws_root)

        if not stl_path.exists():
            self._show_error(f"STL file not found:\n{stl_path}")
            return

        self._pending_stl_path = stl_path
        self._pending_label = label
        self._show_web()

        if self._page_ready:
            self._send_model_to_viewer(stl_path, label)

    def load_parts(self, parts: list[dict] | None):
        self._web.reset_wheel_mode()

        self._pending_stl_path = None
        self._pending_label = None
        self.set_selection_caption(None)

        payload = self._build_parts_payload(parts)

        if not payload:
            self.clear()
            return

        self._pending_parts = payload
        self._part_transforms_cache = [
            {
                'x': part.get('offset_x', 0),
                'y': part.get('offset_y', 0),
                'z': part.get('offset_z', 0),
                'rx': part.get('rot_x', 0),
                'ry': part.get('rot_y', 0),
                'rz': part.get('rot_z', 0),
            }
            for part in payload
        ]
        self._show_web()

        if self._page_ready:
            part_files = [str(part.get('file') or '') for part in payload]
            same_files_loaded = part_files == self._loaded_part_files

            if same_files_loaded:
                self._update_parts_in_viewer(payload)
            else:
                self._send_parts_to_viewer(payload)
                self._apply_preview_transform_state()
                self._apply_transform_editor_state()
                self._apply_measurement_state()

    def _apply_preview_transform_state(self):
        if not self._page_ready:
            return
        self._call_js('setAlignmentPlane', self._alignment_plane)
        self._call_js('resetModelRotation')
        for axis, deg in self._rotation_deg.items():
            if deg:
                self._call_js('rotateModel', axis, float(deg))

    def set_alignment_plane(self, plane: str):
        normalized = (plane or 'XZ').strip().upper()
        if normalized not in {'XZ', 'XY', 'YZ'}:
            normalized = 'XZ'
        self._alignment_plane = normalized
        self._call_js('setAlignmentPlane', self._alignment_plane)

    def rotate_model(self, axis: str, degrees: float = 90.0):
        key = (axis or '').strip().lower()
        if key not in {'x', 'y', 'z'}:
            return
        self._rotation_deg[key] += float(degrees)
        self._call_js('rotateModel', key, float(degrees))

    def reset_model_rotation(self):
        self._rotation_deg = {'x': 0, 'y': 0, 'z': 0}
        self._call_js('resetModelRotation')

    def _apply_transform_editor_state(self):
        if not self._page_ready:
            return

        self._call_js('setTransformEditEnabled', bool(self._transform_edit_enabled))
        self._call_js('setTransformMode', self._transform_mode)
        self._call_js('setFineTransformEnabled', bool(self._fine_transform_enabled))

        if self._part_transforms_cache:
            self._call_js('setPartTransforms', self._part_transforms_cache)

        self._call_js('selectPart', int(self._selected_part_index))

    @staticmethod
    def _parse_xyz_value(value, default=(0.0, 0.0, 0.0)):
        def _finite(v, fallback):
            try:
                num = float(v)
            except Exception:
                return float(fallback)
            return num if math.isfinite(num) else float(fallback)

        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return [
                _finite(value[0], default[0]),
                _finite(value[1], default[1]),
                _finite(value[2], default[2]),
            ]

        text = str(value or '').strip()
        if not text:
            return [float(default[0]), float(default[1]), float(default[2])]

        parts = [token for token in re.split(r'[\s,;]+', text.replace(',', ' ')) if token]
        if len(parts) < 3:
            return [float(default[0]), float(default[1]), float(default[2])]
        return [
            _finite(parts[0], default[0]),
            _finite(parts[1], default[1]),
            _finite(parts[2], default[2]),
        ]

    @staticmethod
    def _parse_float_value(value, default: float = 0.0) -> float:
        try:
            numeric = float(str(value).strip().replace(',', '.'))
        except Exception:
            return float(default)
        return numeric if math.isfinite(numeric) else float(default)

    @staticmethod
    def _normalize_distance_space(part_name, part_index, point_space) -> str:
        has_part_ref = bool(str(part_name or '').strip())
        if not has_part_ref:
            try:
                has_part_ref = int(part_index) >= 0
            except Exception:
                has_part_ref = False
        normalized = str(point_space or '').strip().lower()
        if normalized not in {'local', 'world'}:
            return 'local' if has_part_ref else 'world'
        if normalized == 'world' and has_part_ref:
            # Legacy migration: part-bound coordinates must stay local to follow transforms.
            return 'local'
        return normalized

    @classmethod
    def _normalize_measurement_overlay(cls, overlay, index: int = 0):
        if not isinstance(overlay, dict):
            return None

        overlay_type = str(overlay.get('type') or '').strip().lower()
        if overlay_type == 'distance':
            distance_axis = str(overlay.get('distance_axis') or 'z').strip().lower()
            if distance_axis not in {'direct', 'x', 'y', 'z'}:
                distance_axis = 'z'
            label_value_mode = str(overlay.get('label_value_mode') or 'measured').strip().lower()
            if label_value_mode not in {'measured', 'custom'}:
                label_value_mode = 'measured'
            start_part = str(overlay.get('start_part') or '').strip()
            end_part = str(overlay.get('end_part') or '').strip()
            try:
                start_part_index = int(overlay.get('start_part_index', -1) or -1)
            except Exception:
                start_part_index = -1
            try:
                end_part_index = int(overlay.get('end_part_index', -1) or -1)
            except Exception:
                end_part_index = -1
            start_space = cls._normalize_distance_space(
                start_part,
                start_part_index,
                overlay.get('start_space', ''),
            )
            end_space = cls._normalize_distance_space(
                end_part,
                end_part_index,
                overlay.get('end_space', ''),
            )
            offset_raw = overlay.get('offset_xyz')
            offset_text = str(offset_raw or '').strip()
            offset_xyz = cls._parse_xyz_value(offset_raw) if offset_text else ''
            start_shift = str(overlay.get('start_shift') or '0').strip() or '0'
            end_shift = str(overlay.get('end_shift') or '0').strip() or '0'
            active_point = str(overlay.get('active_point') or '').strip().lower()
            if active_point not in {'start', 'end'}:
                active_point = ''
            return {
                'type': 'distance',
                'name': str(overlay.get('name') or f'Distance {index + 1}').strip() or f'Distance {index + 1}',
                'start_part': start_part,
                'start_part_index': start_part_index,
                'start_xyz': cls._parse_xyz_value(overlay.get('start_xyz')),
                'start_space': start_space,
                'end_part': end_part,
                'end_part_index': end_part_index,
                'end_xyz': cls._parse_xyz_value(overlay.get('end_xyz')),
                'end_space': end_space,
                'distance_axis': distance_axis,
                'label_value_mode': label_value_mode,
                'label_custom_value': str(overlay.get('label_custom_value') or '').strip(),
                'offset_xyz': offset_xyz,
                'start_shift': start_shift,
                'end_shift': end_shift,
                'active_point': active_point,
            }

        if overlay_type == 'diameter_ring':
            diameter_raw = overlay.get('diameter', 0)
            try:
                diameter = float(str(diameter_raw).replace(',', '.'))
            except Exception:
                diameter = 0.0
            center_raw = overlay.get('center_xyz', '')
            center_text = str(center_raw or '').strip()
            edge_raw = overlay.get('edge_xyz', '')
            edge_text = str(edge_raw or '').strip()
            offset_raw = overlay.get('offset_xyz', '')
            offset_text = str(offset_raw or '').strip()
            try:
                part_index = int(overlay.get('part_index', -1) or -1)
            except Exception:
                part_index = -1
            diameter_mode = str(overlay.get('diameter_mode') or '').strip().lower()
            if diameter_mode not in {'measured', 'manual'}:
                diameter_mode = 'measured' if edge_text else 'manual'
            visual_offset_mm = cls._parse_float_value(overlay.get('diameter_visual_offset_mm', 1.0), 1.0)
            axis_xyz = cls._parse_xyz_value(overlay.get('axis_xyz'), default=(0.0, 0.0, 1.0))
            axis_mode = str(overlay.get('diameter_axis_mode') or '').strip().lower()
            if axis_mode not in {'x', 'y', 'z', 'direct'}:
                ax, ay, az = axis_xyz
                length = float((ax * ax + ay * ay + az * az) ** 0.5)
                if length <= 1e-8:
                    axis_mode = 'z'
                else:
                    nx = ax / length
                    ny = ay / length
                    nz = az / length
                    tol = 1e-3
                    if abs(abs(nx) - 1.0) <= tol and abs(ny) <= tol and abs(nz) <= tol:
                        axis_mode = 'x'
                    elif abs(abs(ny) - 1.0) <= tol and abs(nx) <= tol and abs(nz) <= tol:
                        axis_mode = 'y'
                    elif abs(abs(nz) - 1.0) <= tol and abs(nx) <= tol and abs(ny) <= tol:
                        axis_mode = 'z'
                    else:
                        axis_mode = 'direct'
            if axis_mode == 'x':
                axis_xyz = [1.0, 0.0, 0.0]
            elif axis_mode == 'y':
                axis_xyz = [0.0, 1.0, 0.0]
            elif axis_mode == 'z':
                axis_xyz = [0.0, 0.0, 1.0]
            else:
                ax, ay, az = axis_xyz
                length = float((ax * ax + ay * ay + az * az) ** 0.5)
                if length <= 1e-8:
                    axis_xyz = [0.0, 0.0, 1.0]
                else:
                    axis_xyz = [ax / length, ay / length, az / length]
            return {
                'type': 'diameter_ring',
                'name': str(overlay.get('name') or f'Diameter {index + 1}').strip() or f'Diameter {index + 1}',
                'part': str(overlay.get('part') or '').strip(),
                'part_index': part_index,
                'center_xyz': cls._parse_xyz_value(center_raw) if center_text else '',
                'edge_xyz': cls._parse_xyz_value(edge_raw) if edge_text else '',
                'axis_xyz': axis_xyz,
                'diameter_axis_mode': axis_mode,
                'offset_xyz': cls._parse_xyz_value(offset_raw) if offset_text else '',
                'diameter_visual_offset_mm': visual_offset_mm,
                'diameter_mode': diameter_mode,
                'diameter': diameter,
            }

        if overlay_type == 'radius':
            radius_raw = overlay.get('radius', 0)
            try:
                radius = float(str(radius_raw).replace(',', '.'))
            except Exception:
                radius = 0.0
            return {
                'type': 'radius',
                'name': str(overlay.get('name') or f'Radius {index + 1}').strip() or f'Radius {index + 1}',
                'part': str(overlay.get('part') or '').strip(),
                'center_xyz': cls._parse_xyz_value(overlay.get('center_xyz')),
                'axis_xyz': cls._parse_xyz_value(overlay.get('axis_xyz'), default=(0.0, 1.0, 0.0)),
                'radius': radius,
            }

        if overlay_type == 'angle':
            return {
                'type': 'angle',
                'name': str(overlay.get('name') or f'Angle {index + 1}').strip() or f'Angle {index + 1}',
                'part': str(overlay.get('part') or '').strip(),
                'center_xyz': cls._parse_xyz_value(overlay.get('center_xyz')),
                'start_xyz': cls._parse_xyz_value(overlay.get('start_xyz'), default=(1.0, 0.0, 0.0)),
                'end_xyz': cls._parse_xyz_value(overlay.get('end_xyz'), default=(0.0, 1.0, 0.0)),
            }

        return None

    def _apply_measurement_state(self):
        if not self._page_ready:
            return

        self._call_js('setMeasurements', self._measurement_overlays)
        self._call_js('setMeasurementsVisible', bool(self._measurements_visible))
        filter_value = self._measurement_filter if self._measurement_filter else ''
        self._call_js('setMeasurementFilter', filter_value)
        self._call_js('setMeasurementDragEnabled', bool(self._measurement_drag_enabled))

    def _apply_axis_orbit_state(self):
        if not self._page_ready:
            return
        self._call_js('setAxisOrbitVisible', bool(self._axis_orbit_visible))

    def set_measurement_drag_enabled(self, enabled: bool):
        normalized = bool(enabled)
        if normalized == self._measurement_drag_enabled:
            return
        self._measurement_drag_enabled = normalized
        self._call_js('setMeasurementDragEnabled', bool(self._measurement_drag_enabled))

    def get_distance_measured_value(self, index: int, callback):
        if not self._page_ready:
            callback(None)
            return
        self._web.page().runJavaScript(
            f"window.getDistanceMeasuredValue && window.getDistanceMeasuredValue({json.dumps(int(index))});",
            callback,
        )

    def get_measurement_resolved_value(self, index: int, callback):
        if not self._page_ready:
            callback(None)
            return
        self._web.page().runJavaScript(
            f"window.getMeasurementResolvedValue && window.getMeasurementResolvedValue({json.dumps(int(index))});",
            callback,
        )

    def get_measurements_snapshot(self, callback):
        if not self._page_ready:
            callback(None)
            return
        self._web.page().runJavaScript(
            "window.getMeasurementsSnapshot && window.getMeasurementsSnapshot();",
            callback,
        )

    def _on_title_changed(self, title: str):
        parsed = parse_title_event(title)
        if not parsed:
            return

        event_name, payload = parsed

        if event_name == 'TRANSFORM':
            if (
                isinstance(payload, dict)
                and isinstance(payload.get('index'), int)
                and isinstance(payload.get('transform'), dict)
                and payload['index'] >= 0
            ):
                index = payload['index']
                transform = payload['transform']
                while len(self._part_transforms_cache) <= index:
                    self._part_transforms_cache.append({'x': 0, 'y': 0, 'z': 0, 'rx': 0, 'ry': 0, 'rz': 0})
                self._part_transforms_cache[index] = transform
                self.transform_changed.emit(index, transform)
            return

        if event_name == 'TRANSFORM_BATCH':
            if not isinstance(payload, list):
                return
            for item in payload:
                if not isinstance(item, dict):
                    continue
                index = item.get('index')
                transform = item.get('transform')
                if not isinstance(index, int) or index < 0 or not isinstance(transform, dict):
                    continue
                while len(self._part_transforms_cache) <= index:
                    self._part_transforms_cache.append({'x': 0, 'y': 0, 'z': 0, 'rx': 0, 'ry': 0, 'rz': 0})
                self._part_transforms_cache[index] = transform
                self.transform_changed.emit(index, transform)
            return

        if event_name == 'PART_SELECTED':
            self._selected_part_index = int(payload)
            self.part_selected.emit(self._selected_part_index)
            return

        if event_name == 'PART_SELECTIONS':
            normalized = normalize_index_list(payload)
            self._selected_part_indices = normalized
            self._selected_part_index = normalized[-1] if normalized else -1
            self.part_selected.emit(self._selected_part_index)
            self.part_selection_changed.emit(normalized)
            return

        if event_name == 'POINT_PICKED' and isinstance(payload, dict):
            self.point_picked.emit(payload)
            return

        if event_name == 'MEASUREMENT_UPDATED' and isinstance(payload, dict):
            self.measurement_updated.emit(payload)

    def set_transform_edit_enabled(self, enabled: bool):
        self._transform_edit_enabled = bool(enabled)
        self._call_js('setTransformEditEnabled', bool(self._transform_edit_enabled))

    def set_transform_mode(self, mode: str):
        if mode not in ('translate', 'rotate'):
            return
        self._transform_mode = mode
        self._call_js('setTransformMode', mode)

    def set_fine_transform_enabled(self, enabled: bool):
        self._fine_transform_enabled = bool(enabled)
        self._call_js('setFineTransformEnabled', bool(self._fine_transform_enabled))

    def get_part_transforms(self, callback):
        if self._page_ready:
            self._web.page().runJavaScript(
                "window.getPartTransforms && window.getPartTransforms();",
                callback,
            )

    def set_part_transforms(self, transforms: list[dict]):
        self._part_transforms_cache = [
            {
                'x': transform.get('x', 0),
                'y': transform.get('y', 0),
                'z': transform.get('z', 0),
                'rx': transform.get('rx', 0),
                'ry': transform.get('ry', 0),
                'rz': transform.get('rz', 0),
            }
            for transform in (transforms or [])
            if isinstance(transform, dict)
        ]
        self._call_js('setPartTransforms', self._part_transforms_cache)

    def select_part(self, index: int):
        self._selected_part_index = int(index)
        self._selected_part_indices = [self._selected_part_index] if self._selected_part_index >= 0 else []
        self._call_js('selectPart', int(index))

    def select_parts(self, indices: list[int]):
        normalized = [int(idx) for idx in (indices or []) if int(idx) >= 0]
        self._selected_part_indices = normalized
        self._selected_part_index = normalized[-1] if normalized else -1
        self._call_js('selectParts', normalized)

    def reset_selected_part_transform(self):
        for index in self._selected_part_indices or ([self._selected_part_index] if self._selected_part_index >= 0 else []):
            if 0 <= index < len(self._part_transforms_cache):
                self._part_transforms_cache[index] = {'x': 0, 'y': 0, 'z': 0, 'rx': 0, 'ry': 0, 'rz': 0}
        self._call_js('resetSelectedPartTransform')

    def set_measurement_overlays(self, overlays):
        normalized = []
        for idx, overlay in enumerate(overlays or []):
            item = self._normalize_measurement_overlay(overlay, idx)
            if item is not None:
                normalized.append(item)
        if normalized == self._measurement_overlays:
            return
        self._measurement_overlays = normalized
        self._call_js('setMeasurements', self._measurement_overlays)

    def set_measurements_visible(self, visible: bool):
        normalized = bool(visible)
        if normalized == self._measurements_visible:
            return
        self._measurements_visible = normalized
        self._call_js('setMeasurementsVisible', bool(self._measurements_visible))

    def set_measurement_filter(self, name: str | None):
        value = str(name or '').strip()
        normalized = value or None
        if normalized == self._measurement_filter:
            return
        self._measurement_filter = normalized
        self._call_js('setMeasurementFilter', value)

    def set_measurement_focus_index(self, index: int | None):
        value = int(index) if isinstance(index, int) else -1
        self._call_js('setMeasurementFocusIndex', value)

    def set_axis_orbit_visible(self, visible: bool):
        normalized = bool(visible)
        if normalized == self._axis_orbit_visible:
            return
        self._axis_orbit_visible = normalized
        self._apply_axis_orbit_state()

    def set_control_hint_text(self, text: str | None):
        self._control_hint_text = str(text or '').strip()
        self._apply_hint_text()

    def set_selection_caption(self, text: str | None):
        normalized = str(text or '').strip()
        self._selection_caption = normalized
        if not normalized:
            self._selection_caption_label.clear()
            self._selection_caption_wrap.hide()
            return
        self._selection_caption_label.setText(normalized)
        self._selection_caption_wrap.show()
        self._selection_caption_wrap.raise_()

    def set_point_picking_enabled(self, enabled: bool):
        self._point_picking_enabled = bool(enabled)
        self._call_js('setPointPickingEnabled', bool(self._point_picking_enabled))



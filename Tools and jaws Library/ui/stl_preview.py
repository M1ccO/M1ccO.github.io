import json
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QAbstractScrollArea, QLabel, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from config import (
    JAW_MODELS_ROOT_DEFAULT,
    PREVIEW_DIR,
    SHARED_UI_PREFERENCES_PATH,
    TOOL_MODELS_ROOT_DEFAULT,
)
from shared.model_paths import read_model_roots, resolve_model_path


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


class StlPreviewWidget(QWidget):
    transform_changed = Signal(int, dict)
    part_selected = Signal(int)

    def __init__(self, stl_path: str | None = None, parent=None):
        super().__init__(parent)

        self._viewer_html = PREVIEW_DIR / "index.html"

        self._page_ready = False
        self._pending_stl_path = None
        self._pending_label = None
        self._pending_parts = None
        self._alignment_plane = 'XZ'
        self._rotation_deg = {'x': 0, 'y': 0, 'z': 0}

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.hide()

        self._web = ScrollFriendlyWebView()
        self._layout.addWidget(self._web)
        self._layout.addWidget(self._error_label)

        if not self._viewer_html.exists():
            self._show_error(f"Viewer HTML not found:\n{self._viewer_html}")
            return

        self._web.loadFinished.connect(self._on_load_finished)
        self._web.page().titleChanged.connect(self._on_title_changed)
        self._web.load(QUrl.fromLocalFile(str(self._viewer_html)))

        if stl_path:
            self.load_stl(stl_path)

    def _show_error(self, message: str):
        self._web.hide()
        self._error_label.setText(message)
        self._error_label.show()

    def _show_web(self):
        self._error_label.hide()
        self._web.show()

    def _on_load_finished(self, ok: bool):
        self._page_ready = ok

        if not ok:
            self._show_error("Failed to load viewer HTML.")
            return

        self._show_web()

        if self._pending_parts:
            self._send_parts_to_viewer(self._pending_parts)
        elif self._pending_stl_path:
            self._send_model_to_viewer(self._pending_stl_path, self._pending_label)

        self._apply_preview_transform_state()

    def _send_model_to_viewer(self, stl_path: Path, label: str | None = None):
        stl_url = QUrl.fromLocalFile(str(stl_path)).toString()

        if label:
            js = f"window.loadModel && window.loadModel({stl_url!r}, {label!r});"
        else:
            js = f"window.loadModel && window.loadModel({stl_url!r});"

        self._web.page().runJavaScript(js)

    def _send_parts_to_viewer(self, parts: list[dict]):
        tools_root, jaws_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )
        payload = []
        for part in parts:
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

        js_payload = json.dumps(payload)
        js = f"window.loadAssembly && window.loadAssembly({js_payload});"
        self._web.page().runJavaScript(js)

    def clear(self):
        self._pending_stl_path = None
        self._pending_label = None
        self._pending_parts = None
        self._web.reset_wheel_mode()

        if self._page_ready:
            self._web.page().runJavaScript("window.clearModel && window.clearModel();")

    def load_stl(self, stl_path: str | Path | None, label: str | None = None):
        self._pending_parts = None
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

        if not parts:
            self.clear()
            return

        self._pending_parts = parts
        self._show_web()

        if self._page_ready:
            self._send_parts_to_viewer(parts)
            self._apply_preview_transform_state()

    def _apply_preview_transform_state(self):
        if not self._page_ready:
            return
        self._web.page().runJavaScript(
            f"window.setAlignmentPlane && window.setAlignmentPlane({self._alignment_plane!r});"
        )
        self._web.page().runJavaScript("window.resetModelRotation && window.resetModelRotation();")
        for axis, deg in self._rotation_deg.items():
            if deg:
                self._web.page().runJavaScript(
                    f"window.rotateModel && window.rotateModel({axis!r}, {float(deg)});"
                )

    def set_alignment_plane(self, plane: str):
        normalized = (plane or 'XZ').strip().upper()
        if normalized not in {'XZ', 'XY', 'YZ'}:
            normalized = 'XZ'
        self._alignment_plane = normalized
        if self._page_ready:
            self._web.page().runJavaScript(
                f"window.setAlignmentPlane && window.setAlignmentPlane({self._alignment_plane!r});"
            )

    def rotate_model(self, axis: str, degrees: float = 90.0):
        key = (axis or '').strip().lower()
        if key not in {'x', 'y', 'z'}:
            return
        self._rotation_deg[key] += float(degrees)
        if self._page_ready:
            self._web.page().runJavaScript(
                f"window.rotateModel && window.rotateModel({key!r}, {float(degrees)});"
            )

    def reset_model_rotation(self):
        self._rotation_deg = {'x': 0, 'y': 0, 'z': 0}
        if self._page_ready:
            self._web.page().runJavaScript("window.resetModelRotation && window.resetModelRotation();")

    def _on_title_changed(self, title: str):
        if title.startswith('TRANSFORM:'):
            try:
                data = json.loads(title[len('TRANSFORM:'):])
                self.transform_changed.emit(data['index'], data['transform'])
            except (json.JSONDecodeError, KeyError):
                pass
        elif title.startswith('PART_SELECTED:'):
            try:
                idx = int(title[len('PART_SELECTED:'):])
                self.part_selected.emit(idx)
            except ValueError:
                pass

    def set_transform_edit_enabled(self, enabled: bool):
        if self._page_ready:
            self._web.page().runJavaScript(
                f"window.setTransformEditEnabled && window.setTransformEditEnabled({str(enabled).lower()});"
            )

    def set_transform_mode(self, mode: str):
        if mode in ('translate', 'rotate') and self._page_ready:
            self._web.page().runJavaScript(
                f"window.setTransformMode && window.setTransformMode({mode!r});"
            )

    def get_part_transforms(self, callback):
        if self._page_ready:
            self._web.page().runJavaScript(
                "window.getPartTransforms && window.getPartTransforms();",
                callback,
            )

    def set_part_transforms(self, transforms: list[dict]):
        if self._page_ready:
            js_payload = json.dumps(transforms)
            self._web.page().runJavaScript(
                f"window.setPartTransforms && window.setPartTransforms({js_payload});"
            )

    def select_part(self, index: int):
        if self._page_ready:
            self._web.page().runJavaScript(
                f"window.selectPart && window.selectPart({int(index)});"
            )

    def reset_selected_part_transform(self):
        if self._page_ready:
            self._web.page().runJavaScript(
                "window.resetSelectedPartTransform && window.resetSelectedPartTransform();"
            )


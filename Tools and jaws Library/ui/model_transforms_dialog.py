import copy
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from config import TOOL_ICONS_DIR
from shared.ui.helpers.editor_helpers import apply_secondary_button_theme, create_dialog_buttons, style_panel_action_button
from shared.ui.stl_preview import StlPreviewWidget


class ModelTransformsDialog(QDialog):
    """Separate window for editing assembly part transforms with 3D gizmo support."""

    def __init__(
        self,
        parts: list[dict],
        transforms: list[dict] | None = None,
        parent=None,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or "")
        self._parts = copy.deepcopy(parts or [])
        self._selected_part_index = -1
        self._selected_part_indices: list[int] = []
        self._mode = "translate"
        self._fine_transform_enabled = False

        defaults = {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0}
        self._transforms = []
        input_transforms = transforms or []
        for i in range(len(self._parts)):
            t = input_transforms[i] if i < len(input_transforms) and isinstance(input_transforms[i], dict) else {}
            merged = dict(defaults)
            merged.update({k: t.get(k, 0) for k in defaults.keys()})
            self._transforms.append(merged)

        self.setWindowTitle(self._t("tool_editor.transform.editor_title", "3D Model Editor"))
        self.resize(1180, 780)
        self.setMinimumSize(920, 620)
        self._build_ui()
        self._load_preview()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.preview = StlPreviewWidget()
        self.preview.set_control_hint_text(
            self._t(
                "tool_editor.hint.rotate_pan_zoom",
                "Rotate: left mouse â€¢ Pan: right mouse â€¢ Zoom: mouse wheel",
            )
        )
        root.addWidget(self.preview, 1)

        self.preview.set_transform_edit_enabled(True)
        self.preview.set_transform_mode("translate")
        self.preview.set_fine_transform_enabled(self._fine_transform_enabled)
        self.preview.transform_changed.connect(self._on_viewer_transform_changed)
        self.preview.part_selected.connect(self._on_viewer_part_selected)
        self.preview.part_selection_changed.connect(self._on_viewer_part_selection_changed)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.selected_label = QLabel(self._t("tool_editor.transform.no_selection", "Click a part to select. Ctrl+click for multiple"))
        self.selected_label.setStyleSheet("background: transparent;")
        controls.addWidget(self.selected_label, 1)

        self.move_btn = QPushButton(self._t("tool_editor.transform.move", "MOVE"))
        self.rotate_btn = QPushButton(self._t("tool_editor.transform.rotate", "ROTATE"))
        self.fine_btn = QPushButton(self._t("tool_editor.transform.fine", "FINE"))
        self.reset_btn = QPushButton()
        self.move_btn.setCheckable(True)
        self.rotate_btn.setCheckable(True)
        self.fine_btn.setCheckable(True)
        self.move_btn.setChecked(True)
        self.fine_btn.setChecked(self._fine_transform_enabled)
        self.move_btn.setIcon(self._icon("import_export.svg"))
        self.rotate_btn.setIcon(self._icon("arrow_circle_right.svg"))
        self.reset_btn.setIcon(self._icon("arrow_circle_left.svg"))
        self.move_btn.setIconSize(QSize(16, 16))
        self.rotate_btn.setIconSize(QSize(16, 16))
        self.reset_btn.setIconSize(QSize(16, 16))
        self.move_btn.setMinimumWidth(96)
        self.rotate_btn.setMinimumWidth(102)
        self.fine_btn.setMinimumWidth(82)
        self.reset_btn.setFixedWidth(44)
        self.fine_btn.setToolTip(self._t("tool_editor.transform.fine_tooltip", "Toggle fine transform increments"))
        self.reset_btn.setToolTip(self._t("tool_editor.transform.reset", "RESET"))
        style_panel_action_button(self.move_btn)
        style_panel_action_button(self.rotate_btn)
        style_panel_action_button(self.fine_btn)
        style_panel_action_button(self.reset_btn)
        self.move_btn.clicked.connect(lambda: self._set_mode("translate"))
        self.rotate_btn.clicked.connect(lambda: self._set_mode("rotate"))
        self.fine_btn.toggled.connect(self._set_fine_transform_enabled)
        self.reset_btn.clicked.connect(self._reset_current_part_transform)
        controls.addWidget(self.move_btn)
        controls.addWidget(self.rotate_btn)
        controls.addWidget(self.fine_btn)
        controls.addWidget(self.reset_btn)

        self.x_edit = QLineEdit("0")
        self.y_edit = QLineEdit("0")
        self.z_edit = QLineEdit("0")
        for widget in (self.x_edit, self.y_edit, self.z_edit):
            widget.setFixedWidth(96)
            widget.setAlignment(Qt.AlignRight)
            widget.editingFinished.connect(self._apply_manual_transform)

        x_label = QLabel("X")
        x_label.setStyleSheet("background: transparent;")
        x_label.setMinimumWidth(14)
        controls.addWidget(x_label)
        controls.addWidget(self.x_edit)
        y_label = QLabel("Y")
        y_label.setStyleSheet("background: transparent;")
        y_label.setMinimumWidth(14)
        controls.addWidget(y_label)
        controls.addWidget(self.y_edit)
        z_label = QLabel("Z")
        z_label.setStyleSheet("background: transparent;")
        z_label.setMinimumWidth(14)
        controls.addWidget(z_label)
        controls.addWidget(self.z_edit)

        root.addLayout(controls)

        buttons = create_dialog_buttons(
            self,
            save_text=self._t("common.save", "TALLENNA"),
            cancel_text=self._t("common.cancel", "PERUUTA"),
            on_save=self.accept,
            on_cancel=self.reject,
        )
        apply_btn = buttons.button(QDialogButtonBox.Save)
        if apply_btn is not None:
            apply_secondary_button_theme(self, apply_btn)
        root.addWidget(buttons)

    def _icon(self, filename: str) -> QIcon:
        path = TOOL_ICONS_DIR / filename
        return QIcon(str(path)) if path.exists() else QIcon()

    def _load_preview(self):
        if not self._parts:
            return
        parts = copy.deepcopy(self._parts)
        for i, part in enumerate(parts):
            t = self._transforms[i] if i < len(self._transforms) else {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0}
            part["offset_x"] = t.get("x", 0)
            part["offset_y"] = t.get("y", 0)
            part["offset_z"] = t.get("z", 0)
            part["rot_x"] = t.get("rx", 0)
            part["rot_y"] = t.get("ry", 0)
            part["rot_z"] = t.get("rz", 0)
        self.preview.load_parts(parts)
        self.preview.set_part_transforms(self._transforms)

    def _on_viewer_part_selected(self, index: int):
        self._selected_part_indices = [index] if 0 <= index < len(self._parts) else []
        self._selected_part_index = index
        if index < 0 or index >= len(self._parts):
            self._refresh_selection_state()
            return

        self._refresh_selection_state()

    def _on_viewer_part_selection_changed(self, indices: list[int]):
        normalized = [idx for idx in indices if 0 <= idx < len(self._parts)]
        self._selected_part_indices = normalized
        self._selected_part_index = normalized[-1] if normalized else -1
        self._refresh_selection_state()

    def _on_viewer_transform_changed(self, index: int, transform: dict):
        if index < 0 or index >= len(self._transforms):
            return
        normalized = {
            "x": transform.get("x", 0),
            "y": transform.get("y", 0),
            "z": transform.get("z", 0),
            "rx": transform.get("rx", 0),
            "ry": transform.get("ry", 0),
            "rz": transform.get("rz", 0),
        }
        self._transforms[index] = normalized
        if index in self._selected_part_indices:
            self._refresh_selection_state()

    def _set_mode(self, mode: str):
        self._mode = mode
        self.move_btn.setChecked(mode == "translate")
        self.rotate_btn.setChecked(mode == "rotate")
        self.preview.set_transform_mode(mode)
        self._refresh_selection_state()

    def _set_fine_transform_enabled(self, enabled: bool):
        self._fine_transform_enabled = bool(enabled)
        if hasattr(self, 'fine_btn') and self.fine_btn.isChecked() != self._fine_transform_enabled:
            self.fine_btn.setChecked(self._fine_transform_enabled)
        self.preview.set_fine_transform_enabled(self._fine_transform_enabled)

    def _refresh_selection_state(self):
        count = len(self._selected_part_indices)
        fields_enabled = count == 1
        for widget in (self.x_edit, self.y_edit, self.z_edit):
            widget.setEnabled(fields_enabled)

        if count == 0:
            self.selected_label.setText(self._t("tool_editor.transform.no_selection", "Click a part to select. Ctrl+click for multiple"))
            self.x_edit.setText("0")
            self.y_edit.setText("0")
            self.z_edit.setText("0")
            self.reset_btn.setEnabled(False)
            return

        self.reset_btn.setEnabled(True)
        if count == 1 and 0 <= self._selected_part_index < len(self._parts):
            part_name = str(self._parts[self._selected_part_index].get("name") or f"Part {self._selected_part_index + 1}")
            self.selected_label.setText(part_name)
            self._update_fields(self._transforms[self._selected_part_index])
            return

        multi_text = self._t("tool_editor.transform.multi_selection", "{count} models selected", count=count)
        self.selected_label.setText(multi_text.format(count=count) if '{count}' in multi_text else multi_text)
        self.x_edit.clear()
        self.y_edit.clear()
        self.z_edit.clear()

    def _update_fields(self, transform: dict):
        if self._mode == "translate":
            self.x_edit.setText(str(transform.get("x", 0)))
            self.y_edit.setText(str(transform.get("y", 0)))
            self.z_edit.setText(str(transform.get("z", 0)))
        else:
            self.x_edit.setText(str(transform.get("rx", 0)))
            self.y_edit.setText(str(transform.get("ry", 0)))
            self.z_edit.setText(str(transform.get("rz", 0)))

    def _apply_manual_transform(self):
        if len(self._selected_part_indices) != 1:
            return
        if self._selected_part_index < 0 or self._selected_part_index >= len(self._transforms):
            return
        try:
            vx = float(self.x_edit.text().replace(",", "."))
            vy = float(self.y_edit.text().replace(",", "."))
            vz = float(self.z_edit.text().replace(",", "."))
        except ValueError:
            return

        t = dict(self._transforms[self._selected_part_index])
        if self._mode == "translate":
            t["x"] = vx
            t["y"] = vy
            t["z"] = vz
        else:
            t["rx"] = vx
            t["ry"] = vy
            t["rz"] = vz
        self._transforms[self._selected_part_index] = t
        self.preview.set_part_transforms(self._transforms)

    def _reset_current_part_transform(self):
        if not self._selected_part_indices:
            return
        for index in self._selected_part_indices:
            self._transforms[index] = {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0}
        self.preview.set_part_transforms(self._transforms)
        self.preview.reset_selected_part_transform()
        self._refresh_selection_state()

    def get_transforms(self) -> list[dict]:
        return copy.deepcopy(self._transforms)


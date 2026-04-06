import copy
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from shared.editor_helpers import apply_secondary_button_theme, create_dialog_buttons, style_panel_action_button
from ui.stl_preview import StlPreviewWidget


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
        self._mode = "translate"

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
        root.addWidget(self.preview, 1)

        self.preview.set_transform_edit_enabled(True)
        self.preview.set_transform_mode("translate")
        self.preview.transform_changed.connect(self._on_viewer_transform_changed)
        self.preview.part_selected.connect(self._on_viewer_part_selected)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.selected_label = QLabel(self._t("tool_editor.transform.no_selection", "Click a part to select"))
        self.selected_label.setStyleSheet("background: transparent;")
        controls.addWidget(self.selected_label, 1)

        self.move_btn = QPushButton(self._t("tool_editor.transform.move", "MOVE"))
        self.rotate_btn = QPushButton(self._t("tool_editor.transform.rotate", "ROTATE"))
        self.reset_btn = QPushButton(self._t("tool_editor.transform.reset", "RESET"))
        self.move_btn.setCheckable(True)
        self.rotate_btn.setCheckable(True)
        self.move_btn.setChecked(True)
        style_panel_action_button(self.move_btn)
        style_panel_action_button(self.rotate_btn)
        style_panel_action_button(self.reset_btn)
        self.move_btn.clicked.connect(lambda: self._set_mode("translate"))
        self.rotate_btn.clicked.connect(lambda: self._set_mode("rotate"))
        self.reset_btn.clicked.connect(self._reset_current_part_transform)
        controls.addWidget(self.move_btn)
        controls.addWidget(self.rotate_btn)
        controls.addWidget(self.reset_btn)

        self.x_edit = QLineEdit("0")
        self.y_edit = QLineEdit("0")
        self.z_edit = QLineEdit("0")
        for widget in (self.x_edit, self.y_edit, self.z_edit):
            widget.setFixedWidth(84)
            widget.setAlignment(Qt.AlignRight)
            widget.editingFinished.connect(self._apply_manual_transform)

        x_label = QLabel("X:")
        x_label.setStyleSheet("background: transparent;")
        controls.addWidget(x_label)
        controls.addWidget(self.x_edit)
        y_label = QLabel("Y:")
        y_label.setStyleSheet("background: transparent;")
        controls.addWidget(y_label)
        controls.addWidget(self.y_edit)
        z_label = QLabel("Z:")
        z_label.setStyleSheet("background: transparent;")
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
        self._selected_part_index = index
        if index < 0 or index >= len(self._parts):
            self.selected_label.setText(self._t("tool_editor.transform.no_selection", "Click a part to select"))
            self.x_edit.setText("0")
            self.y_edit.setText("0")
            self.z_edit.setText("0")
            return

        part_name = str(self._parts[index].get("name") or f"Part {index + 1}")
        self.selected_label.setText(part_name)
        self._update_fields(self._transforms[index])

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
        if index == self._selected_part_index:
            self._update_fields(normalized)

    def _set_mode(self, mode: str):
        self._mode = mode
        self.move_btn.setChecked(mode == "translate")
        self.rotate_btn.setChecked(mode == "rotate")
        self.preview.set_transform_mode(mode)
        if 0 <= self._selected_part_index < len(self._transforms):
            self._update_fields(self._transforms[self._selected_part_index])

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
        if self._selected_part_index < 0 or self._selected_part_index >= len(self._transforms):
            return
        self._transforms[self._selected_part_index] = {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0}
        self.preview.set_part_transforms(self._transforms)
        self._update_fields(self._transforms[self._selected_part_index])

    def get_transforms(self) -> list[dict]:
        return copy.deepcopy(self._transforms)

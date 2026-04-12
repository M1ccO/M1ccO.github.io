"""Preview panel builder for HomePage detail cards."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from shared.ui.helpers.editor_helpers import create_titled_section


def build_preview_panel(
    *,
    page,
    stl_path: str | None,
    stl_preview_widget_cls,
    load_preview_content,
):
    frame = create_titled_section(page._t("tool_library.section.preview", "Preview"))
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    layout = QVBoxLayout(frame)
    layout.setSpacing(10)
    layout.setContentsMargins(6, 4, 6, 6)

    diagram = QWidget()
    diagram.setObjectName("detailPreviewGradientHost")
    diagram.setAttribute(Qt.WA_StyledBackground, True)
    diagram.setStyleSheet(
        "QWidget#detailPreviewGradientHost {"
        "  background-color: #d6d9de;"
        "  border: none;"
        "  border-radius: 6px;"
        "}"
    )
    diagram.setMinimumHeight(300)
    diagram.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    dlay = QVBoxLayout(diagram)
    dlay.setContentsMargins(6, 6, 6, 6)
    dlay.setSpacing(0)

    viewer = stl_preview_widget_cls() if stl_preview_widget_cls is not None else None
    if viewer is not None:
        viewer.setStyleSheet("background: transparent; border: none;")
        viewer.set_control_hint_text(
            page._t(
                "tool_editor.hint.rotate_pan_zoom",
                "Rotate: left mouse â€¢ Pan: right mouse â€¢ Zoom: mouse wheel",
            )
        )
    loaded = load_preview_content(viewer, stl_path, label="Detail Preview") if viewer is not None else False
    if viewer is not None:
        viewer.setMinimumHeight(260)
        viewer.set_measurement_overlays([])
        viewer.set_measurements_visible(False)

    if loaded:
        dlay.addWidget(viewer, 1)
        viewer.show()
    else:
        txt = QLabel(
            page._t("tool_library.preview.invalid_data", "No valid 3D model data found.")
            if stl_path
            else page._t("tool_library.preview.none_assigned", "No 3D model assigned.")
        )
        txt.setWordWrap(True)
        txt.setAlignment(Qt.AlignCenter)
        dlay.addStretch(1)
        dlay.addWidget(txt)
        dlay.addStretch(1)

    layout.addWidget(diagram, 1)
    return frame


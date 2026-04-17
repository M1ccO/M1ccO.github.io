from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt


def _activate_tool_library_namespace_aliases(dialog: Any) -> None:
    existing = getattr(dialog, "_embedded_selector_namespace_aliases", None)
    if isinstance(existing, dict):
        return

    aliases = {
        "config": "tools_and_jaws_library.config",
        "ui": "tools_and_jaws_library.ui",
        "data": "tools_and_jaws_library.data",
        "services": "tools_and_jaws_library.services",
        "models": "tools_and_jaws_library.models",
    }
    snapshot: dict[str, Any] = {}
    for alias, target in aliases.items():
        snapshot[alias] = sys.modules.get(alias)
        try:
            sys.modules[alias] = importlib.import_module(target)
        except Exception:
            # Keep best-effort behavior; unresolved aliases will surface via normal import errors.
            pass
    setattr(dialog, "_embedded_selector_namespace_aliases", snapshot)


def release_tool_library_namespace_aliases(dialog: Any) -> None:
    snapshot = getattr(dialog, "_embedded_selector_namespace_aliases", None)
    if not isinstance(snapshot, dict):
        return
    for alias, original in snapshot.items():
        if original is None:
            sys.modules.pop(alias, None)
        else:
            sys.modules[alias] = original
    setattr(dialog, "_embedded_selector_namespace_aliases", None)


def warmup_embedded_selector_runtime(dialog: Any) -> None:
    """Preload selector import aliases and service bundle for first-open smoothness."""
    _activate_tool_library_namespace_aliases(dialog)
    _ensure_service_bundle(dialog)


def _ensure_service_bundle(dialog: Any) -> dict[str, Any]:
    bundle = getattr(dialog, "_embedded_selector_service_bundle", None)
    if isinstance(bundle, dict):
        return bundle

    from tools_and_jaws_library.data.database import Database
    from tools_and_jaws_library.data.fixture_database import FixtureDatabase
    from tools_and_jaws_library.data.jaw_database import JawDatabase
    from tools_and_jaws_library.services.fixture_service import FixtureService
    from tools_and_jaws_library.services.jaw_service import JawService
    from tools_and_jaws_library.services.tool_service import ToolService

    draw_service = dialog.draw_service
    tool_db = Database(Path(draw_service.tool_db_path))
    jaw_db = JawDatabase(Path(draw_service.jaw_db_path))
    fixture_db = FixtureDatabase(Path(getattr(draw_service, "fixture_db_path", draw_service.jaw_db_path)))

    bundle = {
        "tool_service": ToolService(tool_db),
        "jaw_service": JawService(jaw_db),
        "fixture_service": FixtureService(fixture_db),
        "tool_db": tool_db,
        "jaw_db": jaw_db,
        "fixture_db": fixture_db,
    }
    setattr(dialog, "_embedded_selector_service_bundle", bundle)
    return bundle


def _apply_embedded_selector_style(widget: Any) -> None:
    """Apply selector-local style overrides for embedded hosting in Work Editor.

    Setup Manager and Tool Library use different global stylesheets. These
    targeted rules restore selector visual parity without touching app-wide QSS.
    """
    if widget is None:
        return

    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setProperty("selectorContext", True)
    widget.setStyleSheet(
        """
QFrame[selectorContext="true"] {
    background-color: #ffffff;
    border: none;
    border-radius: 2px;
}

QWidget[selectorPanel="true"] {
    background-color: #ffffff;
    border: none;
}
QWidget[selectorContext="true"] QFrame[selectorAssignmentsFrame="true"],
QWidget[selectorContext="true"] QFrame[toolIdsPanel="true"] {
    background-color: #f0f6fc;
    border: 1px solid #d0d8e0;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
}
QWidget[selectorContext="true"] QFrame[selectorScrollFrame="true"] {
    background-color: #f0f6fc;
    border: 1px solid #d0d8e0;
    border-radius: 6px;
}
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"] {
    background-color: #ffffff;
    border: 1px solid #99acbf;
    border-radius: 8px;
    min-height: 34px;
    padding: 1px;
}
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][hasComment="true"] {
    min-height: 42px;
}
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"]:hover {
    background-color: #ffffff;
}
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][selected="true"],
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][selected="true"]:hover {
    background-color: #ffffff;
    border: 2px solid #00C8FF;
    padding: 0px;
}
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"] QLabel {
    background-color: transparent;
}
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][selected="true"] QLabel {
    color: #24303c;
}

QWidget[selectorContext="true"] QFrame[selectorInfoHeader="true"] {
    background-color: #ffffff;
    border: 1px solid #c8d4e0;
    border-radius: 6px;
}

QWidget[selectorContext="true"] QLabel[selectorInfoTitle="true"] {
    font-size: 11.5pt;
    font-weight: 700;
    color: #13202b;
    background: transparent;
}

QWidget[selectorContext="true"] QLabel[miniAssignmentTitle="true"] {
    font-size: 10.8pt;
    font-weight: 600;
    color: #171a1d;
}
QWidget[selectorContext="true"] QLabel[miniAssignmentMeta="true"] {
    font-size: 8.4pt;
    font-weight: 600;
    color: #2b3136;
}
QWidget[selectorContext="true"] QLabel[miniAssignmentHint="true"] {
    font-size: 8.4pt;
    font-weight: 500;
    color: #617180;
}

QWidget[selectorContext="true"] QLabel[selectorInlineHint="true"] {
    font-size: 8pt;
    font-style: italic;
    font-weight: 400;
    color: #5f6f7d;
    padding-top: 2px;
}

QWidget[selectorContext="true"] QListWidget#toolIdsOrderList {
    background: transparent;
    border: none;
    border-radius: 0px;
    outline: none;
    padding: 0px;
}
QWidget[selectorContext="true"] QListWidget#toolIdsOrderList::item {
    background-color: transparent;
    border: none;
    border-radius: 0px;
    padding: 0px;
    margin: 0px;
}
QWidget[selectorContext="true"] QListWidget#toolIdsOrderList::item:hover {
    background-color: transparent;
    border: none;
}

QWidget[selectorContext="true"] QListWidget#toolIdsOrderList::item:selected,
QWidget[selectorContext="true"] QListWidget#toolIdsOrderList::item:selected:active,
QWidget[selectorContext="true"] QListWidget#toolIdsOrderList::item:selected:!active {
    background-color: transparent;
    border: none;
    color: inherit;
}
QWidget[selectorContext="true"] QListWidget#toolIdsOrderList::viewport {
    background: transparent;
    border: none;
    border-radius: 0px;
}
QWidget[selectorContext="true"] QFrame[selectorAssignmentsFrame="true"][catalogDragOver="true"],
QWidget[selectorContext="true"] QFrame[toolIdsPanel="true"][catalogDragOver="true"] {
    border: 1px solid #00c8ff;
}
QWidget[selectorContext="true"] QGroupBox[selectorAssignmentsFrame="true"][catalogDragOver="true"],
QWidget[selectorContext="true"] QGroupBox[toolIdsPanel="true"][catalogDragOver="true"] {
    background-color: #f0f6fc;
    border: 1px solid #00c8ff;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
}
QWidget[selectorContext="true"] QGroupBox[selectorAssignmentsFrame="true"][catalogDragOver="true"]::title,
QWidget[selectorContext="true"] QGroupBox[toolIdsPanel="true"][catalogDragOver="true"]::title {
    color: #0f5f8e;
}
QWidget[selectorContext="true"] QGroupBox[selectorAssignmentsFrame="true"][catalogDragOver="true"] QLabel[selectorInlineHint="true"],
QWidget[selectorContext="true"] QGroupBox[toolIdsPanel="true"][catalogDragOver="true"] QLabel[selectorInlineHint="true"] {
    color: #3c7294;
}
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][catalogDragOver="true"] {
    background-color: rgba(255, 255, 255, 0.28);
    border: 1px solid #b8c7d6;
}
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][catalogDragOver="true"] QLabel[miniAssignmentTitle="true"],
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][catalogDragOver="true"] QLabel[miniAssignmentHint="true"],
QWidget[selectorContext="true"] QFrame[miniAssignmentCard="true"][catalogDragOver="true"] QLabel[miniAssignmentMeta="true"] {
    color: #738391;
}
"""
    )
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


def build_embedded_selector_parity_widget(
    dialog: Any,
    *,
    mount_container: QWidget | None = None,
    kind: str,
    head: str | None = None,
    spindle: str | None = None,
    follow_up: dict | None = None,
    initial_assignments: list[dict] | None = None,
    initial_assignment_buckets: dict[str, list[dict]] | None = None,
    on_submit: Callable[[dict], None],
    on_cancel: Callable[[], None],
):
    kind_key = str(kind or "").strip().lower()
    _activate_tool_library_namespace_aliases(dialog)
    services = _ensure_service_bundle(dialog)

    if kind_key == "tools":
        from tools_and_jaws_library.ui.selectors.tool_selector_dialog import ToolSelectorDialog

        widget = ToolSelectorDialog(
            tool_service=services["tool_service"],
            machine_profile=dialog.machine_profile,
            translate=dialog._t,
            selector_head=str(head or ""),
            selector_spindle=str(spindle or ""),
            initial_assignments=initial_assignments,
            initial_assignment_buckets=initial_assignment_buckets,
            on_submit=on_submit,
            on_cancel=on_cancel,
            parent=None,
            embedded_mode=True,
        )
        if not hasattr(widget, "_refresh_elided_group_title"):
            setattr(widget, "_refresh_elided_group_title", lambda *_args, **_kwargs: None)
    elif kind_key == "jaws":
        from tools_and_jaws_library.ui.selectors.jaw_selector_dialog import JawSelectorDialog

        widget = JawSelectorDialog(
            jaw_service=services["jaw_service"],
            machine_profile=dialog.machine_profile,
            translate=dialog._t,
            selector_spindle=str(spindle or ""),
            initial_assignments=initial_assignments,
            on_submit=on_submit,
            on_cancel=on_cancel,
            parent=None,
            embedded_mode=True,
        )
    else:
        from tools_and_jaws_library.ui.selectors.fixture_selector_dialog import FixtureSelectorDialog

        widget = FixtureSelectorDialog(
            fixture_service=services["fixture_service"],
            translate=dialog._t,
            initial_assignments=initial_assignments,
            initial_assignment_buckets=initial_assignment_buckets,
            initial_target_key=str((follow_up or {}).get("target_key") or ""),
            on_submit=on_submit,
            on_cancel=on_cancel,
            parent=None,
            embedded_mode=True,
        )

    # Force child-widget hosting to avoid transient top-level QDialog flashes.
    # Use a single setWindowFlags call — individual setWindowFlag calls each
    # trigger a re-parent cycle that can briefly flash a top-level window.
    parent_widget = mount_container or dialog
    widget.setWindowFlags(Qt.Widget)
    widget.setParent(parent_widget)
    widget.setWindowModality(Qt.NonModal)
    widget.setAttribute(Qt.WA_DontShowOnScreen, True)
    widget.setVisible(False)
    widget.setAttribute(Qt.WA_DontShowOnScreen, False)
    _apply_embedded_selector_style(widget)
    return widget

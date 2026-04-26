from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from shared.ui.helpers.common_widgets import apply_shared_dropdown_style


_LOGGER = logging.getLogger(__name__)


def _selector_diagnostic_kind() -> str:
    return str(os.environ.get("NTX_WORK_EDITOR_SELECTOR_DIAGNOSTIC_KIND", "")).strip().lower()


def _build_trivial_diagnostic_selector_widget(
    *,
    kind: str,
    parent: QWidget | None,
    on_submit: Callable[[dict], None],
    on_cancel: Callable[[], None],
) -> QWidget:
    widget = QFrame(parent)
    widget.setObjectName("workEditorDiagnosticSelector")
    widget.setProperty("selectorContext", True)
    widget.setProperty("diagnosticSelector", True)

    root = QVBoxLayout(widget)
    root.setContentsMargins(24, 24, 24, 24)
    root.setSpacing(16)

    title = QLabel(f"Diagnostic selector placeholder ({kind})", widget)
    title.setProperty("selectorInfoTitle", True)
    title.setWordWrap(True)
    root.addWidget(title)

    body = QLabel(
        "This widget intentionally bypasses the real selector subtree so the "
        "Work Editor host transition can be compared against trivial content.",
        widget,
    )
    body.setWordWrap(True)
    body.setProperty("selectorInlineHint", True)
    root.addWidget(body)

    fill = QFrame(widget)
    fill.setProperty("selectorAssignmentsFrame", True)
    fill_layout = QVBoxLayout(fill)
    fill_layout.setContentsMargins(18, 18, 18, 18)
    fill_layout.setSpacing(10)
    fill_label = QLabel(
        "If the visible glitch still appears with this placeholder, the "
        "remaining culprit is likely above selector internals.",
        fill,
    )
    fill_label.setWordWrap(True)
    fill_layout.addWidget(fill_label)
    root.addWidget(fill, 1)

    buttons_row = QHBoxLayout()
    buttons_row.addStretch(1)

    cancel_button = QPushButton("Cancel", widget)
    cancel_button.clicked.connect(on_cancel)
    buttons_row.addWidget(cancel_button)

    submit_button = QPushButton("Submit placeholder", widget)
    submit_button.clicked.connect(lambda: on_submit({"kind": kind, "selected_items": []}))
    buttons_row.addWidget(submit_button)
    root.addLayout(buttons_row)
    return widget


def _selector_widget_cache(dialog: Any) -> dict[str, QWidget]:
    cache = getattr(dialog, "_embedded_selector_widget_cache", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    setattr(dialog, "_embedded_selector_widget_cache", cache)
    return cache


def _selector_widget_snapshot(widget: Any) -> dict[str, Any]:
    if not isinstance(widget, QWidget):
        return {"widget_type": type(widget).__name__ if widget is not None else "None"}
    parent = widget.parentWidget()
    return {
        "widget_type": type(widget).__name__,
        "parent_type": type(parent).__name__ if parent is not None else None,
        "is_window": bool(widget.isWindow()),
        "window_type": int(widget.windowType()),
        "window_flags": int(widget.windowFlags()),
        "visible": bool(widget.isVisible()),
        "dont_show_on_screen": bool(widget.testAttribute(Qt.WA_DontShowOnScreen)),
    }


def _trace_selector_event(dialog: Any, event: str, **fields: Any) -> None:
    payload = {"event": event}
    payload.update(fields)
    if hasattr(dialog, "_log_selector_event"):
        dialog._log_selector_event(event, **fields)
        return
    _LOGGER.info("embedded.selector %s", payload)


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


def dispose_embedded_selector_runtime(dialog: Any) -> None:
    """Dispose cached embedded selector widgets, preview windows, and DB handles."""
    cache = getattr(dialog, "_embedded_selector_widget_cache", None)
    if isinstance(cache, dict):
        for widget in list(cache.values()):
            if widget is None:
                continue
            try:
                preview_dialog = getattr(widget, "_detached_preview_dialog", None)
                if preview_dialog is not None:
                    preview_dialog.close()
            except Exception:
                _LOGGER.debug("Failed closing embedded selector preview dialog", exc_info=True)
            try:
                warmup = getattr(widget, "_inline_preview_warmup", None)
                if warmup is not None:
                    warmup.deleteLater()
                    setattr(widget, "_inline_preview_warmup", None)
            except Exception:
                _LOGGER.debug("Failed disposing embedded selector warmup preview", exc_info=True)
            try:
                widget.setParent(None)
                widget.deleteLater()
            except Exception:
                _LOGGER.debug("Failed disposing embedded selector widget", exc_info=True)
        cache.clear()
    setattr(dialog, "_embedded_selector_widget_cache", {})

    bundle = getattr(dialog, "_embedded_selector_service_bundle", None)
    if isinstance(bundle, dict):
        # Only close DB handles we own (not preload_manager's).
        if not bundle.get("_owned_by_preload"):
            for key in ("tool_db", "jaw_db", "fixture_db"):
                db = bundle.get(key)
                close = getattr(db, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        _LOGGER.debug("Failed closing embedded selector database handle %s", key, exc_info=True)
        bundle.clear()
    setattr(dialog, "_embedded_selector_service_bundle", None)

    release_tool_library_namespace_aliases(dialog)


def warmup_embedded_selector_runtime(dialog: Any) -> None:
    """Preload selector import aliases and service bundle for first-open smoothness."""
    _activate_tool_library_namespace_aliases(dialog)
    _ensure_service_bundle(dialog)


def warmup_embedded_tool_selector_widget(
    dialog: Any,
    *,
    mount_container: QWidget | None = None,
    selector_head: str = "HEAD1",
    selector_spindle: str = "main",
) -> None:
    """Prebuild and dispose an embedded Tool Selector to smooth first real open."""
    _activate_tool_library_namespace_aliases(dialog)
    services = _ensure_service_bundle(dialog)
    parent_widget = mount_container or dialog

    from tools_and_jaws_library.ui.selectors.tool_selector_dialog import ToolSelectorDialog

    widget = ToolSelectorDialog(
        tool_service=services["tool_service"],
        machine_profile=dialog.machine_profile,
        translate=dialog._t,
        selector_head=str(selector_head or "HEAD1"),
        selector_spindle=str(selector_spindle or "main"),
        initial_assignments=[],
        initial_assignment_buckets={},
        on_submit=lambda _payload: None,
        on_cancel=lambda: None,
        parent=parent_widget,
        embedded_mode=True,
    )

    widget.setWindowFlags(Qt.Widget)
    widget.setWindowModality(Qt.NonModal)
    widget.setAttribute(Qt.WA_DontShowOnScreen, True)
    widget.setVisible(False)
    _prime_embedded_selector_widget(widget)
    _apply_embedded_selector_style(widget)
    widget.setParent(None)
    widget.deleteLater()


def _ensure_service_bundle(dialog: Any) -> dict[str, Any]:
    bundle = getattr(dialog, "_embedded_selector_service_bundle", None)
    if isinstance(bundle, dict):
        return bundle

    # Prefer preload_manager services when available (avoids duplicate DB connections).
    try:
        from services.preload_manager import get_preload_manager

        pm = get_preload_manager()
        if pm.initialized and pm.tool_service is not None and pm.jaw_service is not None and pm.fixture_service is not None:
            bundle = {
                "tool_service": pm.tool_service,
                "jaw_service": pm.jaw_service,
                "fixture_service": pm.fixture_service,
                "tool_db": None,
                "jaw_db": None,
                "fixture_db": None,
                "_owned_by_preload": True,
            }
            setattr(dialog, "_embedded_selector_service_bundle", bundle)
            return bundle
    except Exception:
        _LOGGER.debug("_ensure_service_bundle: preload_manager not available, falling back to local connections", exc_info=True)

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
QWidget[selectorContext="true"] {
    background-color: #ffffff;
    border: none;
    border-radius: 2px;
}

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
QWidget[selectorContext="true"] QFrame[bottomBar="true"] {
    background-color: transparent;
    border: none;
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
QWidget[selectorContext="true"] QFrame[embeddedSelectorToolbar="true"] {
    background-color: #ffffff;
    border: 1px solid #d5dee8;
    border-radius: 8px;
}
QWidget[selectorContext="true"] QLabel[embeddedSectionTitle="true"] {
    font-size: 10pt;
    font-weight: 700;
    color: #263442;
    background: transparent;
}
QWidget[selectorContext="true"] QListWidget#embeddedCatalogList {
    background-color: #ffffff;
    border: 1px solid #d0d8e0;
    border-radius: 8px;
    outline: none;
    padding: 6px;
}
QWidget[selectorContext="true"] QListWidget#embeddedCatalogList::item {
    background-color: #ffffff;
    border: 1px solid #cad6e2;
    border-radius: 7px;
    padding: 8px 10px;
    margin: 3px;
    color: #18232f;
}
QWidget[selectorContext="true"] QListWidget#embeddedCatalogList::item:hover {
    background-color: #f6fbff;
    border: 1px solid #a9c5df;
}
QWidget[selectorContext="true"] QListWidget#embeddedCatalogList::item:selected {
    background-color: #e8f5ff;
    border: 2px solid #00C8FF;
    color: #13202b;
}
QWidget[selectorContext="true"] QListWidget#legacyToolIdsOrderList {
    background-color: transparent;
    border: none;
    outline: none;
    padding: 4px;
}
QWidget[selectorContext="true"] QListWidget#legacyToolIdsOrderList::item {
    background-color: #ffffff;
    border: 1px solid #99acbf;
    border-radius: 8px;
    padding: 7px 9px;
    margin: 3px 1px;
    color: #171a1d;
}
QWidget[selectorContext="true"] QListWidget#toolIdsOrderList::item:selected {
    background-color: #ffffff;
    border: 2px solid #00C8FF;
    color: #24303c;
}
QWidget[selectorContext="true"] QPushButton[embeddedSlotCard="true"] {
    background-color: #ffffff;
    border: 1px solid #99acbf;
    border-radius: 8px;
    padding: 10px;
    color: #171a1d;
    text-align: left;
    font-weight: 600;
}
QWidget[selectorContext="true"] QPushButton[embeddedSlotCard="true"]:hover {
    background-color: #f6fbff;
    border: 1px solid #7fb5dc;
}
QWidget[selectorContext="true"] QPushButton[embeddedSlotCard="true"]:checked {
    background-color: #ffffff;
    border: 2px solid #00C8FF;
    color: #24303c;
}
QWidget[selectorContext="true"] QLabel[toolBadge="true"] {
    background-color: #e7f1fb;
    color: #1d5f9d;
    border: 1px solid #c2d9ee;
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 9pt;
    font-weight: 600;
    min-height: 18px;
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
QWidget[selectorContext="true"] QListWidget#legacyToolIdsOrderList::item:hover {
    background-color: transparent;
    border: none;
}

QWidget[selectorContext="true"] QListWidget#legacyToolIdsOrderList::item:selected,
QWidget[selectorContext="true"] QListWidget#legacyToolIdsOrderList::item:selected:active,
QWidget[selectorContext="true"] QListWidget#legacyToolIdsOrderList::item:selected:!active {
    background-color: transparent;
    border: none;
    color: inherit;
}
QWidget[selectorContext="true"] QListWidget#legacyToolIdsOrderList::viewport {
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
    for combo in widget.findChildren(QComboBox):
        if combo.objectName() == "topTypeFilter":
            combo.setProperty("modernDropdown", True)
            combo.setProperty("dropdownSizeProfile", "compact")
            if not bool(getattr(widget, "_embedded_mode", False)):
                apply_shared_dropdown_style(combo)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


def _prime_embedded_selector_widget(widget: Any) -> None:
    if widget is None:
        return
    ensure_polished = getattr(widget, "ensurePolished", None)
    if callable(ensure_polished):
        ensure_polished()
    layout = getattr(widget, "layout", lambda: None)()
    if layout is not None:
        layout.activate()
    if isinstance(widget, QWidget):
        for child in widget.findChildren(QWidget):
            child_ensure_polished = getattr(child, "ensurePolished", None)
            if callable(child_ensure_polished):
                child_ensure_polished()
            child_layout = child.layout()
            if child_layout is not None:
                child_layout.activate()
            child_style = child.style()
            if child_style is not None:
                child_style.unpolish(child)
                child_style.polish(child)


def _warm_embedded_tool_selector_preview(widget: Any) -> None:
    if widget is None:
        return
    # Embedded selector startup must stay side-effect free. The preview engine
    # is already warmed by the library process preload path, and forcing a
    # hidden preview widget show/hide cycle here can destabilize the Work
    # Editor modal session.
    _LOGGER.debug("Embedded tool selector preview warmup disabled for modal safety")


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
    parent_widget = mount_container or dialog
    cache = _selector_widget_cache(dialog)
    _trace_selector_event(
        dialog,
        "factory.build.begin",
        kind=kind_key,
        parent_type=type(parent_widget).__name__ if parent_widget is not None else None,
        diagnostic_kind=_selector_diagnostic_kind(),
    )

    if _selector_diagnostic_kind() == "trivial":
        widget = _build_trivial_diagnostic_selector_widget(
            kind=kind_key,
            parent=parent_widget,
            on_submit=on_submit,
            on_cancel=on_cancel,
        )
        _trace_selector_event(
            dialog,
            "factory.build.diagnostic",
            kind=kind_key,
            diagnostic_kind=_selector_diagnostic_kind(),
            snapshot=_selector_widget_snapshot(widget),
        )
        widget.setParent(parent_widget, Qt.Widget)
        widget.setWindowFlag(Qt.Window, False)
        widget.setWindowModality(Qt.NonModal)
        widget.setVisible(False)
        _prime_embedded_selector_widget(widget)
        _apply_embedded_selector_style(widget)
        return widget

    _activate_tool_library_namespace_aliases(dialog)
    services = _ensure_service_bundle(dialog)

    widget = cache.get(kind_key)

    if kind_key == "tools":
        if widget is None:
            from tools_and_jaws_library.ui.selectors.tool_selector_dialog import EmbeddedToolSelectorWidget

            widget = EmbeddedToolSelectorWidget(
                tool_service=services["tool_service"],
                machine_profile=dialog.machine_profile,
                translate=dialog._t,
                selector_head=str(head or ""),
                selector_spindle=str(spindle or ""),
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
                on_submit=on_submit,
                on_cancel=on_cancel,
                parent=parent_widget,
            )
            if not hasattr(widget, "_refresh_elided_group_title"):
                setattr(widget, "_refresh_elided_group_title", lambda *_args, **_kwargs: None)
            cache[kind_key] = widget
    elif kind_key == "jaws":
        if widget is None:
            from tools_and_jaws_library.ui.selectors.jaw_selector_dialog import EmbeddedJawSelectorWidget

            widget = EmbeddedJawSelectorWidget(
                jaw_service=services["jaw_service"],
                machine_profile=dialog.machine_profile,
                translate=dialog._t,
                selector_spindle=str(spindle or ""),
                initial_assignments=initial_assignments,
                on_submit=on_submit,
                on_cancel=on_cancel,
                parent=parent_widget,
            )
            cache[kind_key] = widget
    else:
        if widget is None:
            from tools_and_jaws_library.ui.selectors.fixture_selector_dialog import FixtureSelectorDialog

            widget = FixtureSelectorDialog(
                fixture_service=services["fixture_service"],
                translate=dialog._t,
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
                initial_target_key=str((follow_up or {}).get("target_key") or ""),
                on_submit=on_submit,
                on_cancel=on_cancel,
                parent=parent_widget,
                embedded_mode=True,
            )
            cache[kind_key] = widget

    if kind_key == "tools":
        prepare = getattr(widget, "prepare_for_session", None)
        if callable(prepare):
            prepare(
                selector_head=str(head or ""),
                selector_spindle=str(spindle or ""),
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
                on_submit=on_submit,
                on_cancel=on_cancel,
            )
        setattr(widget, "_reuse_cached_selector_widget", True)
    elif kind_key == "jaws":
        prepare = getattr(widget, "prepare_for_session", None)
        if callable(prepare):
            prepare(
                selector_spindle=str(spindle or ""),
                initial_assignments=initial_assignments,
                on_submit=on_submit,
                on_cancel=on_cancel,
            )
        setattr(widget, "_reuse_cached_selector_widget", True)
    else:
        reset = getattr(widget, "reset_for_session", None)
        if callable(reset):
            reset(
                initial_assignments=initial_assignments,
                initial_assignment_buckets=initial_assignment_buckets,
                initial_target_key=str((follow_up or {}).get("target_key") or ""),
                on_submit=on_submit,
                on_cancel=on_cancel,
            )
        setattr(widget, "_reuse_cached_selector_widget", True)

    _trace_selector_event(
        dialog,
        "factory.build.constructed",
        kind=kind_key,
        snapshot=_selector_widget_snapshot(widget),
    )

    # Some selector implementations still derive from QDialog. Even when they
    # are constructed for embedded mode, explicitly re-parent them under the
    # mount container with child-widget flags so they cannot surface as native
    # top-level windows.
    widget.setParent(parent_widget, Qt.Widget)
    widget.hide()

    _trace_selector_event(
        dialog,
        "factory.build.reparented",
        kind=kind_key,
        snapshot=_selector_widget_snapshot(widget),
    )
    _prime_embedded_selector_widget(widget)
    _apply_embedded_selector_style(widget)
    _trace_selector_event(
        dialog,
        "factory.build.ready",
        kind=kind_key,
        snapshot=_selector_widget_snapshot(widget),
    )
    return widget

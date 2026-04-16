from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .library_ipc import allow_set_foreground


_NO_MATCH_ID = "__NO_MATCH_LINKED_ITEMS__"


def complete_tool_library_handoff(window) -> None:
    window.hide()
    window.setWindowOpacity(1.0)


def _selected_module(module: str) -> str:
    if module == "fixtures":
        return "fixtures"
    if module == "jaws":
        return "jaws"
    return "tools"


def _library_payload(window, *, module: str, geometry: str, clear_master_filter: bool = False, safe_tools=None, safe_jaws=None) -> dict:
    payload = {
        "geometry": geometry,
        "show": True,
        "module": _selected_module(module),
        "tools_db_path": str(window.draw_service.tool_db_path),
        "jaws_db_path": str(window.draw_service.jaw_db_path),
        "fixtures_db_path": str(getattr(window.draw_service, "fixture_db_path", window.draw_service.jaw_db_path)),
    }
    if clear_master_filter:
        payload["clear_master_filter"] = True
    if safe_tools is not None:
        payload["master_filter_tools"] = list(safe_tools)
    if safe_jaws is not None:
        payload["master_filter_jaws"] = list(safe_jaws)
    if safe_tools is not None or safe_jaws is not None:
        payload["master_filter_active"] = True
    return payload


def open_tool_library_module(window, module: str) -> None:
    x, y, width, height = window._current_window_rect()
    geometry = f"{x},{y},{width},{height}"
    allow_set_foreground()

    payload = _library_payload(
        window,
        module=module,
        geometry=geometry,
        clear_master_filter=True,
    )
    if window._send_to_tool_library(payload):
        window._fade_out_and(lambda: complete_tool_library_handoff(window))
        return

    if window._launch_tool_library(["--geometry", geometry]):
        window._send_request_with_retry(
            payload,
            on_success=lambda: window._fade_out_and(lambda: complete_tool_library_handoff(window)),
        )
        return

    QMessageBox.warning(
        window,
        window._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
        window._t(
            "setup_manager.library_unavailable.body",
            "Could not find a launchable Tool Library executable or source entry point.",
        ),
    )


def open_tool_library_deep_link(window, kind: str, item_id: str) -> None:
    x, y, width, height = window._current_window_rect()
    geometry = f"{x},{y},{width},{height}"
    if kind == "jaw":
        args = ["--geometry", geometry, "--open-jaw", item_id] if item_id else []
    else:
        args = ["--geometry", geometry, "--open-tool", item_id] if item_id else []
    if window._launch_tool_library(args):
        return
    QMessageBox.warning(
        window,
        window._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
        window._t(
            "setup_manager.library_unavailable.body",
            "Could not find a launchable Tool Library executable or source entry point.",
        ),
    )


def open_tool_library_with_master_filter(window, tool_ids, jaw_ids, module: str = "tools") -> None:
    raw_tools = [str(t).strip() for t in (tool_ids or []) if str(t).strip()]
    raw_jaws = [str(j).strip() for j in (jaw_ids or []) if str(j).strip()]
    safe_tools = list(raw_tools) if raw_tools else [_NO_MATCH_ID]
    safe_jaws = list(raw_jaws) if raw_jaws else [_NO_MATCH_ID]
    selected_module = _selected_module(module)

    if selected_module == "tools" and tool_ids is not None and not raw_tools:
        QMessageBox.information(
            window,
            window._t("setup_manager.viewer.title", "Viewer"),
            window._t("setup_manager.viewer.no_tools", "No tools selected for this work."),
        )
    if selected_module == "jaws" and jaw_ids is not None and not raw_jaws:
        QMessageBox.information(
            window,
            window._t("setup_manager.viewer.title", "Viewer"),
            window._t("setup_manager.viewer.no_jaws", "No jaws selected for this work."),
        )
    if selected_module == "fixtures" and jaw_ids is not None and not raw_jaws:
        QMessageBox.information(
            window,
            window._t("setup_manager.viewer.title", "Viewer"),
            window._t("setup_manager.viewer.no_fixtures", "No fixtures selected for this work."),
        )

    x, y, width, height = window._current_window_rect()
    geometry = f"{x},{y},{width},{height}"
    allow_set_foreground()

    payload = _library_payload(
        window,
        module=selected_module,
        geometry=geometry,
        safe_tools=safe_tools,
        safe_jaws=safe_jaws,
    )
    if window._send_to_tool_library(payload):
        window._fade_out_and(lambda: complete_tool_library_handoff(window))
        return

    args = [
        "--geometry",
        geometry,
        "--master-filter-tools",
        ",".join(safe_tools),
        "--master-filter-jaws",
        ",".join(safe_jaws),
        "--master-filter-active",
        "1",
    ]
    if window._launch_tool_library(args):
        window._send_request_with_retry(
            payload,
            on_success=lambda: window._fade_out_and(lambda: complete_tool_library_handoff(window)),
        )
        return

    QMessageBox.warning(
        window,
        window._t("setup_manager.library_unavailable.title", "Tool Library unavailable"),
        window._t(
            "setup_manager.library_unavailable.body",
            "Could not find a launchable Tool Library executable or source entry point.",
        ),
    )

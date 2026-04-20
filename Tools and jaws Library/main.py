import json
import sys
import ctypes
import ctypes.wintypes
import traceback
from pathlib import Path

# Add parent directory to path so shared module can be imported
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QProgressDialog

from shared.ui.bootstrap_visual import FastTooltipStyle, build_fixed_light_palette as _build_fixed_light_palette


def _split_csv(text: str) -> list[str]:
    return [part.strip() for part in (text or '').split(',') if part.strip()]


def _build_launch_payload(args) -> dict:
    return {
        'geometry': str(args.geometry or '').strip(),
        'kind': 'jaw' if str(args.open_jaw or '').strip() else ('tool' if str(args.open_tool or '').strip() else ''),
        'item_id': str(args.open_jaw or args.open_tool or '').strip(),
        'master_filter_tools': _split_csv(args.master_filter_tools),
        'master_filter_jaws': _split_csv(args.master_filter_jaws),
        'master_filter_active': str(args.master_filter_active).strip() not in {'0', 'false', 'False', ''},
        'show': not bool(args.hidden),
    }


def _send_to_existing_instance(server_name: str, payload: dict) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if not socket.waitForConnected(350):
        return False
    try:
        socket.write(json.dumps(payload).encode('utf-8'))
        socket.flush()
        socket.waitForBytesWritten(900)
    finally:
        socket.disconnectFromServer()
    return True


def _apply_frame_geometry_string(widget, geometry_text: str) -> bool:
    try:
        x, y, width, height = (int(v) for v in str(geometry_text or "").split(","))
    except Exception:
        return False
    if width <= 0 or height <= 0:
        return False
    try:
        hwnd = int(widget.winId())
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            0,
            x,
            y,
            width,
            height,
            SWP_NOZORDER | SWP_NOACTIVATE,
        )
    except Exception:
        return False
    return True


def main():
    # Avoid fractional-scale half-pixel painting artifacts on Windows.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.RoundPreferFloor
    )

    app = QApplication(sys.argv)
    # Parse deep-link and geometry arguments before Qt consumes argv.
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--open-jaw", default="", dest="open_jaw")
    parser.add_argument("--open-tool", default="", dest="open_tool")
    parser.add_argument("--geometry", default="", dest="geometry")
    parser.add_argument("--hidden", action="store_true", dest="hidden")
    parser.add_argument("--master-filter-tools", default="", dest="master_filter_tools")
    parser.add_argument("--master-filter-jaws", default="", dest="master_filter_jaws")
    parser.add_argument("--master-filter-active", default="0", dest="master_filter_active")
    _known_args, _remaining = parser.parse_known_args()

    from config import TOOL_LIBRARY_SERVER_NAME

    launch_payload = _build_launch_payload(_known_args)
    if _send_to_existing_instance(TOOL_LIBRARY_SERVER_NAME, launch_payload):
        return

    app.setStyle('Fusion')
    app.setPalette(_build_fixed_light_palette())
    app.setStyle(FastTooltipStyle(app.style()))
    app.setQuitOnLastWindowClosed(not _known_args.hidden)

    splash = None
    if not _known_args.hidden:
        splash = QProgressDialog('Starting Tools and jaws Library...', '', 0, 8)
        splash.setWindowTitle('Loading')
        splash.setWindowModality(Qt.ApplicationModal)
        splash.setCancelButton(None)
        splash.setMinimumDuration(0)
        splash.setAutoClose(False)
        splash.setAutoReset(False)
        splash.resize(460, 110)
        splash.setStyleSheet(
            "QProgressDialog {"
            " background-color: #eef3f8;"
            " border: 1px solid #c8d4e0;"
            " border-radius: 8px;"
            " font-family: 'Segoe UI';"
            " font-size: 10pt;"
            " color: #2b3136;"
            "}"
            "QProgressDialog QLabel {"
            " background: transparent;"
            " font-family: 'Segoe UI';"
            " font-size: 9.5pt;"
            " font-weight: 600;"
            " color: #2b3136;"
            "}"
            "QProgressBar {"
            " border: 1px solid #c8cfd6;"
            " background: #ffffff;"
            " border-radius: 4px;"
            " color: #2b3136;"
            " text-align: center;"
            "}"
            "QProgressBar::chunk {"
            " background: #2fa1ee;"
            " border-radius: 3px;"
            "}"
        )
        splash.show()

    def step(progress: int, text: str):
        if splash is not None:
            splash.setLabelText(text)
            splash.setValue(progress)
        app.processEvents()

    step(1, 'Loading modules...')
    from config import DB_PATH, FIXTURES_DB_PATH, JAWS_DB_PATH, SETTINGS_PATH, TOOL_LIBRARY_READY_PATH, TOOL_LIBRARY_SERVER_NAME
    from data.database import Database
    from services.export_service import ExportService
    from services.fixture_service import FixtureService
    from services.jaw_service import JawService
    from services.settings_service import SettingsService
    from services.tool_service import ToolService
    from ui.main_window import MainWindow

    step(2, 'Connecting database...')
    db = Database(DB_PATH)
    from data.fixture_database import FixtureDatabase
    from data.jaw_database import JawDatabase
    jaws_db = JawDatabase(JAWS_DB_PATH)
    fixtures_db = FixtureDatabase(FIXTURES_DB_PATH)

    step(3, 'Loading tool service...')
    tool_service = ToolService(db)

    step(4, 'Loading export service...')
    export_service = ExportService()

    step(5, 'Loading jaw service...')
    jaw_service = JawService(jaws_db)
    fixture_service = FixtureService(fixtures_db)

    step(6, 'Loading settings...')
    settings_service = SettingsService(SETTINGS_PATH)

    step(7, 'Preparing 3D preview...')
    app._preview_warmup_widget = None

    step(8, 'Opening main window...')

    launch_master_filter = {
        "enabled": bool(_split_csv(_known_args.master_filter_tools) or _split_csv(_known_args.master_filter_jaws)),
        "active": str(_known_args.master_filter_active).strip() not in {"0", "false", "False", ""},
        "tool_ids": _split_csv(_known_args.master_filter_tools),
        "jaw_ids": _split_csv(_known_args.master_filter_jaws),
    }

    win = MainWindow(
        tool_service,
        jaw_service,
        fixture_service,
        export_service,
        settings_service,
        launch_master_filter=launch_master_filter,
    )

    QTimer.singleShot(50, win.preload_catalog_pages)

    def warm_preview_after_startup():
        if getattr(app, '_preview_warmup_widget', None) is not None:
            return
        try:
            from shared.ui.stl_preview import StlPreviewWidget
            warmup = StlPreviewWidget()
            # Qt.Tool suppresses the taskbar entry for this invisible warmup window.
            warmup.setWindowFlag(Qt.Tool)
            # Show at real off-screen coordinates so Windows creates the HWND
            # and D3D11 compositor surface now, not on first user interaction.
            # WA_DontShowOnScreen intentionally NOT used — it skips surface creation.
            warmup.setGeometry(-32000, -32000, 8, 8)
            warmup.show()
            app.processEvents()
            # Keep alive for the full app session.  Destroying the last
            # QWebEngineView shuts down Chromium; any subsequent creation
            # would cold-start and freeze the UI.
            app._preview_warmup_widget = warmup
        except Exception:
            app._preview_warmup_widget = None

    app._preview_warmup_scheduled = False

    def schedule_preview_warmup(delay_ms: int = 250) -> None:
        if getattr(app, '_preview_warmup_widget', None) is not None:
            return
        if bool(getattr(app, '_preview_warmup_scheduled', False)):
            return

        app._preview_warmup_scheduled = True

        def _run_warmup() -> None:
            app._preview_warmup_scheduled = False
            warm_preview_after_startup()

        QTimer.singleShot(max(0, int(delay_ms)), _run_warmup)

    # In hidden preload mode, defer warmup until the main window is surfaced to
    # avoid a separate off-screen helper window appearing in task switching.
    if not _known_args.hidden:
        schedule_preview_warmup(250)

    if not _known_args.hidden:
        win.show()
    # Hidden mode: window stays hidden until an IPC show request arrives.
    # No brief show/hide cycle to avoid taskbar flashing on Windows.

    server = QLocalServer(app)
    if not server.listen(TOOL_LIBRARY_SERVER_NAME):
        QLocalServer.removeServer(TOOL_LIBRARY_SERVER_NAME)
        server.listen(TOOL_LIBRARY_SERVER_NAME)

    try:
        TOOL_LIBRARY_READY_PATH.write_text("ready", encoding="utf-8")
    except Exception:
        pass

    def cleanup_runtime_files():
        try:
            TOOL_LIBRARY_READY_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        QLocalServer.removeServer(TOOL_LIBRARY_SERVER_NAME)

    def process_external_request(payload: dict):
        command = str((payload or {}).get('command') or '').strip().lower()
        if command == 'shutdown':
            app.quit()
            return

        # Capture visibility BEFORE apply_external_request so _show_main_window
        # has the true pre-handoff state even if apply_external_request shows the
        # window as a side effect.
        was_visible = bool(win.isVisible() and not win.isMinimized())
        win.apply_external_request(payload)
        geometry_text = str(payload.get('geometry', '')).strip()
        selector_mode = str(payload.get('selector_mode', '')).strip().lower()
        selector_active_request = selector_mode in {'tools', 'jaws', 'fixtures'}

        if bool(payload.get('show', True)):
            # Selector sessions run in standalone dialogs while the main window
            # stays hidden. If quitOnLastWindowClosed is True here, closing the
            # selector dialog can terminate the background Tool Library process,
            # forcing a relaunch (visible flash) on the next open.
            app.setQuitOnLastWindowClosed(not selector_active_request)
            try:
                TOOL_LIBRARY_READY_PATH.write_text("ready", encoding="utf-8")
            except Exception:
                pass

            # Selector requests are hosted in standalone dialogs; do not surface
            # the main library window behind them.
            if selector_active_request:
                # Standalone selector sessions still need preview warmup so the
                # first detached 3D preview open does not cold-start Chromium.
                # The helper window is a Qt.Tool off-screen surface, so warming
                # here does not force the main library window visible.
                schedule_preview_warmup(80)
                return

            # Warm up preview only when the main library window is actually
            # being shown.
            schedule_preview_warmup(80)

            # Defer top-level visibility changes out of the socket callback so
            # selector/session transitions settle before foreground activation.
            def _show_main_window() -> None:
                if not was_visible:
                    # Ensure the window is hidden and transparent before geometry
                    # is applied so it never flashes at the wrong position.
                    win.hide()
                    win.setWindowOpacity(0.0)
                if geometry_text:
                    # Apply geometry while still hidden (or before raising) so
                    # the window appears at the correct position on first paint.
                    _apply_frame_geometry_string(win, geometry_text)
                if win.isMinimized():
                    win.showNormal()
                if not win.isVisible():
                    win.show()
                if geometry_text:
                    _apply_frame_geometry_string(win, geometry_text)
                    QTimer.singleShot(0, lambda text=geometry_text: _apply_frame_geometry_string(win, text))
                    QTimer.singleShot(120, lambda text=geometry_text: _apply_frame_geometry_string(win, text))
                if not was_visible:
                    # Smooth fade-in instead of a hard opacity snap.
                    win.fade_in()
                win.raise_()
                win.activateWindow()
                # Belt-and-suspenders: use Win32 API for reliable foreground activation.
                try:
                    import ctypes
                    hwnd = int(win.winId())
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass

            QTimer.singleShot(0, _show_main_window)

    def handle_new_connection():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()

            def consume_socket(sock=socket):
                try:
                    raw = bytes(sock.readAll()).decode('utf-8').strip()
                    if raw:
                        process_external_request(json.loads(raw))
                except Exception:
                    # Never fail silently here: Setup Manager handoff depends on this path.
                    traceback.print_exc()
                finally:
                    sock.disconnectFromServer()
                    sock.deleteLater()

            socket.readyRead.connect(consume_socket)
            if socket.bytesAvailable() > 0:
                consume_socket()

    server.newConnection.connect(handle_new_connection)

    app.aboutToQuit.connect(cleanup_runtime_files)

    if splash is not None:
        splash.close()

    # Restore geometry if launched with --geometry X,Y,W,H
    if _known_args.geometry:
        _apply_frame_geometry_string(win, _known_args.geometry)
        QTimer.singleShot(0, lambda text=_known_args.geometry: _apply_frame_geometry_string(win, text))
        QTimer.singleShot(120, lambda text=_known_args.geometry: _apply_frame_geometry_string(win, text))

    # Navigate to a specific jaw or tool if requested.
    if _known_args.open_jaw:
        _jaw_id = _known_args.open_jaw
        QTimer.singleShot(400, lambda: win.navigate_to("jaw", _jaw_id))
    elif _known_args.open_tool:
        _tool_id = _known_args.open_tool
        QTimer.singleShot(400, lambda: win.navigate_to("tool", _tool_id))
    elif _split_csv(_known_args.master_filter_tools):
        # Default to tools module when opened with a tool master filter.
        QTimer.singleShot(100, lambda: win._apply_module_mode("tools"))

    sys.exit(app.exec())


if __name__ == '__main__':
    main()

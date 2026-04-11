import json
import sys
import ctypes
import ctypes.wintypes
import traceback
from PySide6.QtCore import QTimer, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QProgressDialog, QProxyStyle, QStyle


class FastTooltipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return 150
        if hint == QStyle.SH_ToolTip_FallAsleepDelay:
            return 20000
        return super().styleHint(hint, option, widget, returnData)


def _build_fixed_light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor('#eef3f8'))
    palette.setColor(QPalette.WindowText, QColor('#1f252b'))
    palette.setColor(QPalette.Base, QColor('#ffffff'))
    palette.setColor(QPalette.AlternateBase, QColor('#f6f9fc'))
    palette.setColor(QPalette.ToolTipBase, QColor('#ffffff'))
    palette.setColor(QPalette.ToolTipText, QColor('#1f252b'))
    palette.setColor(QPalette.Text, QColor('#1f252b'))
    palette.setColor(QPalette.Button, QColor('#f7fafc'))
    palette.setColor(QPalette.ButtonText, QColor('#1f252b'))
    palette.setColor(QPalette.BrightText, QColor('#ffffff'))
    palette.setColor(QPalette.Highlight, QColor('#2fa1ee'))
    palette.setColor(QPalette.HighlightedText, QColor('#ffffff'))
    palette.setColor(QPalette.Link, QColor('#2fa1ee'))
    palette.setColor(QPalette.PlaceholderText, QColor('#6c7a88'))
    return palette


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
    if not socket.waitForConnected(250):
        return False
    try:
        socket.write(json.dumps(payload).encode('utf-8'))
        socket.flush()
        socket.waitForBytesWritten(250)
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
    from config import DB_PATH, JAWS_DB_PATH, SETTINGS_PATH, TOOL_LIBRARY_READY_PATH, TOOL_LIBRARY_SERVER_NAME
    from data.database import Database
    from services.export_service import ExportService
    from services.jaw_service import JawService
    from services.settings_service import SettingsService
    from services.tool_service import ToolService
    from ui.main_window import MainWindow

    step(2, 'Connecting database...')
    db = Database(DB_PATH)
    from data.jaw_database import JawDatabase
    jaws_db = JawDatabase(JAWS_DB_PATH)

    step(3, 'Loading tool service...')
    tool_service = ToolService(db)

    step(4, 'Loading export service...')
    export_service = ExportService()

    step(5, 'Loading jaw service...')
    jaw_service = JawService(jaws_db)

    step(6, 'Loading settings...')
    settings_service = SettingsService(SETTINGS_PATH)

    step(7, 'Warming up 3D preview...')
    try:
        from ui.stl_preview import StlPreviewWidget
        app._preview_warmup_widget = StlPreviewWidget()
        app._preview_warmup_widget.hide()
    except Exception:
        app._preview_warmup_widget = None

    step(8, 'Opening main window...')

    launch_master_filter = {
        "enabled": bool(_split_csv(_known_args.master_filter_tools) or _split_csv(_known_args.master_filter_jaws)),
        "active": str(_known_args.master_filter_active).strip() not in {"0", "false", "False", ""},
        "tool_ids": _split_csv(_known_args.master_filter_tools),
        "jaw_ids": _split_csv(_known_args.master_filter_jaws),
    }

    win = MainWindow(tool_service, jaw_service, export_service, settings_service, launch_master_filter=launch_master_filter)

    if not _known_args.hidden:
        win.show()
    else:
        # Pre-create the native window off-screen so the first real open does not
        # pay the one-time window creation / first-paint cost.
        win.setAttribute(Qt.WA_DontShowOnScreen, True)
        win.show()
        app.processEvents()
        win.hide()
        win.setAttribute(Qt.WA_DontShowOnScreen, False)

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
        win.apply_external_request(payload)
        geometry_text = str(payload.get('geometry', '')).strip()

        if bool(payload.get('show', True)):
            app.setQuitOnLastWindowClosed(True)
            try:
                TOOL_LIBRARY_READY_PATH.write_text("ready", encoding="utf-8")
            except Exception:
                pass

            win.setWindowOpacity(1.0)
            if win.isMinimized():
                win.showNormal()
            win.show()
            if geometry_text:
                _apply_frame_geometry_string(win, geometry_text)
                QTimer.singleShot(0, lambda text=geometry_text: _apply_frame_geometry_string(win, text))
                QTimer.singleShot(120, lambda text=geometry_text: _apply_frame_geometry_string(win, text))
            win.raise_()
            win.activateWindow()
            # Belt-and-suspenders: use Win32 API for reliable foreground activation.
            try:
                import ctypes
                hwnd = int(win.winId())
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            win.fade_in()

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

    if getattr(app, '_preview_warmup_widget', None) is not None:
        QTimer.singleShot(1500, app._preview_warmup_widget.deleteLater)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

import argparse
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QProgressDialog, QProxyStyle, QStyle


def _is_runnable_python(candidate: Path) -> bool:
    try:
        completed = subprocess.run(
            [str(candidate), "-c", "import sys"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except Exception:
        return False
    return completed.returncode == 0


def _project_venv_python() -> Path | None:
    scripts_dir = Path(__file__).resolve().parent.parent / ".venv" / "Scripts"
    current_name = Path(sys.executable).name.lower()
    candidates = ["python.exe", "pythonw.exe"]
    if "pythonw" in current_name:
        candidates = ["pythonw.exe", "python.exe"]
    for name in candidates:
        candidate = scripts_dir / name
        if candidate.exists() and _is_runnable_python(candidate):
            return candidate
    return None


def _maybe_relaunch_with_project_venv() -> None:
    if getattr(sys, "frozen", False):
        return
    if os.environ.get("NTX_SETUP_MANAGER_VENV_RELAUNCHED") == "1":
        return

    target_python = _project_venv_python()
    if target_python is None:
        return

    try:
        current_python = Path(sys.executable).resolve()
        target_resolved = target_python.resolve()
    except Exception:
        return

    if current_python == target_resolved:
        return

    env = os.environ.copy()
    env["NTX_SETUP_MANAGER_VENV_RELAUNCHED"] = "1"
    args = [str(target_resolved), str(Path(__file__).resolve())] + sys.argv[1:]
    subprocess.Popen(args, cwd=str(Path(__file__).resolve().parent), env=env)
    raise SystemExit(0)


class FastTooltipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return 150
        if hint == QStyle.SH_ToolTip_FallAsleepDelay:
            return 20000
        return super().styleHint(hint, option, widget, returnData)


def main():
    _maybe_relaunch_with_project_venv()

    from PySide6.QtCore import QProcess
    from config import I18N_DIR, SHARED_UI_PREFERENCES_PATH

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--geometry", default="", dest="geometry")
    _known_args, _remaining = parser.parse_known_args()

    def apply_frame_geometry_string(widget, geometry_text: str) -> bool:
        try:
            parts = [int(part) for part in str(geometry_text or "").strip().split(",")]
        except Exception:
            return False
        if len(parts) != 4:
            return False
        x, y, width, height = parts
        if width <= 0 or height <= 0:
            return False
        if x == -32000 and y == -32000:
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

    def tool_library_server_ready(server_name: str) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(server_name)
        ready = socket.waitForConnected(150)
        if ready:
            socket.disconnectFromServer()
        return ready

    def is_safe_tool_library_target(candidate: Path) -> bool:
        try:
            resolved = candidate.resolve()
            current = Path(sys.executable).resolve()
        except Exception:
            return False
        if not resolved.exists() or resolved == current:
            return False
        name = resolved.name.lower()
        return "tool library" in name

    def _load_loading_texts() -> dict:
        lang = "en"
        try:
            prefs = json.loads(Path(SHARED_UI_PREFERENCES_PATH).read_text(encoding="utf-8"))
            lang = str(prefs.get("language") or "en").strip().lower()
        except Exception:
            lang = "en"
        if lang not in {"en", "fi"}:
            lang = "en"
        try:
            return json.loads((Path(I18N_DIR) / f"{lang}.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    _texts = _load_loading_texts()

    def _lt(key: str, default: str) -> str:
        return str(_texts.get(key, default))

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyle(FastTooltipStyle(app.style()))
    app.setQuitOnLastWindowClosed(False)

    loading_header = _lt("setup_manager.loading.header", "INITIALIZE")
    splash = QProgressDialog(
        f"{loading_header}\n\n{_lt('setup_manager.loading.initial', 'Loading Tool Library and Setup Manager...')}",
        "",
        0,
        10,
    )
    splash.setWindowTitle(_lt("setup_manager.loading.window_title", "Loading"))
    splash.setWindowModality(Qt.ApplicationModal)
    splash.setCancelButton(None)
    splash.setMinimumDuration(0)
    splash.setAutoClose(False)
    splash.setAutoReset(False)
    splash.resize(460, 150)
    splash.show()

    def step(progress, text):
        splash.setLabelText(text)
        splash.setValue(progress)
        app.processEvents()

    # Step 0: Pre-load Tool Library in background
    step(1, f"{loading_header}\n\n{_lt('setup_manager.loading.start_tool_library', 'Starting Tool Library (hidden)...')}")
    from config import (
        APP_TITLE,
        DB_PATH,
        DRAWINGS_DIR,
        ENABLE_TOOL_LIBRARY_PRELOAD,
        JAW_LIBRARY_DB_PATH,
        TOOL_LIBRARY_DB_PATH,
        TOOL_LIBRARY_EXE_CANDIDATES,
        TOOL_LIBRARY_MAIN_PATH,
        TOOL_LIBRARY_PROJECT_DIR,
        TOOL_LIBRARY_SERVER_NAME,
        SETUP_MANAGER_SERVER_NAME,
    )

    geom_file = Path(DB_PATH).parent / ".window_geometry"
    tool_lib_args = ["--hidden"]  # Start hidden for faster switching
    launch_geometry = str(_known_args.geometry or "").strip()
    if not launch_geometry and geom_file.exists():
        try:
            launch_geometry = geom_file.read_text().strip()
        except Exception:
            launch_geometry = ""

    if launch_geometry:
        tool_lib_args.append(f"--geometry={launch_geometry}")

    # Launch Tool Library immediately only when explicitly enabled.
    if ENABLE_TOOL_LIBRARY_PRELOAD:
        tool_lib_process = None
        if TOOL_LIBRARY_MAIN_PATH.exists() and not getattr(sys, "frozen", False):
            tool_lib_process = QProcess()
            tool_lib_process.startDetached(
                str(Path(sys.executable)),
                [str(TOOL_LIBRARY_MAIN_PATH)] + tool_lib_args,
                str(TOOL_LIBRARY_PROJECT_DIR),
            )
        if tool_lib_process is None:
            for exe_path in TOOL_LIBRARY_EXE_CANDIDATES:
                if not is_safe_tool_library_target(exe_path):
                    continue
                tool_lib_process = QProcess()
                tool_lib_process.startDetached(str(exe_path), tool_lib_args, str(exe_path.parent))
                break

    step(2, f"{loading_header}\n\n{_lt('setup_manager.loading.load_modules', 'Loading modules...')}")
    from data.database import Database
    from services.draw_service import DrawService
    from services.logbook_service import LogbookService
    from services.print_service import PrintService
    from services.work_service import WorkService
    from ui.main_window import MainWindow

    step(3, f"{loading_header}\n\n{_lt('setup_manager.loading.connect_db', 'Connecting setup database...')}")
    db = Database(DB_PATH)

    step(4, f"{loading_header}\n\n{_lt('setup_manager.loading.load_work_service', 'Loading work service...')}")
    work_service = WorkService(db)

    step(5, f"{loading_header}\n\n{_lt('setup_manager.loading.load_logbook_service', 'Loading logbook service...')}")
    logbook_service = LogbookService(db)

    step(6, f"{loading_header}\n\n{_lt('setup_manager.loading.load_drawing_service', 'Loading drawing service...')}")
    draw_service = DrawService(
        drawing_dir=DRAWINGS_DIR,
        tool_db_path=TOOL_LIBRARY_DB_PATH,
        jaw_db_path=JAW_LIBRARY_DB_PATH,
    )

    step(7, f"{loading_header}\n\n{_lt('setup_manager.loading.load_print_service', 'Loading print service...')}")
    print_service = PrintService(APP_TITLE)
    print_service.set_reference_service(draw_service)

    step(8, f"{loading_header}\n\n{_lt('setup_manager.loading.warm_preview', 'Warming up 3D preview...')}")
    try:
        from ui.stl_preview import StlPreviewWidget

        app._preview_warmup_widget = StlPreviewWidget()
        app._preview_warmup_widget.hide()
    except Exception:
        app._preview_warmup_widget = None

    if ENABLE_TOOL_LIBRARY_PRELOAD:
        step(9, f"{loading_header}\n\n{_lt('setup_manager.loading.warm_tool_library', 'Tool Library warming up...')}")
        ready_deadline = time.time() + 12.0
        while time.time() < ready_deadline:
            if tool_library_server_ready(TOOL_LIBRARY_SERVER_NAME):
                break
            app.processEvents()
            time.sleep(0.1)
    else:
        step(9, f"{loading_header}\n\n{_lt('setup_manager.loading.skip_preload', 'Skipping Tool Library preload...')}")

    step(10, f"{loading_header}\n\n{_lt('setup_manager.loading.open_main', 'Opening Setup Manager...')}")
    win = MainWindow(work_service, logbook_service, draw_service, print_service)
    if launch_geometry:
        apply_frame_geometry_string(win, launch_geometry)

    server = QLocalServer(app)
    if not server.listen(SETUP_MANAGER_SERVER_NAME):
        QLocalServer.removeServer(SETUP_MANAGER_SERVER_NAME)
        server.listen(SETUP_MANAGER_SERVER_NAME)

    def show_setup_manager(request: dict | None = None):
        geometry_text = str((request or {}).get("geometry", "")).strip()
        win.setWindowOpacity(1.0)
        if win.isMinimized():
            win.showNormal()
        else:
            win.show()

        def _apply_handoff_bounds():
            if geometry_text:
                return apply_frame_geometry_string(win, geometry_text)
            return False

        if geometry_text:
            _apply_handoff_bounds()
            QTimer.singleShot(0, _apply_handoff_bounds)
            QTimer.singleShot(120, _apply_handoff_bounds)
            QTimer.singleShot(320, _apply_handoff_bounds)
        win.raise_()
        win.activateWindow()
        # Belt-and-suspenders: use Win32 API as well, since AllowSetForegroundWindow
        # was already called by the sender before sending the IPC "show" message.
        try:
            import ctypes
            hwnd = int(win.winId())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        win.fade_in()

    def process_show_requests():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            raw_payload = ""
            request = {"command": ""}
            try:
                if socket.waitForReadyRead(200):
                    raw_payload = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip()
            except Exception:
                raw_payload = ""
            finally:
                socket.disconnectFromServer()
                socket.deleteLater()

            if raw_payload:
                try:
                    parsed = json.loads(raw_payload)
                    if isinstance(parsed, dict):
                        request = parsed
                        request["command"] = str(parsed.get("command", "")).strip().lower()
                    else:
                        request["command"] = str(raw_payload).strip().lower()
                except Exception:
                    request["command"] = str(raw_payload).strip().lower()

            # Empty payload is treated as show request for compatibility.
            if request["command"] in {"", "show", "activate", "restore"}:
                show_setup_manager(request)

    server.newConnection.connect(process_show_requests)

    win.show()
    if launch_geometry:
        QTimer.singleShot(0, lambda text=launch_geometry: apply_frame_geometry_string(win, text))
        QTimer.singleShot(120, lambda text=launch_geometry: apply_frame_geometry_string(win, text))
    win.raise_()
    win.activateWindow()

    splash.close()

    if getattr(app, "_preview_warmup_widget", None) is not None:
        QTimer.singleShot(1200, app._preview_warmup_widget.deleteLater)

    def _cleanup_server():
        QLocalServer.removeServer(SETUP_MANAGER_SERVER_NAME)

    app.aboutToQuit.connect(_cleanup_server)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

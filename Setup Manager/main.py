import argparse
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add parent directory to path so shared module can be imported
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QProgressDialog

from shared.ui.bootstrap_visual import FastTooltipStyle, build_fixed_light_palette as _build_fixed_light_palette
from shared.ui.main_window_helpers import apply_frame_geometry_string as _apply_frame_geometry_string


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
    if (
        os.environ.get("SETUP_MANAGER_VENV_RELAUNCHED") == "1"
        or os.environ.get("NTX_SETUP_MANAGER_VENV_RELAUNCHED") == "1"
    ):
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
    env["SETUP_MANAGER_VENV_RELAUNCHED"] = "1"
    env["NTX_SETUP_MANAGER_VENV_RELAUNCHED"] = "1"
    args = [str(target_resolved), str(Path(__file__).resolve())] + sys.argv[1:]
    subprocess.Popen(args, cwd=str(Path(__file__).resolve().parent), env=env)
    raise SystemExit(0)


def main():
    _maybe_relaunch_with_project_venv()

    # Avoid fractional-scale half-pixel painting artifacts on Windows.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.RoundPreferFloor
    )

    from PySide6.QtCore import QProcess
    from config import I18N_DIR, SHARED_UI_PREFERENCES_PATH

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--geometry", default="", dest="geometry")
    _known_args, _remaining = parser.parse_known_args()

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
    app.setPalette(_build_fixed_light_palette())
    app.setStyle(FastTooltipStyle(app.style()))
    default_font = app.font()
    default_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(default_font)
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
        FIXTURE_LIBRARY_DB_PATH,
        MACHINE_CONFIGS_PATH,
        TOOL_LIBRARY_DB_PATH,
        TOOL_LIBRARY_EXE_CANDIDATES,
        TOOL_LIBRARY_MAIN_PATH,
        TOOL_LIBRARY_PROJECT_DIR,
        TOOL_LIBRARY_SERVER_NAME,
        RUNTIME_DIR,
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
            launch_python = Path(sys.executable)
            pythonw_candidate = launch_python.parent / "pythonw.exe"
            if pythonw_candidate.exists() and _is_runnable_python(pythonw_candidate):
                launch_python = pythonw_candidate
            tool_lib_process = QProcess()
            tool_lib_process.startDetached(
                str(launch_python),
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
    from services.preload_manager import get_preload_manager
    from services.print_service import PrintService
    from services.work_service import WorkService
    from ui.main_window import MainWindow
    from shared.services.machine_config_service import MachineConfigService
    from shared.services.ui_preferences_service import UiPreferencesService
    from shared.ui.theme import compile_app_stylesheet, install_application_theme_state

    _prefs_svc = UiPreferencesService(SHARED_UI_PREFERENCES_PATH, include_setup_db_path=True)
    machine_config_svc = MachineConfigService(MACHINE_CONFIGS_PATH, RUNTIME_DIR)

    # Apply the compiled shared theme at application scope before any modal
    # startup dialogs (e.g. MachineSetupWizard) are shown.
    try:
        _startup_prefs = _prefs_svc.load()
        install_application_theme_state(_startup_prefs)
        app.setStyleSheet(compile_app_stylesheet(STYLE_PATH, _startup_prefs))
    except Exception:
        pass

    # Backfill any existing configs that still have empty tools/jaws DB paths
    # (created before per-config library isolation was introduced).
    machine_config_svc.migrate_empty_db_paths(
        str(TOOL_LIBRARY_DB_PATH),
        str(JAW_LIBRARY_DB_PATH),
        str(FIXTURE_LIBRARY_DB_PATH),
    )

    # Copy all DB files into per-config folders with machine-name filenames.
    # Idempotent: safe to run on every startup.  Original files are kept.
    machine_config_svc.migrate_to_config_folders()

    # ----------------------------------------------------------------
    # Determine which Setup DB to open
    #
    # On first ever run machine_configurations.json doesn't exist yet,
    # so we fall back to the legacy DB_PATH from config.py and create
    # the migration entry afterwards once we know the profile key.
    # ----------------------------------------------------------------
    step(3, f"{loading_header}\n\n{_lt('setup_manager.loading.connect_db', 'Connecting setup database...')}")

    if machine_config_svc.is_empty():
        active_setup_db_path = str(DB_PATH)
        active_tools_db_path = str(TOOL_LIBRARY_DB_PATH)
        active_jaws_db_path = str(JAW_LIBRARY_DB_PATH)
        active_fixtures_db_path = str(FIXTURE_LIBRARY_DB_PATH)
    else:
        _active_cfg = machine_config_svc.get_active_config()
        active_setup_db_path = _active_cfg.setup_db_path or str(DB_PATH)
        active_tools_db_path = _active_cfg.tools_db_path or str(TOOL_LIBRARY_DB_PATH)
        active_jaws_db_path = _active_cfg.jaws_db_path or str(JAW_LIBRARY_DB_PATH)
        active_fixtures_db_path = _active_cfg.fixtures_db_path or str(FIXTURE_LIBRARY_DB_PATH)

    db = Database(active_setup_db_path)

    step(4, f"{loading_header}\n\n{_lt('setup_manager.loading.load_work_service', 'Loading work service...')}")
    work_service = WorkService(db)

    step(5, f"{loading_header}\n\n{_lt('setup_manager.loading.load_logbook_service', 'Loading logbook service...')}")
    logbook_service = LogbookService(db)

    step(6, f"{loading_header}\n\n{_lt('setup_manager.loading.load_drawing_service', 'Loading drawing service...')}")
    draw_service = DrawService(
        drawing_dir=DRAWINGS_DIR,
        tool_db_path=active_tools_db_path,
        jaw_db_path=active_jaws_db_path,
        fixture_db_path=active_fixtures_db_path,
    )

    preload_manager = get_preload_manager()
    preload_manager.initialize(draw_service)

    step(7, f"{loading_header}\n\n{_lt('setup_manager.loading.load_print_service', 'Loading print service...')}")
    print_service = PrintService(APP_TITLE)
    print_service.set_reference_service(draw_service)

    step(8, f"{loading_header}\n\n{_lt('setup_manager.loading.warm_preview', 'Preparing 3D preview support...')}")
    # Preview runtime ownership lives in the Tool Library process. Setup
    # Manager keeps this loading step only as part of the startup sequence.

    # ----------------------------------------------------------------
    # Machine profile bootstrap
    #
    # 1. Read the DB-bound key from app_config.
    # 2. For a fresh DB (empty key) → run the setup wizard.
    # 3. When machine configurations exist, treat the active config profile
    #    as authoritative and stamp it into the active setup DB so profile
    #    bleed cannot happen between config-specific databases.
    # 4. Mirror the key to shared_ui_preferences.json so the Tools Library
    #    can reflect it without a cross-app import.
    # 5. If this is the very first run (no machine_configurations.json),
    #    create the first named config ("NTX2500") from legacy state.
    # ----------------------------------------------------------------
    db_profile_key = work_service.get_machine_profile_key()

    if not db_profile_key:
        # Fresh database — show the setup wizard before opening the main window.
        splash.close()

        from ui.machine_setup_wizard import MachineSetupWizard

        def _wt(key: str, default: str | None = None) -> str:
            return str(_texts.get(key) or default or key)

        wizard = MachineSetupWizard(translate=_wt)
        mc_overrides: dict = {}
        if wizard.exec():
            db_profile_key = wizard.selected_profile_key()
            try:
                mc_overrides = wizard.selected_mc_overrides() or {}
            except Exception:
                mc_overrides = {}
        else:
            db_profile_key = "ntx_2sp_2h"

        work_service.set_machine_profile_key(db_profile_key)

        if mc_overrides:
            try:
                _prefs_svc.set_machining_center_overrides(
                    fourth_axis_letter=mc_overrides.get("mc_fourth_axis_letter"),
                    fifth_axis_letter=mc_overrides.get("mc_fifth_axis_letter"),
                    has_turning_option=mc_overrides.get("mc_has_turning_option"),
                )
            except Exception:
                pass

        # Re-show a minimal progress indicator for the remaining steps.
        splash.reset()
        splash.setRange(0, 10)
        splash.show()
        app.processEvents()

    # Config-specific setup DBs must follow the active machine configuration,
    # not stale DB/app prefs from a previous active config.
    if not machine_config_svc.is_empty():
        active_cfg = machine_config_svc.get_active_config()
        if active_cfg is not None:
            cfg_profile_key = str(active_cfg.machine_profile_key or "").strip().lower()
            if cfg_profile_key and cfg_profile_key != db_profile_key:
                work_service.set_machine_profile_key(cfg_profile_key)
                db_profile_key = cfg_profile_key

    # Mirror to shared prefs so Tools Library can pick it up.
    _prefs_svc.set_machine_profile_key(db_profile_key)

    # First-run migration: create the initial named configuration.
    # Pass the actual legacy DB paths so existing tool/jaw data is preserved.
    if machine_config_svc.is_empty():
        machine_config_svc.migrate_from_legacy(
            name="NTX2500",
            machine_profile_key=db_profile_key,
            setup_db_path=active_setup_db_path,
            tools_db_path=str(TOOL_LIBRARY_DB_PATH),
            jaws_db_path=str(JAW_LIBRARY_DB_PATH),
            fixtures_db_path=str(FIXTURE_LIBRARY_DB_PATH),
        )

    if ENABLE_TOOL_LIBRARY_PRELOAD:
        step(9, f"{loading_header}\n\n{_lt('setup_manager.loading.warm_tool_library', 'Tool Library warming up in background...')}")
    else:
        step(9, f"{loading_header}\n\n{_lt('setup_manager.loading.skip_preload', 'Skipping Tool Library preload...')}")

    step(10, f"{loading_header}\n\n{_lt('setup_manager.loading.open_main', 'Opening Setup Manager...')}")
    win = MainWindow(work_service, logbook_service, draw_service, print_service, machine_config_svc)
    if launch_geometry:
        _apply_frame_geometry_string(win, launch_geometry, retry_delays_ms=(0, 120))

    # ----------------------------------------------------------------
    # IPC server (lives on the QApplication, survives live switches)
    # ----------------------------------------------------------------
    server = QLocalServer(app)
    if not server.listen(SETUP_MANAGER_SERVER_NAME):
        QLocalServer.removeServer(SETUP_MANAGER_SERVER_NAME)
        server.listen(SETUP_MANAGER_SERVER_NAME)

    _last_show_request_ts = 0.0
    _last_show_geometry = ""

    def _get_active_work_editor(target_win):
        """Return the shared Work Editor dialog if one is open, or None."""
        try:
            setup_page = getattr(target_win, "setup_page", None)
            if setup_page is None:
                return None
            cache = getattr(setup_page, "_work_editor_dialog_cache", {})
            return cache.get("shared") if isinstance(cache, dict) else None
        except Exception:
            return None

    def _deliver_selector_result(target_win, payload: dict):
        """Route a selector_result IPC message from Library to the Work Editor."""
        try:
            dialog = _get_active_work_editor(target_win)
            if dialog is not None:
                ctrl = getattr(dialog, "_selector_ctrl", None)
                if ctrl is not None:
                    ctrl.receive_ipc_result(payload)
                elif hasattr(dialog, "_receive_ipc_selector_result"):
                    dialog._receive_ipc_selector_result(payload)
        except Exception:
            pass

        # Bring Work Editor (and SM main window) to the foreground immediately
        # without waiting for the follow-up "show" IPC message that Library
        # sends after this one.  Library called AllowSetForegroundWindow(-1)
        # before the handoff so SetForegroundWindow is permitted here.
        try:
            import ctypes
            dialog = _get_active_work_editor(target_win)
            if dialog is not None and dialog.isVisible():
                ctypes.windll.user32.SetForegroundWindow(int(dialog.winId()))
            else:
                target_win.raise_()
                target_win.activateWindow()
                ctypes.windll.user32.SetForegroundWindow(int(target_win.winId()))
        except Exception:
            pass

    def _restore_work_editor_if_waiting(target_win):
        """Show Work Editor if it was hidden while waiting for a selector result (cancel path)."""
        try:
            dialog = _get_active_work_editor(target_win)
            if dialog is None or dialog.isVisible():
                return
            ctrl = getattr(dialog, "_selector_ctrl", None)
            if ctrl is not None:
                ctrl.restore_if_waiting()
            elif getattr(dialog, "_pending_ipc_selector_request_id", None) is not None:
                dialog._pending_ipc_selector_request_id = None
                dialog._pending_ipc_selector_kind = None
                dialog.show()
                dialog.raise_()
                dialog.activateWindow()
        except Exception:
            pass

    def show_setup_manager(request: dict | None = None):
        nonlocal _last_show_request_ts, _last_show_geometry
        geometry_text = str((request or {}).get("geometry", "")).strip()
        now = time.monotonic()
        # Debounce duplicate show requests from fast IPC bursts.
        if (now - _last_show_request_ts) < 0.25 and geometry_text == _last_show_geometry:
            return
        _last_show_request_ts = now
        _last_show_geometry = geometry_text

        was_visible = bool(win.isVisible() and not win.isMinimized())

        def _apply_handoff_bounds():
            if geometry_text:
                return _apply_frame_geometry_string(win, geometry_text, retry_delays_ms=(0, 120, 320))
            return False

        def _do_show():
            _pending = getattr(win, "_pending_fade_in_timer", None)
            if _pending is not None:
                try:
                    _pending.stop()
                except Exception:
                    pass
                win._pending_fade_in_timer = None

            _fade_anim = getattr(win, "_fade_anim", None)
            if _fade_anim is not None:
                try:
                    _fade_anim.stop()
                except Exception:
                    pass
                win._fade_anim = None

            win.setWindowOpacity(1.0)

            if not was_visible:
                if geometry_text:
                    _apply_handoff_bounds()
                if win.isMinimized():
                    win.showNormal()
                else:
                    win.show()
            win.raise_()
            win.activateWindow()
            try:
                import ctypes
                hwnd = int(win.winId())
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            _restore_work_editor_if_waiting(win)

        _do_show()

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

            if request["command"] in {"", "show", "activate", "restore"}:
                show_setup_manager(request)
            elif request["command"] == "hide_for_library_handoff":
                win.setWindowOpacity(1.0)
                if win.isVisible():
                    win.hide()
            elif request["command"] == "selector_result":
                _deliver_selector_result(win, request)

    server.newConnection.connect(process_show_requests)

    # ----------------------------------------------------------------
    # Live configuration switch
    #
    # Triggered by MainWindow.config_switch_requested(config_id).
    # Closes the current window without quitting, re-creates all
    # services with the new config's DB paths, then opens a new window.
    # ----------------------------------------------------------------
    def _maybe_show_shared_db_notice(target_win, active_cfg) -> None:
        """Show a notice if shared DBs were changed since this config was last used.

        Respects the ``show_shared_db_notice`` preference (default False/off).
        """
        prefs = _prefs_svc.load()
        if not prefs.get("show_shared_db_notice", False):
            return

        db_attrs = [
            ("setup_db_path", "Setup DB"),
            ("tools_db_path", "Tools Library"),
            ("jaws_db_path", "Jaws Library"),
            ("fixtures_db_path", "Fixtures Library"),
        ]

        # Discover which DBs this config shares with others.
        shared: dict[str, list[str]] = {}  # label → [other config names]
        for attr, label in db_attrs:
            path = getattr(active_cfg, attr, "")
            if path:
                others = machine_config_svc.configs_sharing_path(path, exclude_id=active_cfg.id)
                if others:
                    shared[label] = [o.name for o in others]

        if not shared:
            return

        last_used = (active_cfg.last_used_at or "").strip()

        if not last_used:
            # First time opening this config — show an informational notice.
            lines = [f"<b>{active_cfg.name}</b> uses shared databases:"]
            for label, names in shared.items():
                lines.append(f"  \u2022 {label} (shared with: {', '.join(names)})")
            notice_text = "<br>".join(lines)
        else:
            # Check if any shared DB file was modified after last_used_at.
            from datetime import datetime, timezone as _tz
            try:
                last_dt = datetime.fromisoformat(last_used)
            except Exception:
                return

            changed: dict[str, list[str]] = {}
            for attr, label in db_attrs:
                if label not in shared:
                    continue
                path = getattr(active_cfg, attr, "")
                if not path:
                    continue
                try:
                    mtime = Path(path).stat().st_mtime
                    mtime_dt = datetime.fromtimestamp(mtime, tz=_tz.utc)
                    if mtime_dt > last_dt:
                        changed[label] = shared[label]
                except Exception:
                    pass

            if not changed:
                return

            lines = [f"Shared databases were modified since <b>{active_cfg.name}</b> was last used:"]
            for label, names in changed.items():
                lines.append(f"  \u2022 {label} (possibly by: {', '.join(names)})")
            notice_text = "<br>".join(lines)

        from PySide6.QtWidgets import QDialog as _QDialog, QVBoxLayout as _QVL, QLabel as _QL, QHBoxLayout as _QHL, QPushButton as _QPB, QCheckBox as _QCB
        dlg = _QDialog(target_win)
        dlg.setWindowTitle("Shared Database Notice")
        dlg.setModal(True)
        dlg.resize(420, 180)
        vl = _QVL(dlg)
        vl.setContentsMargins(16, 14, 16, 14)
        vl.setSpacing(10)
        lbl = _QL()
        lbl.setTextFormat(Qt.RichText)
        lbl.setText(notice_text)
        lbl.setWordWrap(True)
        vl.addWidget(lbl)
        cb = _QCB("Don't show these notices")
        cb.setChecked(False)
        vl.addWidget(cb)
        hl = _QHL()
        hl.addStretch(1)
        ok_btn = _QPB("OK")
        ok_btn.setProperty("panelActionButton", True)
        ok_btn.setProperty("primaryAction", True)
        ok_btn.clicked.connect(dlg.accept)
        hl.addWidget(ok_btn)
        vl.addLayout(hl)
        dlg.exec()

        if cb.isChecked():
            p = _prefs_svc.load()
            p["show_shared_db_notice"] = False
            _prefs_svc.save(p)

    def _do_live_switch(new_config_id: str) -> None:
        nonlocal win, work_service, logbook_service, draw_service

        # Stamp last_used_at on the config we are LEAVING so we can later detect
        # changes that happened while another config was active.
        old_active_id = machine_config_svc.get_active_config_id()
        if old_active_id and old_active_id != new_config_id:
            machine_config_svc.update_last_used(old_active_id)

        machine_config_svc.set_active_config_id(new_config_id)
        active = machine_config_svc.get_active_config()
        if active is None:
            return

        new_setup_db = active.setup_db_path or str(DB_PATH)
        new_tools_db = active.tools_db_path or str(TOOL_LIBRARY_DB_PATH)
        new_jaws_db = active.jaws_db_path or str(JAW_LIBRARY_DB_PATH)
        new_fixtures_db = active.fixtures_db_path or str(FIXTURE_LIBRARY_DB_PATH)

        # Close old window without triggering app.quit().
        win._suppress_quit = True
        win.close()
        win.deleteLater()

        # Show a brief wait cursor while services reinitialise.
        from PySide6.QtWidgets import QApplication as _QApp
        from PySide6.QtCore import Qt as _Qt
        _QApp.setOverrideCursor(_Qt.WaitCursor)
        try:
            new_db = Database(new_setup_db)
            new_work_service = WorkService(new_db)
            new_logbook_service = LogbookService(new_db)
            new_draw_service = DrawService(
                drawing_dir=DRAWINGS_DIR,
                tool_db_path=new_tools_db,
                jaw_db_path=new_jaws_db,
                fixture_db_path=new_fixtures_db,
            )
            print_service.set_reference_service(new_draw_service)
            preload_manager.refresh(new_draw_service)

            # Config profile is authoritative for this setup DB; write it to
            # the DB immediately so Work Editor always reads the right profile
            # for the active machine config.
            new_work_service.set_machine_profile_key(active.machine_profile_key)

            # Mirror new profile key to shared prefs.
            _prefs_svc.set_machine_profile_key(active.machine_profile_key)
        finally:
            _QApp.restoreOverrideCursor()

        new_win = MainWindow(
            new_work_service, new_logbook_service, new_draw_service,
            print_service, machine_config_svc,
        )
        new_win.config_switch_requested.connect(_do_live_switch)

        # Restore geometry from the previous window's DB directory if available.
        prev_geom_file = Path(new_setup_db).parent / ".window_geometry"
        restore_geom = ""
        if prev_geom_file.exists():
            try:
                restore_geom = prev_geom_file.read_text().strip()
            except Exception:
                restore_geom = ""
        if restore_geom:
            _apply_frame_geometry_string(new_win, restore_geom, retry_delays_ms=(0, 120))

        new_win.show()
        new_win.raise_()
        new_win.activateWindow()
        try:
            import ctypes as _ct
            _ct.windll.user32.SetForegroundWindow(int(new_win.winId()))
        except Exception:
            pass

        # Silently notify the running Tool Library (if any) to switch to the
        # new config's databases immediately, without showing its window.
        try:
            from ui.main_window_support.library_ipc import send_to_tool_library
            send_to_tool_library(TOOL_LIBRARY_SERVER_NAME, {
                "show": False,
                "tools_db_path": new_tools_db,
                "jaws_db_path": new_jaws_db,
                "fixtures_db_path": new_fixtures_db,
            })
        except Exception:
            pass

        # Update nonlocals so the IPC show_setup_manager closure uses the new window.
        win = new_win
        work_service = new_work_service
        logbook_service = new_logbook_service
        draw_service = new_draw_service

        # Shared-DB notice: delay slightly so the window is fully painted first.
        _active_snap = active  # capture for closure
        QTimer.singleShot(500, lambda: _maybe_show_shared_db_notice(win, _active_snap))

    win.config_switch_requested.connect(_do_live_switch)

    # Close splash before showing main window — an application-modal splash
    # blocks repaint of the main window and causes a visible startup glitch.
    splash.close()

    win.show()
    win.raise_()
    win.activateWindow()

    # Shared-DB notice on initial startup for the active config.
    _startup_cfg = machine_config_svc.get_active_config()
    if _startup_cfg is not None:
        QTimer.singleShot(800, lambda: _maybe_show_shared_db_notice(win, _startup_cfg))

    def _cleanup_server():
        QLocalServer.removeServer(SETUP_MANAGER_SERVER_NAME)

    def _request_tool_library_shutdown():
        try:
            sock = QLocalSocket()
            sock.connectToServer(TOOL_LIBRARY_SERVER_NAME)
            if not sock.waitForConnected(200):
                return
            sock.write(json.dumps({"command": "shutdown"}).encode("utf-8"))
            sock.flush()
            sock.waitForBytesWritten(200)
        except Exception:
            pass
        finally:
            try:
                sock.disconnectFromServer()
            except Exception:
                pass

    app.aboutToQuit.connect(_request_tool_library_shutdown)
    app.aboutToQuit.connect(_cleanup_server)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

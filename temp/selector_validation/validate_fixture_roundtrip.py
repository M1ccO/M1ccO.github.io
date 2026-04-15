from __future__ import annotations

import importlib.util
import json
import sys
import traceback
import uuid
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[2]
TOOL_LIB_ROOT = ROOT / 'Tools and jaws Library'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOL_LIB_ROOT))


def _load_bridge_class():
    bridge_path = ROOT / 'Setup Manager' / 'ui' / 'work_editor_support' / 'bridge.py'
    spec = importlib.util.spec_from_file_location('setup_bridge_validation', bridge_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.SelectorSessionBridge


def main() -> int:
    from data.database import Database
    from data.fixture_database import FixtureDatabase
    from data.jaw_database import JawDatabase
    from services.export_service import ExportService
    from services.fixture_service import FixtureService
    from services.jaw_service import JawService
    from services.settings_service import SettingsService
    from services.tool_service import ToolService
    from ui.main_window import MainWindow

    SelectorSessionBridge = _load_bridge_class()

    runtime_dir = ROOT / 'temp' / 'selector_validation' / 'runtime'
    runtime_dir.mkdir(parents=True, exist_ok=True)
    result_path = runtime_dir / 'result.json'

    tools_db_path = runtime_dir / 'tools.db'
    jaws_db_path = runtime_dir / 'jaws.db'
    fixtures_db_path = runtime_dir / 'fixtures.db'
    settings_path = runtime_dir / 'settings.json'

    for file_path in (tools_db_path, jaws_db_path, fixtures_db_path, settings_path):
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    if result_path.exists():
        result_path.unlink()
    stage = {'value': 'starting'}

    def write_stage(name: str) -> None:
        stage['value'] = name
        result_path.write_text(
            json.dumps({'status': 'starting', 'harness_version': 2, 'stage': stage['value']}, ensure_ascii=True, sort_keys=True, indent=2),
            encoding='utf-8',
        )

    write_stage('before_qapplication')
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    write_stage('after_qapplication')

    tool_db = Database(tools_db_path)
    jaw_db = JawDatabase(jaws_db_path)
    fixture_db = FixtureDatabase(fixtures_db_path)
    write_stage('after_databases')

    tool_service = ToolService(tool_db)
    jaw_service = JawService(jaw_db)
    fixture_service = FixtureService(fixture_db)
    settings_service = SettingsService(settings_path)
    export_service = ExportService()
    write_stage('after_services')

    fixture_service.save_fixture(
        {
            'fixture_id': 'FIX-VALID-01',
            'fixture_kind': 'Part',
            'fixture_type': 'Test Fixture',
            'clamping_diameter_text': '40',
            'clamping_length': '10',
            'used_in_work': '',
            'turning_washer': '',
            'last_modified': '2026-04-15',
            'notes': 'selector validation fixture',
            'stl_path': '',
            'assembly_part_ids': [],
        }
    )

    win = MainWindow(tool_service, jaw_service, fixture_service, export_service, settings_service)
    write_stage('after_main_window')

    write_stage('after_request_server')

    received: dict = {}
    errors: list[tuple[str, str]] = []
    state = {'finished': False}
    trace: list[str] = []

    def cleanup() -> None:
        try:
            bridge.shutdown()
        except Exception:
            pass
        try:
            win.close()
        except Exception:
            pass
        app.processEvents()

    def succeed() -> None:
        if state['finished']:
            return
        state['finished'] = True
        result_path.write_text(
            json.dumps({'status': 'ok', 'received': received, 'warnings': errors, 'trace': trace}, ensure_ascii=True, sort_keys=True, indent=2),
            encoding='utf-8',
        )
        print('fixture_selector_roundtrip_ok')
        print(json.dumps(received, ensure_ascii=True, sort_keys=True))
        cleanup()
        app.exit(0)

    def fail(message: str) -> None:
        if state['finished']:
            return
        state['finished'] = True
        result_path.write_text(
            json.dumps({'status': 'failed', 'message': message, 'received': received, 'warnings': errors, 'trace': trace}, ensure_ascii=True, sort_keys=True, indent=2),
            encoding='utf-8',
        )
        print(f'fixture_selector_roundtrip_failed: {message}')
        if errors:
            print(json.dumps({'warnings': errors}, ensure_ascii=True, sort_keys=True))
        cleanup()
        app.exit(1)

    def show_warning(title: str, body: str) -> None:
        errors.append((title, body))

    def apply_fixture_result(request: dict, selected_items: list[dict]) -> bool:
        trace.append('fixture_callback_received')
        received['request'] = dict(request)
        received['selected_items'] = [dict(item) for item in selected_items]
        target_key = str(request.get('target_key') or '').strip()
        fixture_id = str((selected_items[0] if selected_items else {}).get('fixture_id') or '').strip()
        if target_key != 'OP10':
            fail(f'unexpected target_key: {target_key!r}')
            return False
        if fixture_id != 'FIX-VALID-01':
            fail(f'unexpected fixture_id: {fixture_id!r}')
            return False
        if errors:
            fail(f'unexpected warnings: {errors!r}')
            return False
        QTimer.singleShot(0, succeed)
        return True

    bridge = SelectorSessionBridge(
        translate=lambda _key, default=None, **_kwargs: default or '',
        show_warning=show_warning,
        normalize_head=lambda value: str(value or '').strip().upper(),
        normalize_spindle=lambda value: str(value or '').strip().lower(),
        default_spindle=lambda: 'main',
        initial_tool_assignment_buckets=lambda: {},
        apply_tool_result=lambda request, selected_items: True,
        apply_jaw_result=lambda request, selected_items: True,
        apply_fixture_result=apply_fixture_result,
        open_jaw_selector=lambda spindle=None: True,
        tool_library_server_name='unused',
        tool_library_main_path=TOOL_LIB_ROOT / 'main.py',
        tool_library_project_dir=TOOL_LIB_ROOT,
        tool_library_exe_candidates=[],
        tools_db_path=str(tools_db_path),
        jaws_db_path=str(jaws_db_path),
    )
    write_stage('after_bridge')

    if not bridge.ensure_server():
        fail('callback server unavailable')
        return app.exec()

    request_id = uuid.uuid4().hex
    bridge._pending_requests[request_id] = {
        'request_id': request_id,
        'kind': 'fixtures',
        'head': '',
        'spindle': 'main',
        'target_key': 'OP10',
        'follow_up': {'target_key': 'OP10'},
    }
    trace.append('pending_request_created')

    payload = {
        'show': True,
        'module': 'fixtures',
        'selector_mode': 'fixtures',
        'selector_callback_server': bridge._callback_server_name,
        'selector_request_id': request_id,
        'tools_db_path': str(tools_db_path),
        'jaws_db_path': str(jaws_db_path),
        'current_assignments': [],
    }
    win.apply_external_request(payload)
    trace.append('external_request_applied')
    trace.append(f"selector_mode={getattr(win, '_selector_mode', '')}")

    loop = QEventLoop()

    def _wait_for(predicate, label: str, timeout_ms: int = 6000):
        result = {'ok': False}

        def _tick():
            if predicate():
                result['ok'] = True
                loop.quit()
                return
            QTimer.singleShot(25, _tick)

        QTimer.singleShot(0, _tick)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        if not result['ok']:
            fail(f'timeout waiting for {label}')
            return False
        return True

    def wait_for_dialog() -> None:
        dialog = getattr(win, '_fixture_selector_dialog', None)
        if dialog is None and not _wait_for(lambda: getattr(win, '_fixture_selector_dialog', None) is not None, 'fixture selector dialog'):
            return
        dialog = getattr(win, '_fixture_selector_dialog', None)
        trace.append('fixture_selector_dialog_opened')
        wait_for_catalog(dialog)

    def wait_for_catalog(dialog) -> None:
        if not _wait_for(lambda: dialog.catalog_list.count() > 0, 'fixture selector catalog'):
            return
        trace.append(f'fixture_catalog_count={dialog.catalog_list.count()}')
        submit_selection(dialog)

    def submit_selection(dialog) -> None:
        item = dialog.catalog_list.item(0)
        if item is None:
            fail('no selectable fixture row found')
            return
        trace.append('submitting_fixture_selection')
        item.setSelected(True)
        dialog._add_current_selection()
        dialog._send_selector_selection()
        if not _wait_for(lambda: 'selected_items' in received, 'fixture callback payload'):
            return
        succeed()

    write_stage('after_open_session')

    QTimer.singleShot(0, wait_for_dialog)
    QTimer.singleShot(12000, lambda: fail('validation timed out'))
    write_stage('before_app_exec')
    return app.exec()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        failure_path = ROOT / 'temp' / 'selector_validation' / 'runtime' / 'unhandled_exception.txt'
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(traceback.format_exc(), encoding='utf-8')
        raise
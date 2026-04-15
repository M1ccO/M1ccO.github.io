import logging
import os
import shutil
import sys
from pathlib import Path

APP_TITLE = 'Tools and jaws Library'

SOURCE_DIR = Path(__file__).resolve().parent
IS_FROZEN = getattr(sys, 'frozen', False)

# DEV_MODE is True when running from source; False in a PyInstaller frozen build.
DEV_MODE = not IS_FROZEN
APP_DIR = Path(getattr(sys, '_MEIPASS', SOURCE_DIR))
STYLE_PATH = APP_DIR / 'styles' / 'library_style.qss'
PREVIEW_DIR = APP_DIR / 'preview'

ASSETS_DIR = APP_DIR / 'assets'
TOOL_ICONS_DIR = ASSETS_DIR / 'icons' / 'tools'

if IS_FROZEN:
    local_appdata = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
    USER_DATA_DIR = local_appdata / APP_TITLE
    DB_DIR = USER_DATA_DIR / 'databases'
    SETTINGS_PATH = USER_DATA_DIR / 'library_settings.json'
    EXPORT_DEFAULT_PATH = USER_DATA_DIR / 'tool_library_export.xlsx'
else:
    USER_DATA_DIR = SOURCE_DIR
    DB_DIR = SOURCE_DIR / 'databases'
    SETTINGS_PATH = SOURCE_DIR / 'library_settings.json'
    EXPORT_DEFAULT_PATH = SOURCE_DIR / 'tool_library_export.xlsx'

DB_DIR.mkdir(parents=True, exist_ok=True)

# --- Logging -----------------------------------------------------------------
def _configure_logging() -> None:
    log_level = logging.DEBUG if DEV_MODE else logging.WARNING
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_path = USER_DATA_DIR / 'app.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding='utf-8'))
    except OSError:
        pass
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        handlers=handlers,
        force=True,
    )

_configure_logging()
# -----------------------------------------------------------------------------

PROJECTS_DIR = SOURCE_DIR.parent
_projects_dir = str(PROJECTS_DIR)
if _projects_dir not in sys.path:
    sys.path.insert(0, _projects_dir)

if IS_FROZEN:
    _models_base_dir = local_appdata / 'Tools and jaws Library' / 'assets' / '3d'
else:
    _models_base_dir = PROJECTS_DIR / 'Tools and jaws Library' / 'assets' / '3d'
TOOL_MODELS_ROOT_DEFAULT = _models_base_dir / 'tools'
JAW_MODELS_ROOT_DEFAULT = _models_base_dir / 'jaws'
TOOL_MODELS_ROOT_DEFAULT.mkdir(parents=True, exist_ok=True)
JAW_MODELS_ROOT_DEFAULT.mkdir(parents=True, exist_ok=True)


def _resolve_runtime_dir() -> Path:
    if not IS_FROZEN:
        return SOURCE_DIR.parent / '.runtime'

    runtime_dir = local_appdata / 'Shared Runtime'
    runtime_dir.mkdir(parents=True, exist_ok=True)

    return runtime_dir


RUNTIME_DIR = _resolve_runtime_dir()
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
SHARED_UI_PREFERENCES_PATH = RUNTIME_DIR / 'shared_ui_preferences.json'
TOOL_LIBRARY_READY_PATH = RUNTIME_DIR / 'tool_library.ready'
TOOL_LIBRARY_SHOW_REQUEST_PATH = RUNTIME_DIR / 'tool_library.show'
TOOL_LIBRARY_SERVER_NAME = 'tool_library_single_instance'
SETUP_MANAGER_SERVER_NAME = 'setup_manager_single_instance'


def _resolve_active_library_db_paths() -> tuple[Path, Path]:
    """Return (tools_db, jaws_db) from the active machine config if available.

    Falls back to the local ``databases/`` files so the app can still start
    standalone when no machine config has been created yet.
    """
    _default_tools = DB_DIR / 'tool_library.db'
    _default_jaws  = DB_DIR / 'jaws_library.db'
    try:
        import json as _json
        _config_json = RUNTIME_DIR / 'machine_configurations.json'
        if _config_json.exists():
            _data = _json.loads(_config_json.read_text(encoding='utf-8'))
            _active_id = str(_data.get('active_config_id') or '')
            for _entry in _data.get('configurations', []):
                if str(_entry.get('id') or '') == _active_id:
                    _tools = str(_entry.get('tools_db_path') or '').strip()
                    _jaws  = str(_entry.get('jaws_db_path') or '').strip()
                    if _tools and _jaws:
                        return Path(_tools), Path(_jaws)
    except Exception:
        pass
    return _default_tools, _default_jaws


DB_PATH, JAWS_DB_PATH = _resolve_active_library_db_paths()
I18N_DIR = APP_DIR / 'i18n'
if not I18N_DIR.exists():
    I18N_DIR = SOURCE_DIR / 'i18n'

# Shared UI sizing constants for dropdown controls.
EDITOR_DROPDOWN_WIDTH = 250
RAIL_HEAD_DROPDOWN_WIDTH = 86


def _seed_frozen_database():
    if not IS_FROZEN or DB_PATH.exists():
        return

    bundled_db = APP_DIR / 'databases' / 'tool_library.db'
    if bundled_db.exists():
        shutil.copy2(bundled_db, DB_PATH)


_seed_frozen_database()

TURNING_TOOL_TYPES = [
    'O.D Turning',
    'I.D Turning',
    'O.D Groove',
    'I.D Groove',
    'Face Groove',
    'O.D Thread',
    'I.D Thread',
    'Turn Thread',
    'Turn Drill',
    'Turn Spot Drill',
]

MILLING_TOOL_TYPES = [
    'Drill',
    'Spot Drill',
    'Tapping',
    'Reamer',
    'Boring',
    'Chamfer',
    'Face Mill',
    'Side Mill',
    'Endmill',
    'Slotting',
    'Custom',
    'Sensor',
]

ALL_TOOL_TYPES = TURNING_TOOL_TYPES + MILLING_TOOL_TYPES

TOOL_TYPE_TO_ICON = {
    'O.D Turning': 'od_turning.png',
    'I.D Turning': 'id_turning.png',
    'O.D Groove': 'od_groove.png',
    'I.D Groove': 'id_groove.png',
    'Face Groove': 'face_groove.png',
    'O.D Thread': 'od_thread.png',
    'I.D Thread': 'id_thread.png',
    'Turn Thread': 'turn_thread.png',
    'Turn Drill': 'turn_drill.png',
    'Turn Spot Drill': 'turn_spot_drill.png',
    'Drill': 'drill.png',
    'Spot Drill': 'spot_drill.png',
    'Tapping': 'tapping.png',
    'Reamer': 'reamer.png',
    'Boring': 'boring.png',
    'Chamfer': 'chamfer.png',
    'Face Mill': 'face_mill.png',
    'Side Mill': 'side_mill.png',
    'Endmill': 'endmill.png',
    'Slotting': 'slotting.png',
    'Custom': 'custom.png',
    'Sensor': 'sensor.png',
}
DEFAULT_TOOL_ICON = 'default.png'

NAV_ITEM_TO_ICON = {
    'TOOLS': 'library.svg',
    'JAWS': 'jaw_icon.png',
    'ASSEMBLIES': 'assemblies_icon.svg',
    'HOLDERS': 'holders_icon.svg',
    'INSERTS': 'inserts_icon.svg',
    'EXPORT': 'import_export.svg',
}

NAV_ICON_DEFAULT_SIZE = (30, 30)
NAV_ICON_RENDER_OVERRIDES = {}


import os
import shutil
import sys
from pathlib import Path

APP_TITLE = "Setup Manager"

SOURCE_DIR = Path(__file__).resolve().parent
IS_FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
PROJECTS_DIR = SOURCE_DIR.parent
PREVIEW_DIR = APP_DIR / "preview"
ASSETS_DIR = APP_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
STYLE_PATH = APP_DIR / "styles" / "setup_manager_style.qss"


def _first_existing_path(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _first_existing_dir(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return candidates[0]

if IS_FROZEN:
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    USER_DATA_DIR = local_appdata / APP_TITLE
    DB_DIR = USER_DATA_DIR / "databases"
    DRAWINGS_DIR = USER_DATA_DIR / "drawings"
    TEMP_DIR = USER_DATA_DIR / "temp"
    TOOL_LIBRARY_USER_DB_DIR = local_appdata / "Tools and jaws Library" / "databases"
    TOOL_LIBRARY_INSTALL_DIR = local_appdata / "Programs" / "Tools and jaws Library"
    exe_dir = Path(sys.executable).resolve().parent
    dist_dir = exe_dir.parent
    setup_project_dir = dist_dir.parent
    workspace_root_dir = setup_project_dir.parent
    SIBLING_PROJECTS_DIR = _first_existing_dir(
        workspace_root_dir,
        setup_project_dir,
        dist_dir,
    )
else:
    USER_DATA_DIR = SOURCE_DIR
    DB_DIR = SOURCE_DIR / "databases"
    DRAWINGS_DIR = SOURCE_DIR / "drawings"
    TEMP_DIR = SOURCE_DIR / "temp"
    TOOL_LIBRARY_USER_DB_DIR = PROJECTS_DIR / "Tools and jaws Library" / "databases"
    TOOL_LIBRARY_INSTALL_DIR = PROJECTS_DIR / "Tools and jaws Library"
    SIBLING_PROJECTS_DIR = PROJECTS_DIR

DB_DIR.mkdir(parents=True, exist_ok=True)
DRAWINGS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
_shared_dir = str(PROJECTS_DIR / 'shared')
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

if IS_FROZEN:
    _models_base_dir = local_appdata / "Tools and jaws Library" / "assets" / "3d"
else:
    _models_base_dir = PROJECTS_DIR / "Tools and jaws Library" / "assets" / "3d"
TOOL_MODELS_ROOT_DEFAULT = _models_base_dir / "tools"
JAW_MODELS_ROOT_DEFAULT = _models_base_dir / "jaws"
TOOL_MODELS_ROOT_DEFAULT.mkdir(parents=True, exist_ok=True)
JAW_MODELS_ROOT_DEFAULT.mkdir(parents=True, exist_ok=True)


def _seed_frozen_databases():
    """Copy bundled DB snapshots to user-data directory on first frozen run."""
    if not IS_FROZEN:
        return
    bundled_db_dir = APP_DIR / "databases"
    if not bundled_db_dir.exists():
        return
    for name in ("setup_manager.db", "tool_library.db", "jaws_library.db"):
        target = DB_DIR / name
        source = bundled_db_dir / name
        if target.exists() or not source.exists():
            continue
        try:
            shutil.copy2(source, target)
        except Exception:
            # If copy fails, runtime will continue and show missing DB state.
            pass


_seed_frozen_databases()


def _resolve_runtime_dir() -> Path:
    if not IS_FROZEN:
        return PROJECTS_DIR / ".runtime"

    runtime_dir = local_appdata / "Shared Runtime"
    legacy_runtime_dir = local_appdata / "NTX Shared Runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    legacy_prefs = legacy_runtime_dir / "shared_ui_preferences.json"
    current_prefs = runtime_dir / "shared_ui_preferences.json"
    if legacy_prefs.exists() and not current_prefs.exists():
        try:
            shutil.copy2(legacy_prefs, current_prefs)
        except Exception:
            pass

    return runtime_dir


RUNTIME_DIR = _resolve_runtime_dir()
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
SHARED_UI_PREFERENCES_PATH = RUNTIME_DIR / "shared_ui_preferences.json"
I18N_DIR = APP_DIR / "i18n"
if not I18N_DIR.exists():
    I18N_DIR = SOURCE_DIR / "i18n"

if IS_FROZEN:
    source_like_db = SOURCE_DIR.parent / "databases" / "setup_manager.db"
    workspace_like_db = SOURCE_DIR.parent.parent / "Setup Manager" / "databases" / "setup_manager.db"
    DB_PATH = _first_existing_path(
        source_like_db,
        workspace_like_db,
        DB_DIR / "setup_manager.db",
    )
else:
    DB_PATH = DB_DIR / "setup_manager.db"
TOOL_LIBRARY_PROJECT_DIR = _first_existing_dir(
    SIBLING_PROJECTS_DIR / "Tools and jaws Library",
    SOURCE_DIR.parent / "Tools and jaws Library",
    Path(sys.executable).resolve().parent.parent / "Tools and jaws Library" if IS_FROZEN else SOURCE_DIR.parent / "Tools and jaws Library",
)
TOOL_LIBRARY_MAIN_PATH = _first_existing_path(
    TOOL_LIBRARY_PROJECT_DIR / "main.py",
    SOURCE_DIR.parent / "Tools and jaws Library" / "main.py",
)
TOOL_LIBRARY_SERVER_NAME = "tool_library_single_instance"
SETUP_MANAGER_SERVER_NAME = "setup_manager_single_instance"
TOOL_LIBRARY_EXE_CANDIDATES = [
    SIBLING_PROJECTS_DIR / "Tools and jaws Library" / "dist" / "Tools and jaws Library" / "Tools and jaws Library.exe",
    SOURCE_DIR.parent / "Tools and jaws Library" / "dist" / "Tools and jaws Library" / "Tools and jaws Library.exe",
    Path(sys.executable).resolve().parent.parent / "Tools and jaws Library" / "Tools and jaws Library.exe" if IS_FROZEN else SOURCE_DIR.parent / "Tools and jaws Library" / "Tools and jaws Library.exe",
    TOOL_LIBRARY_PROJECT_DIR / "dist" / "Tools and jaws Library" / "Tools and jaws Library.exe",
    TOOL_LIBRARY_INSTALL_DIR / "Tools and jaws Library.exe",
]

# Tool icon lookup is shared with Tool Library. Setup Manager may keep only a
# reduced icon set, so we allow fallback to Tool Library's icon directory.
TOOL_ICONS_DIR = ICONS_DIR / "tools"
TOOL_LIBRARY_TOOL_ICONS_DIR = TOOL_LIBRARY_PROJECT_DIR / "assets" / "icons" / "tools"

TOOL_TYPE_TO_ICON = {
    "O.D Turning": "od_turning.png",
    "I.D Turning": "id_turning.png",
    "O.D Groove": "od_groove.png",
    "I.D Groove": "id_groove.png",
    "Face Groove": "face_groove.png",
    "O.D Thread": "od_thread.png",
    "I.D Thread": "id_thread.png",
    "Turn Thread": "turn_thread.png",
    "Turn Drill": "turn_drill.png",
    "Turn Spot Drill": "turn_spot_drill.png",
    "Drill": "drill.png",
    "Spot Drill": "spot_drill.png",
    "Tapping": "tapping.png",
    "Reamer": "reamer.png",
    "Boring": "boring.png",
    "Chamfer": "chamfer.png",
    "Face Mill": "face_mill.png",
    "Side Mill": "side_mill.png",
    "Endmill": "endmill.png",
    "Slotting": "slotting.png",
    "Custom": "custom.png",
    "Sensor": "sensor.png",
}
DEFAULT_TOOL_ICON = "default.png"
TOOL_LIBRARY_DB_PATH = _first_existing_path(
    TOOL_LIBRARY_PROJECT_DIR / "databases" / "tool_library.db",
    TOOL_LIBRARY_USER_DB_DIR / "tool_library.db",
    DB_DIR / "tool_library.db",
)
JAW_LIBRARY_DB_PATH = _first_existing_path(
    TOOL_LIBRARY_PROJECT_DIR / "databases" / "jaws_library.db",
    TOOL_LIBRARY_USER_DB_DIR / "jaws_library.db",
    DB_DIR / "jaws_library.db",
)

NAV_ITEMS = ["SETUPS", "DRAWINGS", "LOGBOOK"]

# Keep cross-app launch explicit during active development. This avoids risky
# background/preload behavior while the standalone packaging paths are still in flux.
ENABLE_TOOL_LIBRARY_PRELOAD = True

JAW_TYPES = ["Soft jaws", "Hard jaws", "Spiked jaws", "Special jaws"]
SPINDLE_SIDES = ["SP1", "SP2", "Both"]

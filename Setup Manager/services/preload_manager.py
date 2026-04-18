"""App-level preload manager.

Per WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md (CODE PATH INDEX +
PRELOAD RULES): owns warm services, database handles, and resolver
registration. Does NOT own widgets, selector windows, or scene geometry.

Lifecycle:
- `initialize(draw_service)` at startup: opens library DBs, constructs
  tool/jaw services, builds LibraryBacked resolvers, registers them via
  `shared.ui.resolvers.set_resolver`.
- `refresh(draw_service)` on live DB swap (e.g. machine config switch):
  closes current handles, rebuilds services + resolvers, re-registers.
- `shutdown()` on app exit: clears registry + drops handles.

Preload is best-effort. If library modules cannot be imported the
manager logs and continues; resolver registry stays unconfigured and
any caller attempting `get_resolver` gets a clear error.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from shared.ui.resolvers import (
    LibraryBackedJawResolver,
    LibraryBackedToolResolver,
    set_resolver,
)

_log = logging.getLogger(__name__)

_InvalidationListener = Callable[[str, tuple[str, ...]], None]


class PreloadManager:
    def __init__(self) -> None:
        self._tool_db: Any = None
        self._jaw_db: Any = None
        self._fixture_db: Any = None
        self._tool_service: Any = None
        self._jaw_service: Any = None
        self._fixture_service: Any = None
        self._tool_resolver: LibraryBackedToolResolver | None = None
        self._jaw_resolver: LibraryBackedJawResolver | None = None
        self._preview_warmup_widget: Any = None
        self._preview_warmup_armed: bool = False
        self._initialized: bool = False
        self._listeners: list[_InvalidationListener] = []

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def tool_service(self) -> Any:
        return self._tool_service

    @property
    def jaw_service(self) -> Any:
        return self._jaw_service

    @property
    def fixture_service(self) -> Any:
        return self._fixture_service

    @property
    def tool_resolver(self) -> LibraryBackedToolResolver | None:
        return self._tool_resolver

    @property
    def jaw_resolver(self) -> LibraryBackedJawResolver | None:
        return self._jaw_resolver

    def initialize(self, draw_service: Any) -> bool:
        return self._build_from_draw_service(draw_service)

    def refresh(self, draw_service: Any) -> bool:
        self._close_handles()
        return self._build_from_draw_service(draw_service)

    def bump_revisions(self) -> None:
        """Signal that library data changed; invalidates resolver caches."""
        if self._tool_resolver is not None:
            self._tool_resolver.bump_revision()
        if self._jaw_resolver is not None:
            self._jaw_resolver.bump_revision()
        self._emit("all", ())

    def invalidate(self, kind: str, ids: Iterable[str] | None = None) -> None:
        """Invalidate cached entries for a specific kind + id set.

        kind: "tool", "jaw", or "all". When ids is None or empty, falls
        back to a full bump for that kind. Listeners receive the same
        (kind, ids) tuple after cache mutation completes.
        """
        id_tuple: tuple[str, ...] = tuple(i for i in (ids or ()) if isinstance(i, str) and i)

        if kind == "tool":
            if self._tool_resolver is None:
                self._emit(kind, id_tuple)
                return
            if not id_tuple:
                self._tool_resolver.bump_revision()
            else:
                for tool_id in id_tuple:
                    self._tool_resolver.invalidate_tool(tool_id)
            self._emit(kind, id_tuple)
            return

        if kind == "jaw":
            if self._jaw_resolver is None:
                self._emit(kind, id_tuple)
                return
            if not id_tuple:
                self._jaw_resolver.bump_revision()
            else:
                for jaw_id in id_tuple:
                    self._jaw_resolver.invalidate_jaw(jaw_id)
            self._emit(kind, id_tuple)
            return

        if kind == "all":
            self.bump_revisions()
            return

        raise ValueError(f"unknown invalidation kind: {kind!r}")

    def add_listener(self, listener: _InvalidationListener) -> None:
        if not callable(listener):
            raise TypeError("listener must be callable")
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: _InvalidationListener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def _emit(self, kind: str, ids: tuple[str, ...]) -> None:
        for listener in list(self._listeners):
            try:
                listener(kind, ids)
            except Exception:
                _log.debug("invalidation listener raised", exc_info=True)

    def shutdown(self) -> None:
        set_resolver("tool", None)
        set_resolver("jaw", None)
        self._dispose_preview_warmup()
        self._close_handles()
        self._initialized = False

    def _build_from_draw_service(self, draw_service: Any) -> bool:
        if draw_service is None:
            _log.warning("PreloadManager.initialize: draw_service is None; skipping")
            return False

        try:
            (
                Database,
                FixtureDatabase,
                JawDatabase,
                FixtureService,
                JawService,
                ToolService,
            ) = _import_library_runtime_types()
        except Exception:
            _log.exception("PreloadManager: library imports failed; resolvers will not be registered")
            return False

        try:
            tool_db_path = Path(getattr(draw_service, "tool_db_path"))
            jaw_db_path = Path(getattr(draw_service, "jaw_db_path"))
            fixture_db_path = Path(getattr(draw_service, "fixture_db_path", jaw_db_path))
        except Exception:
            _log.exception("PreloadManager: draw_service missing tool/jaw db paths")
            return False

        try:
            self._tool_db = Database(tool_db_path)
            self._jaw_db = JawDatabase(jaw_db_path)
            self._fixture_db = FixtureDatabase(fixture_db_path)
        except Exception:
            _log.exception("PreloadManager: failed to open library databases")
            self._close_handles()
            return False

        try:
            self._tool_service = ToolService(self._tool_db)
            self._jaw_service = JawService(self._jaw_db)
            self._fixture_service = FixtureService(self._fixture_db)
        except Exception:
            _log.exception("PreloadManager: failed to construct library services")
            self._close_handles()
            return False

        try:
            self._tool_resolver = LibraryBackedToolResolver(self._tool_service)
            self._jaw_resolver = LibraryBackedJawResolver(self._jaw_service)
            set_resolver("tool", self._tool_resolver)
            set_resolver("jaw", self._jaw_resolver)
        except Exception:
            _log.exception("PreloadManager: failed to register resolvers")
            self._close_handles()
            return False

        self._initialized = True
        self._warm_preview_engine()
        _log.info(
            "PreloadManager ready: tool_db=%s jaw_db=%s",
            tool_db_path,
            jaw_db_path,
        )
        return True

    def _warm_preview_engine(self) -> None:
        """Pre-initialize shared STL preview runtime once at app preload.

        This warms OpenGL/context setup so first selector/library preview
        open is less likely to trigger visible mount/rebuild churn.
        """
        if self._preview_warmup_armed:
            return
        app = QApplication.instance()
        if app is None:
            return
        try:
            from shared.ui.stl_preview import StlPreviewWidget
        except Exception:
            _log.debug("PreloadManager: STL preview import failed", exc_info=True)
            return
        if StlPreviewWidget is None:
            return
        try:
            warmup = StlPreviewWidget()
            hint = (
                "Rotate: left mouse | Pan: right mouse | Zoom: mouse wheel"
            )
            set_hint = getattr(warmup, "set_control_hint_text", None)
            if callable(set_hint):
                set_hint(hint)
            warmup.setAttribute(Qt.WA_DontShowOnScreen, True)
            warmup.setGeometry(-10000, -10000, 8, 8)
            warmup.show()
            QTimer.singleShot(0, warmup.hide)

            self._preview_warmup_widget = warmup
            self._preview_warmup_armed = True

            def _drop_warmup() -> None:
                self._dispose_preview_warmup()

            QTimer.singleShot(10000, _drop_warmup)
        except Exception:
            _log.debug("PreloadManager: STL preview warmup skipped", exc_info=True)

    def _dispose_preview_warmup(self) -> None:
        widget = self._preview_warmup_widget
        self._preview_warmup_widget = None
        self._preview_warmup_armed = False
        if widget is None:
            return
        try:
            hide = getattr(widget, "hide", None)
            if callable(hide):
                hide()
        except Exception:
            pass
        try:
            delete_later = getattr(widget, "deleteLater", None)
            if callable(delete_later):
                delete_later()
        except Exception:
            pass

    def _close_handles(self) -> None:
        self._tool_resolver = None
        self._jaw_resolver = None
        self._tool_service = None
        self._jaw_service = None
        self._fixture_service = None
        for handle_name in ("_tool_db", "_jaw_db", "_fixture_db"):
            handle = getattr(self, handle_name)
            if handle is None:
                continue
            conn = getattr(handle, "conn", None)
            close = getattr(conn, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    _log.debug("PreloadManager: close failed on %s", handle_name, exc_info=True)
            setattr(self, handle_name, None)


_instance: PreloadManager | None = None


def get_preload_manager() -> PreloadManager:
    global _instance
    if _instance is None:
        _instance = PreloadManager()
    return _instance


def reset_preload_manager_for_tests() -> None:
    global _instance
    if _instance is not None:
        _instance.shutdown()
    _instance = None


def _import_library_runtime_types():
    """Import library modules with the library's own ``config.py`` in scope.

    The Tools/Jaws app still has several modules that do plain ``from config
    import ...``. When Setup Manager imports those modules for preload work,
    Python can otherwise resolve that name to ``Setup Manager/config.py``
    instead of ``Tools and jaws Library/config.py``.
    """
    library_root = Path(__file__).resolve().parents[2] / "Tools and jaws Library"
    library_root_str = str(library_root)
    inserted_path = False
    if library_root_str not in sys.path:
        sys.path.insert(0, library_root_str)
        inserted_path = True

    previous_config = sys.modules.get("config")
    loaded_library_config = None
    try:
        sys.modules.pop("config", None)
        import config as loaded_library_config  # type: ignore

        from tools_and_jaws_library.data.database import Database
        from tools_and_jaws_library.data.fixture_database import FixtureDatabase
        from tools_and_jaws_library.data.jaw_database import JawDatabase
        from tools_and_jaws_library.services.fixture_service import FixtureService
        from tools_and_jaws_library.services.jaw_service import JawService
        from tools_and_jaws_library.services.tool_service import ToolService

        return (
            Database,
            FixtureDatabase,
            JawDatabase,
            FixtureService,
            JawService,
            ToolService,
        )
    finally:
        sys.modules.pop("config", None)
        if previous_config is not None:
            sys.modules["config"] = previous_config
        elif loaded_library_config is not None:
            # Keep the namespace clean for Setup Manager; callers that need the
            # library config should import it under their package/runtime path.
            sys.modules.pop("config", None)
        if inserted_path:
            try:
                sys.path.remove(library_root_str)
            except ValueError:
                pass

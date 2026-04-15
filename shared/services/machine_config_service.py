"""Named machine configuration management.

Each configuration bundles a display name, a machine profile key, and paths
to the Setup Manager, Tools Library and Jaws Library databases.

All configuration records live in ``machine_configurations.json`` inside the
shared runtime directory so both apps can read the active configuration
without cross-app imports.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _sanitize_folder_name(name: str) -> str:
    """Turn a config name into a safe, lowercase filesystem folder segment.

    ``"NTX 2500 / Line-B"`` → ``"ntx_2500_line_b"``
    """
    s = re.sub(r"[^\w]", "_", str(name).strip()).strip("_").lower()
    return s or "config"


def _sanitize_filename_part(name: str) -> str:
    """Turn a config name into a filesystem-safe segment, preserving case.

    ``"NTX 2500 / Line-B"`` → ``"NTX_2500_Line_B"``
    ``"NTX2500"``            → ``"NTX2500"``
    """
    s = re.sub(r"[^\w]", "_", str(name).strip()).strip("_")
    return s or "config"


@dataclass
class MachineConfig:
    id: str
    name: str
    machine_profile_key: str
    setup_db_path: str = ""
    tools_db_path: str = ""   # empty = use app default
    jaws_db_path: str = ""    # empty = use app default
    last_used_at: str = ""    # ISO-8601 UTC timestamp, updated on every switch-to


class MachineConfigService:
    """CRUD service for named machine configurations stored in JSON.

    The JSON file schema::

        {
          "active_config_id": "config_ntx2500_a3b4c5",
          "configurations": [
            {
              "id": "config_ntx2500_a3b4c5",
              "name": "NTX2500",
              "machine_profile_key": "ntx_2sp_2h",
              "setup_db_path": "/abs/path/ntx2500_a3b4c5/setup_manager.db",
              "tools_db_path": "",
              "jaws_db_path": "",
              "last_used_at": "2026-04-15T07:00:00+00:00"
            }
          ]
        }

    Empty ``tools_db_path`` / ``jaws_db_path`` means "use the application
    default path".  When two configurations share the same non-empty path,
    edits in one are visible in the other.
    """

    def __init__(self, config_file_path: Path, runtime_dir: Path) -> None:
        self._path = Path(config_file_path)
        self._runtime_dir = Path(runtime_dir)
        self._configs: list[MachineConfig] = []
        self._active_id: str = ""
        self._load()

    # ------------------------------------------------------------------ #
    # Internal load / save                                                 #
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        self._active_id = str(data.get("active_config_id") or "")
        for entry in data.get("configurations", []):
            if not isinstance(entry, dict):
                continue
            cfg_id = str(entry.get("id") or "").strip()
            if not cfg_id:
                continue
            self._configs.append(
                MachineConfig(
                    id=cfg_id,
                    name=str(entry.get("name") or "Unnamed"),
                    machine_profile_key=str(
                        entry.get("machine_profile_key") or "ntx_2sp_2h"
                    ),
                    setup_db_path=str(entry.get("setup_db_path") or ""),
                    tools_db_path=str(entry.get("tools_db_path") or ""),
                    jaws_db_path=str(entry.get("jaws_db_path") or ""),
                    last_used_at=str(entry.get("last_used_at") or ""),
                )
            )
        # Ensure active_id always points to an existing config.
        ids = {c.id for c in self._configs}
        if self._configs and self._active_id not in ids:
            self._active_id = self._configs[0].id

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_config_id": self._active_id,
            "configurations": [asdict(c) for c in self._configs],
        }
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def is_empty(self) -> bool:
        """True when no configurations have been created yet (first run)."""
        return len(self._configs) == 0

    def list_configs(self) -> list[MachineConfig]:
        return list(self._configs)

    def get_config(self, config_id: str) -> MachineConfig | None:
        for c in self._configs:
            if c.id == config_id:
                return c
        return None

    def get_active_config_id(self) -> str:
        return self._active_id

    def get_active_config(self) -> MachineConfig | None:
        """Return the active configuration, falling back to the first if needed."""
        if self._active_id:
            found = self.get_config(self._active_id)
            if found:
                return found
        return self._configs[0] if self._configs else None

    def configs_sharing_path(
        self, path: str, exclude_id: str = ""
    ) -> list[MachineConfig]:
        """Return all configs whose any DB path matches *path*, excluding *exclude_id*."""
        if not path:
            return []
        result = []
        for c in self._configs:
            if c.id == exclude_id:
                continue
            if path in (c.setup_db_path, c.tools_db_path, c.jaws_db_path):
                result.append(c)
        return result

    # ------------------------------------------------------------------ #
    # Write                                                                #
    # ------------------------------------------------------------------ #

    def set_active_config_id(self, config_id: str) -> None:
        if any(c.id == config_id for c in self._configs):
            self._active_id = config_id
            self._save()

    def update_last_used(self, config_id: str) -> None:
        """Stamp ``last_used_at`` on a config to the current UTC time."""
        ts = datetime.now(timezone.utc).isoformat()
        for i, c in enumerate(self._configs):
            if c.id == config_id:
                self._configs[i] = MachineConfig(
                    id=c.id,
                    name=c.name,
                    machine_profile_key=c.machine_profile_key,
                    setup_db_path=c.setup_db_path,
                    tools_db_path=c.tools_db_path,
                    jaws_db_path=c.jaws_db_path,
                    last_used_at=ts,
                )
                self._save()
                return

    def create_config(
        self,
        name: str,
        machine_profile_key: str,
        setup_db_path: str = "",
        tools_db_path: str = "",
        jaws_db_path: str = "",
    ) -> MachineConfig:
        """Create and persist a new configuration.

        If *setup_db_path* is empty, a path inside
        ``runtime_dir/configs/<name>_<short_id>/setup_manager.db`` is
        auto-generated using the sanitised machine name so it is recognisable
        in the file system.
        """
        short_id = uuid.uuid4().hex[:6]
        config_id = f"config_{_sanitize_folder_name(name or 'unnamed')}_{short_id}"
        file_name = _sanitize_filename_part(name or 'unnamed')
        config_folder = self._runtime_dir / "configs" / config_id
        resolved_setup_db = str(setup_db_path).strip() or str(
            config_folder / f"setup_manager_{file_name}.db"
        )
        resolved_tools_db = str(tools_db_path).strip() or str(
            config_folder / f"tool_library_{file_name}.db"
        )
        resolved_jaws_db = str(jaws_db_path).strip() or str(
            config_folder / f"jaws_library_{file_name}.db"
        )
        config = MachineConfig(
            id=config_id,
            name=str(name).strip() or "Unnamed",
            machine_profile_key=str(machine_profile_key).strip() or "ntx_2sp_2h",
            setup_db_path=resolved_setup_db,
            tools_db_path=resolved_tools_db,
            jaws_db_path=resolved_jaws_db,
            last_used_at="",
        )
        self._configs.append(config)
        if not self._active_id:
            self._active_id = config_id
        self._save()
        return config

    def update_config(self, config_id: str, **changes) -> MachineConfig:
        """Update fields of an existing configuration and persist."""
        for i, c in enumerate(self._configs):
            if c.id != config_id:
                continue
            updated = MachineConfig(
                id=c.id,
                name=str(changes.get("name", c.name)).strip() or c.name,
                machine_profile_key=str(
                    changes.get("machine_profile_key", c.machine_profile_key)
                ).strip()
                or c.machine_profile_key,
                setup_db_path=str(changes.get("setup_db_path", c.setup_db_path)),
                tools_db_path=str(changes.get("tools_db_path", c.tools_db_path)),
                jaws_db_path=str(changes.get("jaws_db_path", c.jaws_db_path)),
                last_used_at=c.last_used_at,
            )
            self._configs[i] = updated
            self._save()
            return updated
        raise ValueError(f"Configuration {config_id!r} not found.")

    def delete_config(self, config_id: str) -> None:
        """Delete a configuration.

        Raises ``ValueError`` if it is the only configuration or the active one.
        """
        if len(self._configs) <= 1:
            raise ValueError("Cannot delete the only remaining configuration.")
        if config_id == self._active_id:
            raise ValueError(
                "Cannot delete the active configuration. "
                "Switch to a different configuration first."
            )
        self._configs = [c for c in self._configs if c.id != config_id]
        self._save()

    def migrate_empty_db_paths(
        self, tools_fallback: str, jaws_fallback: str
    ) -> bool:
        """Backfill tools_db_path / jaws_db_path for configs that still have empty values.

        Configs whose setup_db_path lives inside the runtime ``configs/``
        directory (i.e. user-created machine configs) receive a dedicated
        per-config library DB path inside the same folder.  All others (the
        original / legacy config) receive the supplied fallback paths that
        point at the shared app-default library files.

        Returns ``True`` when at least one config was updated (already
        persisted to disk).  Safe to call repeatedly — exits early when
        all configs already have explicit paths.
        """
        configs_dir = str((self._runtime_dir / "configs").resolve())
        changed = False
        for i, cfg in enumerate(self._configs):
            new_tools = cfg.tools_db_path
            new_jaws = cfg.jaws_db_path
            file_name = _sanitize_filename_part(cfg.name or 'unnamed')

            if not new_tools:
                setup_folder = str(Path(cfg.setup_db_path).parent.resolve())
                if setup_folder.startswith(configs_dir):
                    # User-created config — give it a dedicated library DB.
                    new_tools = str(Path(cfg.setup_db_path).parent / f"tool_library_{file_name}.db")
                else:
                    # Legacy/original config — keep pointing at the shared library.
                    new_tools = tools_fallback

            if not new_jaws:
                setup_folder = str(Path(cfg.setup_db_path).parent.resolve())
                if setup_folder.startswith(configs_dir):
                    new_jaws = str(Path(cfg.setup_db_path).parent / f"jaws_library_{file_name}.db")
                else:
                    new_jaws = jaws_fallback

            if new_tools != cfg.tools_db_path or new_jaws != cfg.jaws_db_path:
                self._configs[i] = MachineConfig(
                    id=cfg.id,
                    name=cfg.name,
                    machine_profile_key=cfg.machine_profile_key,
                    setup_db_path=cfg.setup_db_path,
                    tools_db_path=new_tools,
                    jaws_db_path=new_jaws,
                    last_used_at=cfg.last_used_at,
                )
                changed = True

        if changed:
            self._save()

        # Pre-create empty SQLite files for any per-config library paths that
        # don't exist on disk yet (so the Tool Library can connect immediately).
        import sqlite3 as _sqlite3
        for cfg in self._configs:
            for lib_path_str in (cfg.tools_db_path, cfg.jaws_db_path):
                if not lib_path_str:
                    continue
                lib_path = Path(lib_path_str)
                try:
                    lib_path.parent.mkdir(parents=True, exist_ok=True)
                    if not lib_path.exists():
                        _conn = _sqlite3.connect(str(lib_path))
                        _conn.close()
                except Exception:
                    pass

        return changed

    def migrate_to_config_folders(self) -> bool:
        """Copy all DB files into per-config folders and rename with machine name.

        For each config, the three database files are copied to::

            .runtime/configs/{config_id}/setup_manager_{Name}.db
            .runtime/configs/{config_id}/tool_library_{Name}.db
            .runtime/configs/{config_id}/jaws_library_{Name}.db

        Original files are **not** deleted — they are left in place as backups.
        This method is idempotent: if the file is already at the target location
        nothing happens.  Returns ``True`` if any config entry was updated.
        """
        import shutil as _shutil

        def _copy_to_target(current_str: str, target: Path) -> str:
            """Copy *current_str* path to *target*.  Return the path that should be used."""
            if not current_str:
                return current_str
            current = Path(current_str)
            try:
                if current.resolve() == target.resolve():
                    return current_str  # already there
            except Exception:
                pass
            if target.exists():
                return str(target)  # already migrated on a previous run
            if not current.exists():
                return current_str  # source missing — leave reference unchanged
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(current), str(target))
                return str(target)
            except Exception:
                return current_str  # copy failed — leave reference unchanged

        changed = False
        for i, cfg in enumerate(self._configs):
            fn = _sanitize_filename_part(cfg.name or 'unnamed')
            folder = self._runtime_dir / "configs" / cfg.id

            new_setup = _copy_to_target(cfg.setup_db_path, folder / f"setup_manager_{fn}.db")
            new_tools = _copy_to_target(cfg.tools_db_path, folder / f"tool_library_{fn}.db")
            new_jaws  = _copy_to_target(cfg.jaws_db_path,  folder / f"jaws_library_{fn}.db")

            if new_setup != cfg.setup_db_path or new_tools != cfg.tools_db_path or new_jaws != cfg.jaws_db_path:
                self._configs[i] = MachineConfig(
                    id=cfg.id,
                    name=cfg.name,
                    machine_profile_key=cfg.machine_profile_key,
                    setup_db_path=new_setup,
                    tools_db_path=new_tools,
                    jaws_db_path=new_jaws,
                    last_used_at=cfg.last_used_at,
                )
                changed = True

        if changed:
            self._save()
        return changed

    def migrate_from_legacy(
        self,
        name: str,
        machine_profile_key: str,
        setup_db_path: str,
        tools_db_path: str = "",
        jaws_db_path: str = "",
    ) -> MachineConfig:
        """Bootstrap the very first configuration from pre-multi-config state.

        Only call this once, when ``is_empty()`` is True.  The created config
        is automatically set as the active one.
        """
        config = self.create_config(
            name=name,
            machine_profile_key=machine_profile_key,
            setup_db_path=setup_db_path,
            tools_db_path=tools_db_path,
            jaws_db_path=jaws_db_path,
        )
        self._active_id = config.id
        self._save()
        return config

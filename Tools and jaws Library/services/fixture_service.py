import json

from config import FIXTURE_MODELS_ROOT_DEFAULT, SHARED_UI_PREFERENCES_PATH, TOOL_MODELS_ROOT_DEFAULT
from shared.data.model_paths import JAWS_PREFIX, normalize_model_path_for_storage, read_model_roots


class FixtureService:
    FIXTURE_KINDS = ['Part', 'Assembly']

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _parse_json_list(raw, default=None):
        fallback = [] if default is None else list(default)
        if isinstance(raw, list):
            return raw
        text = str(raw or '').strip()
        if not text:
            return fallback
        try:
            parsed = json.loads(text)
        except Exception:
            return fallback
        return parsed if isinstance(parsed, list) else fallback

    @staticmethod
    def _normalize_measurement_overlays(raw) -> list[dict]:
        overlays = []
        for item in FixtureService._parse_json_list(raw):
            if isinstance(item, dict):
                overlays.append(dict(item))
        return overlays

    @staticmethod
    def _normalize_selected_parts(raw) -> list[int]:
        values: list[int] = []
        for item in FixtureService._parse_json_list(raw):
            try:
                numeric = int(item)
            except Exception:
                continue
            if numeric >= 0:
                values.append(numeric)
        return values

    @staticmethod
    def _normalize_assembly_part_ids(raw) -> list[str]:
        values: list[str] = []
        for item in FixtureService._parse_json_list(raw):
            text = str(item or '').strip()
            if text:
                values.append(text)
        return values

    def _normalize_fixture_3d_payload(self, fixture: dict) -> dict:
        data = dict(fixture or {})
        data['measurement_overlays'] = self._normalize_measurement_overlays(
            data.get('measurement_overlays', [])
        )
        data['preview_selected_parts'] = self._normalize_selected_parts(
            data.get('preview_selected_parts', [])
        )
        try:
            selected_part = int(data.get('preview_selected_part', -1) or -1)
        except Exception:
            selected_part = -1
        data['preview_selected_part'] = selected_part if selected_part >= 0 else -1
        transform_mode = str(data.get('preview_transform_mode', 'translate') or 'translate').strip().lower()
        data['preview_transform_mode'] = transform_mode if transform_mode in {'translate', 'rotate'} else 'translate'
        data['preview_fine_transform'] = bool(data.get('preview_fine_transform', False))
        data['assembly_part_ids'] = self._normalize_assembly_part_ids(
            data.get('assembly_part_ids', [])
        )
        return data

    @staticmethod
    def _norm(value: str) -> str:
        return str(value or '').strip().lower().replace(' ', '_').replace('/', '_')

    def list_fixtures(self, search_text: str = '', view_mode: str = 'all', fixture_type_filter: str = 'All'):
        query = 'SELECT * FROM fixtures WHERE 1=1'
        params: list = []

        mode = (view_mode or 'all').lower()
        if mode == 'parts':
            query += " AND lower(fixture_kind) = 'part'"
        elif mode == 'assemblies':
            query += " AND lower(fixture_kind) = 'assembly'"

        normalized_filter = self._norm(fixture_type_filter)
        if normalized_filter and normalized_filter not in {'all'}:
            query += ' AND lower(fixture_type) LIKE ?'
            params.append(f'%{normalized_filter}%')

        if search_text:
            token = f"%{search_text.lower()}%"
            query += (
                ' AND ('
                'lower(fixture_id) LIKE ? OR '
                'lower(fixture_type) LIKE ? OR '
                'lower(fixture_kind) LIKE ? OR '
                'lower(clamping_diameter_text) LIKE ? OR '
                'lower(clamping_length) LIKE ? OR '
                'lower(used_in_work) LIKE ? OR '
                'lower(turning_washer) LIKE ? OR '
                'lower(notes) LIKE ?'
                ')'
            )
            params.extend([token] * 8)

        query += ' ORDER BY fixture_id'
        return [dict(row) for row in self.db.conn.execute(query, params).fetchall()]

    def list_fixture_types(self, view_mode: str = 'all') -> list[str]:
        query = 'SELECT DISTINCT fixture_type FROM fixtures WHERE trim(coalesce(fixture_type, "")) != ""'

        mode = (view_mode or 'all').lower()
        if mode == 'parts':
            query += " AND lower(fixture_kind) = 'part'"
        elif mode == 'assemblies':
            query += " AND lower(fixture_kind) = 'assembly'"

        query += ' ORDER BY lower(fixture_type), fixture_type'
        rows = self.db.conn.execute(query).fetchall()
        return [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]

    def get_fixture(self, fixture_id: str):
        row = self.db.conn.execute(
            'SELECT * FROM fixtures WHERE fixture_id = ?', (fixture_id,)
        ).fetchone()
        if not row:
            return None
        return self._normalize_fixture_3d_payload(dict(row))

    def save_fixture(self, fixture: dict):
        fixture_id = (fixture.get('fixture_id', '') or '').strip()
        if not fixture_id:
            raise ValueError('Fixture ID is required.')

        fixture_kind = (fixture.get('fixture_kind', '') or '').strip()
        if fixture_kind not in self.FIXTURE_KINDS:
            raise ValueError('Fixture kind is invalid.')

        fixture_type = (fixture.get('fixture_type', '') or '').strip()

        _, fixtures_models_root = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            FIXTURE_MODELS_ROOT_DEFAULT,
        )
        normalized_stl_path = normalize_model_path_for_storage(
            fixture.get('stl_path', ''),
            fixtures_models_root,
            JAWS_PREFIX,
        )

        payload = (
            fixture_id,
            fixture_kind,
            fixture_type,
            (fixture.get('clamping_diameter_text', '') or '').strip(),
            (fixture.get('clamping_length', '') or '').strip(),
            (fixture.get('used_in_work', '') or '').strip(),
            (fixture.get('turning_washer', '') or '').strip(),
            (fixture.get('last_modified', '') or '').strip(),
            (fixture.get('notes', '') or '').strip(),
            normalized_stl_path,
            json.dumps(self._normalize_assembly_part_ids(fixture.get('assembly_part_ids', []))),
            (fixture.get('preview_plane', '') or 'XZ').strip(),
            int(fixture.get('preview_rot_x', 0) or 0) % 360,
            int(fixture.get('preview_rot_y', 0) or 0) % 360,
            int(fixture.get('preview_rot_z', 0) or 0) % 360,
            json.dumps(self._normalize_measurement_overlays(fixture.get('measurement_overlays', []))),
            int(fixture.get('preview_selected_part', -1) or -1),
            json.dumps(self._normalize_selected_parts(fixture.get('preview_selected_parts', []))),
            (
                'rotate'
                if str(fixture.get('preview_transform_mode', 'translate') or 'translate').strip().lower() == 'rotate'
                else 'translate'
            ),
            1 if bool(fixture.get('preview_fine_transform', False)) else 0,
        )

        with self.db.conn:
            self.db.conn.execute(
                """
                INSERT INTO fixtures (
                    fixture_id, fixture_kind, fixture_type, clamping_diameter_text, clamping_length,
                    used_in_work, turning_washer, last_modified, notes, stl_path,
                    assembly_part_ids,
                    preview_plane, preview_rot_x, preview_rot_y, preview_rot_z,
                    measurement_overlays, preview_selected_part, preview_selected_parts,
                    preview_transform_mode, preview_fine_transform
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    fixture_kind=excluded.fixture_kind,
                    fixture_type=excluded.fixture_type,
                    clamping_diameter_text=excluded.clamping_diameter_text,
                    clamping_length=excluded.clamping_length,
                    used_in_work=excluded.used_in_work,
                    turning_washer=excluded.turning_washer,
                    last_modified=excluded.last_modified,
                    notes=excluded.notes,
                    stl_path=excluded.stl_path,
                    assembly_part_ids=excluded.assembly_part_ids,
                    preview_plane=excluded.preview_plane,
                    preview_rot_x=excluded.preview_rot_x,
                    preview_rot_y=excluded.preview_rot_y,
                    preview_rot_z=excluded.preview_rot_z,
                    measurement_overlays=excluded.measurement_overlays,
                    preview_selected_part=excluded.preview_selected_part,
                    preview_selected_parts=excluded.preview_selected_parts,
                    preview_transform_mode=excluded.preview_transform_mode,
                    preview_fine_transform=excluded.preview_fine_transform
                """,
                payload,
            )

    def delete_fixture(self, fixture_id: str):
        with self.db.conn:
            self.db.conn.execute('DELETE FROM fixtures WHERE fixture_id = ?', (fixture_id,))

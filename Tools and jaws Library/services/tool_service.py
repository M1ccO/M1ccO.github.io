import json

from config import JAW_MODELS_ROOT_DEFAULT, SHARED_UI_PREFERENCES_PATH, TOOL_MODELS_ROOT_DEFAULT
from shared.model_paths import TOOLS_PREFIX, normalize_model_path_for_storage, read_model_roots


class ToolService:
    def __init__(self, db):
        self.db = db
        self._seed_if_empty()

    @staticmethod
    def _coerce_json_list(value):
        """Return a Python list from possibly serialized JSON list content.

        Handles plain lists, JSON strings, and double-encoded JSON strings.
        """
        if isinstance(value, list):
            return value
        if value is None:
            return []
        if not isinstance(value, str):
            return []

        text = value.strip()
        if not text:
            return []

        parsed = text
        for _ in range(2):
            if isinstance(parsed, list):
                return parsed
            if not isinstance(parsed, str):
                return []
            try:
                parsed = json.loads(parsed)
            except Exception:
                return []

        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _normalize_xyz_text(value):
        """Return xyz as 'x, y, z' string, tolerant of list/bracket forms."""
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            try:
                x = float(value[0])
                y = float(value[1])
                z = float(value[2])
                return f'{x:.4g}, {y:.4g}, {z:.4g}'
            except Exception:
                return ''

        text = str(value or '').strip()
        if not text:
            return ''
        text = (
            text.replace('[', ' ')
            .replace(']', ' ')
            .replace('(', ' ')
            .replace(')', ' ')
            .replace(';', ',')
        )
        parts = [p.strip() for p in text.split(',') if p.strip()]
        if len(parts) < 3:
            return ''
        try:
            x = float(parts[0])
            y = float(parts[1])
            z = float(parts[2])
        except Exception:
            return ''
        return f'{x:.4g}, {y:.4g}, {z:.4g}'

    @staticmethod
    def _diameter_axis_mode_from_axis_xyz(axis_xyz_text: str) -> str:
        text = str(axis_xyz_text or '').strip()
        if not text:
            return 'z'
        parts = [p.strip() for p in text.replace(';', ',').split(',') if p.strip()]
        if len(parts) < 3:
            return 'z'
        try:
            x = float(parts[0])
            y = float(parts[1])
            z = float(parts[2])
        except Exception:
            return 'z'

        eps = 1e-6
        if abs(x - 1.0) <= eps and abs(y) <= eps and abs(z) <= eps:
            return 'x'
        if abs(y - 1.0) <= eps and abs(x) <= eps and abs(z) <= eps:
            return 'y'
        if abs(z - 1.0) <= eps and abs(x) <= eps and abs(y) <= eps:
            return 'z'
        return 'direct'

    @staticmethod
    def _normalize_component_item(item, default_order=0):
        if not isinstance(item, dict):
            return None
        role = (item.get('role') or '').strip().lower()
        if role not in {'holder', 'cutting', 'support'}:
            return None
        code = (item.get('code') or '').strip()
        if not code:
            return None
        label = (item.get('label') or '').strip()
        if not label:
            if role == 'holder':
                label = 'Holder'
            elif role == 'cutting':
                label = 'Cutting'
            else:
                label = 'Part'
        try:
            order = int(item.get('order', default_order))
        except Exception:
            order = default_order
        return {
            'role': role,
            'label': label,
            'code': code,
            'link': (item.get('link') or '').strip(),
            'group': (item.get('group') or '').strip(),
            'order': order,
        }

    @staticmethod
    def _normalize_measurement_overlay(item, default_order=0):
        if not isinstance(item, dict):
            return None

        overlay_type = (item.get('type') or '').strip().lower()
        try:
            order = int(item.get('order', default_order))
        except Exception:
            order = default_order

        if overlay_type == 'distance':
            name = (item.get('name') or '').strip() or f'Distance {order + 1}'
            start_xyz = ToolService._normalize_xyz_text(item.get('start_xyz'))
            end_xyz = ToolService._normalize_xyz_text(item.get('end_xyz'))
            start_part = str(item.get('start_part') or '').strip()
            end_part = str(item.get('end_part') or '').strip()
            try:
                start_part_index = int(item.get('start_part_index', -1) or -1)
            except Exception:
                start_part_index = -1
            try:
                end_part_index = int(item.get('end_part_index', -1) or -1)
            except Exception:
                end_part_index = -1
            start_space = str(item.get('start_space') or '').strip().lower()
            end_space = str(item.get('end_space') or '').strip().lower()
            if start_space not in {'local', 'world'}:
                start_space = 'local' if start_part else 'world'
            if end_space not in {'local', 'world'}:
                end_space = 'local' if end_part else 'world'
            if not (name or start_xyz or end_xyz):
                return None
            return {
                'type': 'distance',
                'name': name,
                'start_part': start_part,
                'start_part_index': start_part_index,
                'start_xyz': start_xyz,
                'start_space': start_space,
                'end_part': end_part,
                'end_part_index': end_part_index,
                'end_xyz': end_xyz,
                'end_space': end_space,
                'distance_axis': str(item.get('distance_axis') or 'z').strip() or 'z',
                'label_value_mode': str(item.get('label_value_mode') or 'measured').strip() or 'measured',
                'label_custom_value': str(item.get('label_custom_value') or '').strip(),
                'offset_xyz': ToolService._normalize_xyz_text(item.get('offset_xyz') or ''),
                'start_shift': str(item.get('start_shift') or '0').strip(),
                'end_shift': str(item.get('end_shift') or '0').strip(),
                'order': order,
            }

        if overlay_type == 'diameter_ring':
            name = (item.get('name') or '').strip() or f'Diameter {order + 1}'
            part = str(item.get('part') or '').strip()
            center_xyz = ToolService._normalize_xyz_text(item.get('center_xyz'))
            edge_xyz = ToolService._normalize_xyz_text(item.get('edge_xyz'))
            axis_xyz = ToolService._normalize_xyz_text(item.get('axis_xyz'))
            offset_xyz = ToolService._normalize_xyz_text(item.get('offset_xyz') or '')
            diameter = str(item.get('diameter') or '').strip()
            diameter_mode = str(item.get('diameter_mode') or 'manual').strip().lower()
            if diameter_mode not in {'manual', 'measured'}:
                diameter_mode = 'manual'
            axis_mode = str(item.get('diameter_axis_mode') or '').strip().lower()
            if axis_mode not in {'x', 'y', 'z', 'direct'}:
                axis_mode = ToolService._diameter_axis_mode_from_axis_xyz(axis_xyz)
            try:
                part_index = int(item.get('part_index', -1) or -1)
            except Exception:
                part_index = -1
            if not (name or part or center_xyz or edge_xyz or axis_xyz or diameter or offset_xyz):
                return None
            return {
                'type': 'diameter_ring',
                'name': name,
                'part': part,
                'part_index': part_index,
                'center_xyz': center_xyz,
                'edge_xyz': edge_xyz,
                'axis_xyz': axis_xyz,
                'diameter_mode': diameter_mode,
                'diameter_axis_mode': axis_mode,
                'diameter': diameter,
                'offset_xyz': offset_xyz,
                'order': order,
            }

        if overlay_type == 'radius':
            name = (item.get('name') or '').strip() or f'Radius {order + 1}'
            part = str(item.get('part') or '').strip()
            center_xyz = ToolService._normalize_xyz_text(item.get('center_xyz'))
            axis_xyz = ToolService._normalize_xyz_text(item.get('axis_xyz'))
            radius = str(item.get('radius') or '').strip()
            if not (name or part or center_xyz or axis_xyz or radius):
                return None
            return {
                'type': 'radius',
                'name': name,
                'part': part,
                'center_xyz': center_xyz,
                'axis_xyz': axis_xyz,
                'radius': radius,
                'order': order,
            }

        if overlay_type == 'angle':
            name = (item.get('name') or '').strip() or f'Angle {order + 1}'
            part = str(item.get('part') or '').strip()
            center_xyz = ToolService._normalize_xyz_text(item.get('center_xyz'))
            start_xyz = ToolService._normalize_xyz_text(item.get('start_xyz'))
            end_xyz = ToolService._normalize_xyz_text(item.get('end_xyz'))
            if not (name or part or center_xyz or start_xyz or end_xyz):
                return None
            return {
                'type': 'angle',
                'name': name,
                'part': part,
                'center_xyz': center_xyz,
                'start_xyz': start_xyz,
                'end_xyz': end_xyz,
                'order': order,
            }

        return None

    def _component_items_from_legacy(self, tool):
        items = []

        def _add(role, label, code, link='', group=''):
            code_text = (code or '').strip()
            if not code_text:
                return
            normalized = self._normalize_component_item(
                {
                    'role': role,
                    'label': label,
                    'code': code_text,
                    'link': (link or '').strip(),
                    'group': (group or '').strip(),
                    'order': len(items),
                },
                default_order=len(items),
            )
            if normalized is not None:
                items.append(normalized)

        cutting_type = (tool.get('cutting_type') or 'Insert').strip() or 'Insert'
        _add('holder', 'Holder', tool.get('holder_code', ''), tool.get('holder_link', ''))
        _add('holder', 'Add. Element', tool.get('holder_add_element', ''), tool.get('holder_add_element_link', ''))
        _add('cutting', cutting_type, tool.get('cutting_code', ''), tool.get('cutting_link', ''))
        _add(
            'cutting',
            f'Add. {cutting_type}',
            tool.get('cutting_add_element', ''),
            tool.get('cutting_add_element_link', ''),
        )

        support_parts = self._coerce_json_list(tool.get('support_parts', []))
        for part in support_parts:
            if isinstance(part, str):
                try:
                    part = json.loads(part)
                except Exception:
                    part = {'name': part, 'code': '', 'link': '', 'group': ''}
            if not isinstance(part, dict):
                continue
            _add(
                'support',
                (part.get('name') or 'Part').strip() or 'Part',
                part.get('code', ''),
                part.get('link', ''),
                part.get('group', ''),
            )

        return items

    def _legacy_fields_from_component_items(self, component_items, fallback_cutting_type='Insert'):
        holders = [i for i in component_items if i.get('role') == 'holder']
        cuttings = [i for i in component_items if i.get('role') == 'cutting']
        supports = [i for i in component_items if i.get('role') == 'support']

        holder_main = holders[0] if len(holders) >= 1 else {}
        holder_extra = holders[1] if len(holders) >= 2 else {}
        cutting_main = cuttings[0] if len(cuttings) >= 1 else {}
        cutting_extra = cuttings[1] if len(cuttings) >= 2 else {}

        cutting_type = (
            (cutting_main.get('label') or '').strip()
            or (fallback_cutting_type or 'Insert').strip()
            or 'Insert'
        )
        if cutting_type.lower().startswith('add. '):
            cutting_type = (fallback_cutting_type or 'Insert').strip() or 'Insert'

        support_parts = []
        for item in supports:
            support_parts.append(
                {
                    'name': (item.get('label') or 'Part').strip() or 'Part',
                    'code': (item.get('code') or '').strip(),
                    'link': (item.get('link') or '').strip(),
                    'group': (item.get('group') or '').strip(),
                }
            )

        return {
            'holder_code': (holder_main.get('code') or '').strip(),
            'holder_link': (holder_main.get('link') or '').strip(),
            'holder_add_element': (holder_extra.get('code') or '').strip(),
            'holder_add_element_link': (holder_extra.get('link') or '').strip(),
            'cutting_type': cutting_type,
            'cutting_code': (cutting_main.get('code') or '').strip(),
            'cutting_link': (cutting_main.get('link') or '').strip(),
            'cutting_add_element': (cutting_extra.get('code') or '').strip(),
            'cutting_add_element_link': (cutting_extra.get('link') or '').strip(),
            'support_parts': support_parts,
        }

    def _normalize_tool_record(self, row_dict):
        tool = dict(row_dict)
        if 'uid' in tool:
            try:
                tool['uid'] = int(tool['uid'])
            except Exception:
                tool['uid'] = None
        tool_head = (tool.get('tool_head', 'HEAD1') or 'HEAD1').strip().upper()
        tool['tool_head'] = tool_head if tool_head in {'HEAD1', 'HEAD2'} else 'HEAD1'
        tool['geometry_profiles'] = self._coerce_json_list(tool.get('geometry_profiles'))
        tool['support_parts'] = self._coerce_json_list(tool.get('support_parts'))
        raw_components = self._coerce_json_list(tool.get('component_items'))
        raw_measurements = self._coerce_json_list(tool.get('measurement_overlays'))
        normalized_components = []
        normalized_measurements = []
        for idx, item in enumerate(raw_components):
            normalized = self._normalize_component_item(item, idx)
            if normalized is not None:
                normalized_components.append(normalized)
        for idx, item in enumerate(raw_measurements):
            normalized = self._normalize_measurement_overlay(item, idx)
            if normalized is not None:
                normalized_measurements.append(normalized)
        normalized_components.sort(key=lambda entry: int(entry.get('order', 0)))
        normalized_measurements.sort(key=lambda entry: int(entry.get('order', 0)))
        if not normalized_components:
            normalized_components = self._component_items_from_legacy(tool)
        tool['component_items'] = normalized_components
        tool['measurement_overlays'] = normalized_measurements
        return tool

    def _seed_if_empty(self):
        count = self.db.conn.execute('SELECT COUNT(*) FROM tools').fetchone()[0]
        if count:
            return
        sample = {
            'id': 'T1001',
            'tool_head': 'HEAD1',
            'tool_type': 'O.D Turning',
            'description': 'Ulkorouhinta - 80/R1.2',
            'geom_x': 150.0,
            'geom_z': 50.0,
            'radius': 0.0,
            'nose_corner_radius': 1.2,
            'holder_code': 'C6-PSRNR-35065-15HP',
            'holder_link': '',
            'holder_add_element': '',
            'holder_add_element_link': '',
            'cutting_type': 'Insert',
            'cutting_code': 'SNMG 15 06 16-QM 1205',
            'cutting_link': '',
            'cutting_add_element': '',
            'cutting_add_element_link': '',
            'support_parts': [
                {'name': 'Shim', 'code': '174.3-857'},
                {'name': 'Screw', 'code': '438.3-831'},
                {'name': 'Clamp', 'code': '438.3-840'},
                {'name': 'Extra holder / sleeve', 'code': 'ER32-C6'},
            ],
            'component_items': [
                {'role': 'holder', 'label': 'Holder', 'code': 'C6-PSRNR-35065-15HP', 'link': '', 'group': '', 'order': 0},
                {'role': 'cutting', 'label': 'Insert', 'code': 'SNMG 15 06 16-QM 1205', 'link': '', 'group': '', 'order': 1},
                {'role': 'support', 'label': 'Shim', 'code': '174.3-857', 'link': '', 'group': '', 'order': 2},
                {'role': 'support', 'label': 'Screw', 'code': '438.3-831', 'link': '', 'group': '', 'order': 3},
                {'role': 'support', 'label': 'Clamp', 'code': '438.3-840', 'link': '', 'group': '', 'order': 4},
                {'role': 'support', 'label': 'Extra holder / sleeve', 'code': 'ER32-C6', 'link': '', 'group': '', 'order': 5},
            ],
            'notes': 'Clamp + screw set',
            'drill_nose_angle': 0,
            'mill_cutting_edges': 0,
            'measurement_overlays': [],
            'geometry_profiles': [
                {'variant': 'H1', 'h_code': 'H1', 'b_axis': 'B0', 'spindle': 'Main', 'description': 'Standard main spindle setup'},
                {'variant': 'H2', 'h_code': 'H2', 'b_axis': 'B90', 'spindle': 'Main', 'description': 'Rotated posture'},
            ],
            # empty string means no 3‑D model attached yet
            'stl_path': '',
        }
        self.save_tool(sample)

    def list_tools(self, search_text='', tool_type='All', tool_head='HEAD1/2'):
        query = 'SELECT * FROM tools WHERE 1=1'
        params = []
        if search_text:
            token = f"%{search_text.lower()}%"
            query += (
                ' AND ('
                'lower(id) LIKE ? OR '
                'lower(description) LIKE ? OR '
                'lower(holder_code) LIKE ? OR '
                'lower(cutting_code) LIKE ? OR '
                'lower(notes) LIKE ? OR '
                'lower(CAST(geom_x AS TEXT)) LIKE ? OR '
                'lower(CAST(geom_z AS TEXT)) LIKE ? OR '
                'lower(CAST(radius AS TEXT)) LIKE ? OR '
                'lower(CAST(nose_corner_radius AS TEXT)) LIKE ? OR '
                'lower(printf("%.3f", geom_x)) LIKE ? OR '
                'lower(printf("%.3f", geom_z)) LIKE ? OR '
                'lower(printf("%.3f", radius)) LIKE ? OR '
                'lower(printf("%.3f", nose_corner_radius)) LIKE ?'
                ')'
            )
            params.extend([
                token, token, token, token, token,
                token, token, token, token,
                token, token, token, token,
            ])
        if tool_type and tool_type != 'All':
            query += ' AND tool_type = ?'
            params.append(tool_type)

        selected_head = (tool_head or 'HEAD1/2').strip().upper()
        if selected_head in {'HEAD1', 'HEAD2'}:
            query += ' AND tool_head = ?'
            params.append(selected_head)

        query += ' ORDER BY id, uid'
        return [self._normalize_tool_record(r) for r in self.db.conn.execute(query, params).fetchall()]

    def get_tool(self, tool_id):
        row = self.db.conn.execute('SELECT * FROM tools WHERE id = ? ORDER BY uid DESC LIMIT 1', (tool_id,)).fetchone()
        return self._normalize_tool_record(row) if row else None

    def get_tool_by_uid(self, uid):
        row = self.db.conn.execute('SELECT * FROM tools WHERE uid = ?', (uid,)).fetchone()
        return self._normalize_tool_record(row) if row else None

    def tcode_exists(self, tool_id: str, exclude_uid=None) -> bool:
        tool_id = (tool_id or '').strip()
        if not tool_id:
            return False
        if exclude_uid is None:
            row = self.db.conn.execute('SELECT 1 FROM tools WHERE id = ? LIMIT 1', (tool_id,)).fetchone()
            return bool(row)
        row = self.db.conn.execute(
            'SELECT 1 FROM tools WHERE id = ? AND uid <> ? LIMIT 1',
            (tool_id, int(exclude_uid)),
        ).fetchone()
        return bool(row)

    def save_tool(self, tool, allow_duplicate: bool = False):
        geometry_profiles = self._coerce_json_list(tool.get('geometry_profiles', []))
        raw_component_items = self._coerce_json_list(tool.get('component_items', []))
        component_items = []
        for idx, item in enumerate(raw_component_items):
            normalized = self._normalize_component_item(item, idx)
            if normalized is not None:
                component_items.append(normalized)
        component_items.sort(key=lambda entry: int(entry.get('order', 0)))
        if not component_items:
            component_items = self._component_items_from_legacy(tool)

        legacy = self._legacy_fields_from_component_items(
            component_items,
            fallback_cutting_type=(str(tool.get('cutting_type', 'Insert') or 'Insert').strip() or 'Insert'),
        )
        support_parts = self._coerce_json_list(tool.get('support_parts', []))
        if not support_parts:
            support_parts = legacy['support_parts']
        raw_measurement_overlays = self._coerce_json_list(tool.get('measurement_overlays', []))
        measurement_overlays = []
        for idx, item in enumerate(raw_measurement_overlays):
            normalized = self._normalize_measurement_overlay(item, idx)
            if normalized is not None:
                measurement_overlays.append(normalized)
        measurement_overlays.sort(key=lambda entry: int(entry.get('order', 0)))
        selected_head = (tool.get('tool_head', 'HEAD1') or 'HEAD1').strip().upper()
        if selected_head not in {'HEAD1', 'HEAD2'}:
            selected_head = 'HEAD1'

        tools_models_root, _ = read_model_roots(
            SHARED_UI_PREFERENCES_PATH,
            TOOL_MODELS_ROOT_DEFAULT,
            JAW_MODELS_ROOT_DEFAULT,
        )

        raw_stl_path = tool.get('stl_path', '')
        parsed_parts = self._coerce_json_list(raw_stl_path)
        if parsed_parts:
            normalized_parts = []
            for part in parsed_parts:
                if not isinstance(part, dict):
                    continue
                normalized_part = dict(part)
                normalized_part['file'] = normalize_model_path_for_storage(
                    normalized_part.get('file', ''),
                    tools_models_root,
                    TOOLS_PREFIX,
                )
                normalized_parts.append(normalized_part)
            normalized_stl_path = json.dumps(normalized_parts, ensure_ascii=False) if normalized_parts else ''
        else:
            normalized_stl_path = normalize_model_path_for_storage(
                raw_stl_path,
                tools_models_root,
                TOOLS_PREFIX,
            )

        payload = (
            tool['id'].strip(),
            selected_head,
            tool.get('tool_type', 'O.D Turning').strip() or 'O.D Turning',
            tool.get('description', '').strip(),
            float(tool.get('geom_x', 0) or 0),
            float(tool.get('geom_z', 0) or 0),
            float(tool.get('radius', 0) or 0),
            float(tool.get('nose_corner_radius', 0) or 0),
            legacy['holder_code'],
            legacy['holder_link'],
            legacy['holder_add_element'],
            legacy['holder_add_element_link'],
            legacy['cutting_type'],
            legacy['cutting_code'],
            legacy['cutting_link'],
            legacy['cutting_add_element'],
            legacy['cutting_add_element_link'],
            tool.get('notes', '').strip(),
            float(tool.get('drill_nose_angle', 0) or 0),
            int(tool.get('mill_cutting_edges', 0) or 0),
            tool.get('notes', '').strip(),
            json.dumps(geometry_profiles, ensure_ascii=False),
            json.dumps(support_parts, ensure_ascii=False),
            json.dumps(component_items, ensure_ascii=False),
            json.dumps(measurement_overlays, ensure_ascii=False),
            normalized_stl_path,
            tool.get('default_pot', '').strip(),
        )
        uid = tool.get('uid')
        with self.db.conn:
            if uid is None:
                tool_id = tool['id'].strip()
                if (not allow_duplicate) and self.tcode_exists(tool_id):
                    existing_row = self.db.conn.execute(
                        'SELECT uid FROM tools WHERE id = ? ORDER BY uid DESC LIMIT 1',
                        (tool_id,),
                    ).fetchone()
                    if existing_row:
                        uid = int(existing_row[0])
                if uid is None:
                    self.db.conn.execute(
                        """
                        INSERT INTO tools (
                            id, tool_head, tool_type, description, geom_x, geom_z, radius,
                            nose_corner_radius, holder_code, holder_link, holder_add_element, holder_add_element_link,
                            cutting_type, cutting_code, cutting_link, cutting_add_element, cutting_add_element_link,
                            notes, drill_nose_angle, mill_cutting_edges, spare_parts,
                            geometry_profiles, support_parts, component_items, measurement_overlays, stl_path, default_pot
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        payload,
                    )
                    return int(self.db.conn.execute('SELECT last_insert_rowid()').fetchone()[0])

            update_payload = payload + (int(uid),)
            self.db.conn.execute(
                """
                UPDATE tools
                SET
                    id=?,
                    tool_head=?,
                    tool_type=?,
                    description=?,
                    geom_x=?,
                    geom_z=?,
                    radius=?,
                    nose_corner_radius=?,
                    holder_code=?,
                    holder_link=?,
                    holder_add_element=?,
                    holder_add_element_link=?,
                    cutting_type=?,
                    cutting_code=?,
                    cutting_link=?,
                    cutting_add_element=?,
                    cutting_add_element_link=?,
                    notes=?,
                    drill_nose_angle=?,
                    mill_cutting_edges=?,
                    spare_parts=?,
                    geometry_profiles=?,
                    support_parts=?,
                    component_items=?,
                    measurement_overlays=?,
                    stl_path=?,
                    default_pot=?
                WHERE uid=?
                """,
                update_payload,
            )
            return int(uid)

    def delete_tool(self, tool_id):
        with self.db.conn:
            self.db.conn.execute('DELETE FROM tools WHERE id = ?', (tool_id,))

    def delete_tool_by_uid(self, uid):
        with self.db.conn:
            self.db.conn.execute('DELETE FROM tools WHERE uid = ?', (uid,))

    def copy_tool(self, source_id: str, new_id: str, new_description: str = '', allow_duplicate: bool = False):
        tool = self.get_tool(source_id)
        if not tool:
            raise ValueError('Source tool not found.')
        if not allow_duplicate and self.tcode_exists(new_id):
            raise ValueError(f'Tool ID {new_id} already exists.')
        tool.pop('uid', None)
        tool['id'] = new_id.strip()
        if new_description.strip():
            tool['description'] = new_description.strip()
        new_uid = self.save_tool(tool, allow_duplicate=allow_duplicate)
        copied = self.get_tool_by_uid(new_uid)
        return copied or tool

    def copy_tool_by_uid(self, source_uid: int, new_id: str, new_description: str = '', allow_duplicate: bool = False):
        tool = self.get_tool_by_uid(source_uid)
        if not tool:
            raise ValueError('Source tool not found.')
        if not allow_duplicate and self.tcode_exists(new_id):
            raise ValueError(f'Tool ID {new_id} already exists.')
        tool.pop('uid', None)
        tool['id'] = new_id.strip()
        if new_description.strip():
            tool['description'] = new_description.strip()
        new_uid = self.save_tool(tool, allow_duplicate=allow_duplicate)
        copied = self.get_tool_by_uid(new_uid)
        return copied or tool

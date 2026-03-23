import json


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

    def _normalize_tool_record(self, row_dict):
        tool = dict(row_dict)
        tool['geometry_profiles'] = self._coerce_json_list(tool.get('geometry_profiles'))
        tool['support_parts'] = self._coerce_json_list(tool.get('support_parts'))
        return tool

    def _seed_if_empty(self):
        count = self.db.conn.execute('SELECT COUNT(*) FROM tools').fetchone()[0]
        if count:
            return
        sample = {
            'id': 'T1001',
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
            'notes': 'Clamp + screw set',
            'drill_nose_angle': 0,
            'mill_cutting_edges': 0,
            'geometry_profiles': [
                {'variant': 'H1', 'h_code': 'H1', 'b_axis': 'B0', 'spindle': 'SP1', 'description': 'Standard SP1 setup'},
                {'variant': 'H2', 'h_code': 'H2', 'b_axis': 'B90', 'spindle': 'SP1', 'description': 'Rotated posture'},
            ],
            # empty string means no 3‑D model attached yet
            'stl_path': '',
        }
        self.save_tool(sample)

    def list_tools(self, search_text='', tool_type='All'):
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
        query += ' ORDER BY id'
        return [self._normalize_tool_record(r) for r in self.db.conn.execute(query, params).fetchall()]

    def get_tool(self, tool_id):
        row = self.db.conn.execute('SELECT * FROM tools WHERE id = ?', (tool_id,)).fetchone()
        return self._normalize_tool_record(row) if row else None

    def save_tool(self, tool):
        geometry_profiles = self._coerce_json_list(tool.get('geometry_profiles', []))
        support_parts = self._coerce_json_list(tool.get('support_parts', []))

        payload = (
            tool['id'].strip(),
            tool.get('tool_type', 'O.D Turning').strip() or 'O.D Turning',
            tool.get('description', '').strip(),
            float(tool.get('geom_x', 0) or 0),
            float(tool.get('geom_z', 0) or 0),
            float(tool.get('radius', 0) or 0),
            float(tool.get('nose_corner_radius', 0) or 0),
            tool.get('holder_code', '').strip(),
            tool.get('holder_link', '').strip(),
            tool.get('holder_add_element', '').strip(),
            tool.get('holder_add_element_link', '').strip(),
            tool.get('cutting_type', 'Insert').strip() or 'Insert',
            tool.get('cutting_code', '').strip(),
            tool.get('cutting_link', '').strip(),
            tool.get('cutting_add_element', '').strip(),
            tool.get('cutting_add_element_link', '').strip(),
            tool.get('notes', '').strip(),
            float(tool.get('drill_nose_angle', 0) or 0),
            int(tool.get('mill_cutting_edges', 0) or 0),
            tool.get('notes', '').strip(),
            json.dumps(geometry_profiles, ensure_ascii=False),
            json.dumps(support_parts, ensure_ascii=False),
            tool.get('stl_path', ''),
        )
        with self.db.conn:
            self.db.conn.execute(
                """
                INSERT INTO tools (
                    id, tool_type, description, geom_x, geom_z, radius,
                    nose_corner_radius, holder_code, holder_link, holder_add_element, holder_add_element_link,
                    cutting_type, cutting_code, cutting_link, cutting_add_element, cutting_add_element_link,
                    notes, drill_nose_angle, mill_cutting_edges, spare_parts,
                    geometry_profiles, support_parts, stl_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    tool_type=excluded.tool_type,
                    description=excluded.description,
                    geom_x=excluded.geom_x,
                    geom_z=excluded.geom_z,
                    radius=excluded.radius,
                    nose_corner_radius=excluded.nose_corner_radius,
                    holder_code=excluded.holder_code,
                    holder_link=excluded.holder_link,
                    holder_add_element=excluded.holder_add_element,
                    holder_add_element_link=excluded.holder_add_element_link,
                    cutting_type=excluded.cutting_type,
                    cutting_code=excluded.cutting_code,
                    cutting_link=excluded.cutting_link,
                    cutting_add_element=excluded.cutting_add_element,
                    cutting_add_element_link=excluded.cutting_add_element_link,
                    notes=excluded.notes,
                    drill_nose_angle=excluded.drill_nose_angle,
                    mill_cutting_edges=excluded.mill_cutting_edges,
                    spare_parts=excluded.spare_parts,
                    geometry_profiles=excluded.geometry_profiles,
                    support_parts=excluded.support_parts,
                    stl_path=excluded.stl_path
                """,
                payload,
            )

    def delete_tool(self, tool_id):
        with self.db.conn:
            self.db.conn.execute('DELETE FROM tools WHERE id = ?', (tool_id,))

    def copy_tool(self, source_id: str, new_id: str, new_description: str = ''):
        tool = self.get_tool(source_id)
        if not tool:
            raise ValueError('Source tool not found.')
        if self.get_tool(new_id):
            raise ValueError(f'Tool ID {new_id} already exists.')
        tool['id'] = new_id.strip()
        if new_description.strip():
            tool['description'] = new_description.strip()
        self.save_tool(tool)
        return tool

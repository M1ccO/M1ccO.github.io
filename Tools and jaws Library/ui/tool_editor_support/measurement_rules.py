import json
import math


def empty_measurement_editor_state() -> dict:
    return {
        'distance_measurements': [],
        'diameter_measurements': [],
        'radius_measurements': [],
        'angle_measurements': [],
    }


def normalize_xyz_text(value) -> str:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            x = float(value[0])
            y = float(value[1])
            z = float(value[2])
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                return ''
            return f"{x:.4g}, {y:.4g}, {z:.4g}"
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
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        return ''
    return f"{x:.4g}, {y:.4g}, {z:.4g}"


def normalize_float_value(value, default: float = 0.0) -> float:
    try:
        numeric = float(str(value).strip().replace(',', '.'))
    except Exception:
        return float(default)
    return numeric if math.isfinite(numeric) else float(default)


def normalize_distance_space(part_name, part_index, point_space) -> str:
    has_part_ref = bool(str(part_name or '').strip())
    if not has_part_ref:
        try:
            has_part_ref = int(part_index) >= 0
        except Exception:
            has_part_ref = False
    normalized = str(point_space or '').strip().lower()
    if normalized not in {'local', 'world'}:
        return 'local' if has_part_ref else 'world'
    if normalized == 'world' and has_part_ref:
        # Compatibility guard: legacy part-anchored points are treated as local.
        return 'local'
    return normalized


def normalize_measurement_editor_state(tool_data) -> dict:
    normalized = empty_measurement_editor_state()
    if not isinstance(tool_data, dict):
        return normalized

    for key in normalized:
        values = tool_data.get(key, [])
        if isinstance(values, list):
            normalized[key] = [dict(item) for item in values if isinstance(item, dict)]

    return normalized


def parse_measurement_overlays(raw_overlays) -> dict:
    state = empty_measurement_editor_state()
    source = raw_overlays
    if isinstance(source, str):
        try:
            source = json.loads(source or '[]')
        except Exception:
            source = []

    if not isinstance(source, list):
        return state

    for overlay in source:
        if not isinstance(overlay, dict):
            continue
        overlay_type = (overlay.get('type') or '').strip().lower()
        if overlay_type == 'distance':
            start_part = overlay.get('start_part', '')
            end_part = overlay.get('end_part', '')
            try:
                start_part_index = int(overlay.get('start_part_index', -1) or -1)
            except Exception:
                start_part_index = -1
            try:
                end_part_index = int(overlay.get('end_part_index', -1) or -1)
            except Exception:
                end_part_index = -1
            state['distance_measurements'].append(
                {
                    'name': overlay.get('name', ''),
                    'start_part': start_part,
                    'start_part_index': start_part_index,
                    'start_xyz': normalize_xyz_text(overlay.get('start_xyz', '')),
                    'start_space': normalize_distance_space(
                        start_part,
                        start_part_index,
                        overlay.get('start_space', ''),
                    ),
                    'end_part': end_part,
                    'end_part_index': end_part_index,
                    'end_xyz': normalize_xyz_text(overlay.get('end_xyz', '')),
                    'end_space': normalize_distance_space(
                        end_part,
                        end_part_index,
                        overlay.get('end_space', ''),
                    ),
                    'distance_axis': overlay.get('distance_axis', 'z'),
                    'label_value_mode': overlay.get('label_value_mode', 'measured'),
                    'label_custom_value': overlay.get('label_custom_value', ''),
                    'offset_xyz': normalize_xyz_text(overlay.get('offset_xyz', '')),
                    'start_shift': overlay.get('start_shift', '0'),
                    'end_shift': overlay.get('end_shift', '0'),
                }
            )
        elif overlay_type == 'diameter_ring':
            state['diameter_measurements'].append(
                {
                    'name': overlay.get('name', ''),
                    'part': overlay.get('part', ''),
                    'part_index': overlay.get('part_index', -1),
                    'center_xyz': normalize_xyz_text(overlay.get('center_xyz', '')),
                    'edge_xyz': normalize_xyz_text(overlay.get('edge_xyz', '')),
                    'axis_xyz': normalize_xyz_text(overlay.get('axis_xyz', '0, 0, 1')),
                    'diameter_axis_mode': str(overlay.get('diameter_axis_mode') or '').strip().lower(),
                    'offset_xyz': normalize_xyz_text(overlay.get('offset_xyz', '')),
                    'diameter_visual_offset_mm': normalize_float_value(
                        overlay.get('diameter_visual_offset_mm', 1.0),
                        1.0,
                    ),
                    'diameter_mode': overlay.get('diameter_mode', 'manual'),
                    'diameter': overlay.get('diameter', ''),
                }
            )
        elif overlay_type == 'radius':
            state['radius_measurements'].append(
                {
                    'name': overlay.get('name', ''),
                    'part': overlay.get('part', ''),
                    'center_xyz': normalize_xyz_text(overlay.get('center_xyz', '')),
                    'axis_xyz': normalize_xyz_text(overlay.get('axis_xyz', '')),
                    'radius': overlay.get('radius', ''),
                }
            )
        elif overlay_type == 'angle':
            state['angle_measurements'].append(
                {
                    'name': overlay.get('name', ''),
                    'part': overlay.get('part', ''),
                    'center_xyz': normalize_xyz_text(overlay.get('center_xyz', '')),
                    'start_xyz': normalize_xyz_text(overlay.get('start_xyz', '')),
                    'end_xyz': normalize_xyz_text(overlay.get('end_xyz', '')),
                }
            )

    return normalize_measurement_editor_state(state)


def _to_int(value, default: int = -1) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _diameter_axis_mode_from_axis_vector(axis_xyz: str) -> str:
    axis_tokens = [token.strip() for token in axis_xyz.split(',')]
    if len(axis_tokens) < 3:
        return 'direct'
    try:
        ax = abs(float(axis_tokens[0]))
        ay = abs(float(axis_tokens[1]))
        az = abs(float(axis_tokens[2]))
    except Exception:
        return 'direct'
    tol = 1e-3
    if abs(ax - 1.0) <= tol and ay <= tol and az <= tol:
        return 'x'
    if abs(ay - 1.0) <= tol and ax <= tol and az <= tol:
        return 'y'
    if abs(az - 1.0) <= tol and ax <= tol and ay <= tol:
        return 'z'
    return 'direct'


def measurement_overlays_from_state(state: dict, *, translate) -> list[dict]:
    overlays = []
    normalized_state = normalize_measurement_editor_state(state)

    for entry in normalized_state.get('distance_measurements', []):
        name = (entry.get('name') or '').strip()
        start_part = (entry.get('start_part') or '').strip()
        start_xyz = normalize_xyz_text(entry.get('start_xyz') or '')
        end_part = (entry.get('end_part') or '').strip()
        end_xyz = normalize_xyz_text(entry.get('end_xyz') or '')
        start_part_index = _to_int(entry.get('start_part_index', -1) or -1, -1)
        end_part_index = _to_int(entry.get('end_part_index', -1) or -1, -1)
        if not (name or start_part or start_xyz or end_part or end_xyz):
            continue
        overlays.append(
            {
                'type': 'distance',
                'name': name or translate('tool_editor.measurements.default_distance', 'Distance'),
                'start_part': start_part,
                'start_part_index': start_part_index,
                'start_xyz': start_xyz,
                'start_space': normalize_distance_space(
                    start_part,
                    start_part_index,
                    entry.get('start_space', ''),
                ),
                'end_part': end_part,
                'end_part_index': end_part_index,
                'end_xyz': end_xyz,
                'end_space': normalize_distance_space(
                    end_part,
                    end_part_index,
                    entry.get('end_space', ''),
                ),
                'distance_axis': (entry.get('distance_axis') or 'z').strip() or 'z',
                'label_value_mode': (entry.get('label_value_mode') or 'measured').strip() or 'measured',
                'label_custom_value': (entry.get('label_custom_value') or '').strip(),
                'offset_xyz': normalize_xyz_text(entry.get('offset_xyz') or ''),
                'start_shift': str(entry.get('start_shift') or '0').strip(),
                'end_shift': str(entry.get('end_shift') or '0').strip(),
                'order': len(overlays),
            }
        )

    for entry in normalized_state.get('diameter_measurements', []):
        name = (entry.get('name') or '').strip()
        part = (entry.get('part') or '').strip()
        center_xyz = normalize_xyz_text(entry.get('center_xyz') or '')
        edge_xyz = normalize_xyz_text(entry.get('edge_xyz') or '')
        axis_xyz = normalize_xyz_text(entry.get('axis_xyz') or '0, 0, 1')
        diameter_axis_mode = str(entry.get('diameter_axis_mode') or '').strip().lower()
        if diameter_axis_mode not in {'x', 'y', 'z', 'direct'}:
            diameter_axis_mode = _diameter_axis_mode_from_axis_vector(axis_xyz)
        offset_xyz = normalize_xyz_text(entry.get('offset_xyz') or '')
        diameter_mode = str(entry.get('diameter_mode') or ('measured' if edge_xyz else 'manual')).strip().lower()
        if diameter_mode not in {'measured', 'manual'}:
            diameter_mode = 'manual'
        diameter = str(entry.get('diameter') or '').strip()
        if not (name or part or center_xyz or edge_xyz or axis_xyz or offset_xyz or diameter):
            continue
        overlays.append(
            {
                'type': 'diameter_ring',
                'name': name or translate('tool_editor.measurements.default_ring', 'Diameter'),
                'part': part,
                'part_index': _to_int(entry.get('part_index', -1) or -1, -1),
                'center_xyz': center_xyz,
                'edge_xyz': edge_xyz,
                'axis_xyz': axis_xyz,
                'diameter_axis_mode': diameter_axis_mode,
                'offset_xyz': offset_xyz,
                'diameter_visual_offset_mm': normalize_float_value(
                    entry.get('diameter_visual_offset_mm', 1.0),
                    1.0,
                ),
                'diameter_mode': diameter_mode,
                'diameter': diameter,
                'order': len(overlays),
            }
        )

    for entry in normalized_state.get('radius_measurements', []):
        name = (entry.get('name') or '').strip()
        part = (entry.get('part') or '').strip()
        center_xyz = normalize_xyz_text(entry.get('center_xyz') or '')
        axis_xyz = normalize_xyz_text(entry.get('axis_xyz') or '')
        radius = (entry.get('radius') or '').strip()
        if not (name or part or center_xyz or axis_xyz or radius):
            continue
        overlays.append(
            {
                'type': 'radius',
                'name': name or translate('tool_editor.measurements.default_radius', 'Radius'),
                'part': part,
                'center_xyz': center_xyz,
                'axis_xyz': axis_xyz,
                'radius': radius,
                'order': len(overlays),
            }
        )

    for entry in normalized_state.get('angle_measurements', []):
        name = (entry.get('name') or '').strip()
        part = (entry.get('part') or '').strip()
        center_xyz = normalize_xyz_text(entry.get('center_xyz') or '')
        start_xyz = normalize_xyz_text(entry.get('start_xyz') or '')
        end_xyz = normalize_xyz_text(entry.get('end_xyz') or '')
        if not (name or part or center_xyz or start_xyz or end_xyz):
            continue
        overlays.append(
            {
                'type': 'angle',
                'name': name or translate('tool_editor.measurements.default_angle', 'Angle'),
                'part': part,
                'center_xyz': center_xyz,
                'start_xyz': start_xyz,
                'end_xyz': end_xyz,
                'order': len(overlays),
            }
        )

    return overlays

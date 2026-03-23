from dataclasses import dataclass


@dataclass
class Jaw:
    jaw_id: str
    jaw_type: str = 'Soft jaws'
    spindle_side: str = 'SP1'
    clamping_diameter_text: str = ''
    clamping_length: str = ''
    used_in_work: str = ''
    turning_washer: str = ''
    last_modified: str = ''
    notes: str = ''
    stl_path: str = ''

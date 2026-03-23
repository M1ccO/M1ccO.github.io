from dataclasses import dataclass, field
from typing import List


@dataclass
class AdditionalPart:
    name: str = ''
    code: str = ''
    link: str = ''


@dataclass
class GeometryProfile:
    variant: str = ''
    h_code: str = ''
    b_axis: str = ''
    spindle: str = ''
    description: str = ''


@dataclass
class Tool:
    id: str
    tool_head: str = 'HEAD1'
    tool_type: str = 'Turning'
    description: str = ''
    geom_x: float = 0.0
    geom_z: float = 0.0
    radius: float = 0.0
    nose_corner_radius: float = 0.0
    holder_code: str = ''
    holder_link: str = ''
    holder_add_element: str = ''
    holder_add_element_link: str = ''
    cutting_type: str = 'Insert'
    cutting_code: str = ''
    cutting_link: str = ''
    cutting_add_element: str = ''
    cutting_add_element_link: str = ''
    notes: str = ''
    drill_nose_angle: float = 0.0
    mill_cutting_edges: int = 0
    support_parts: List[AdditionalPart] = field(default_factory=list)
    geometry_profiles: List[GeometryProfile] = field(default_factory=list)

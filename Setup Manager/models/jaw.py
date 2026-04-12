from dataclasses import dataclass
from pathlib import Path
import sys

try:
    from shared.models.jaw import Jaw as _SharedJaw
except ModuleNotFoundError:
    workspace_root = Path(__file__).resolve().parents[2]
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))
    from shared.models.jaw import Jaw as _SharedJaw


@dataclass
class Jaw(_SharedJaw):
    spindle_side: str = 'SP1'


__all__ = ["Jaw"]


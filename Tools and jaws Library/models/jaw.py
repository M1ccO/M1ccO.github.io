from pathlib import Path
import sys

try:
	from shared.models.jaw import Jaw
except ModuleNotFoundError:
	workspace_root = Path(__file__).resolve().parents[2]
	if str(workspace_root) not in sys.path:
		sys.path.insert(0, str(workspace_root))
	from shared.models.jaw import Jaw

__all__ = ["Jaw"]


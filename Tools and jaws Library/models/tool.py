from pathlib import Path
import sys

try:
	from shared.models.tool import AdditionalPart, GeometryProfile, Tool
except ModuleNotFoundError:
	workspace_root = Path(__file__).resolve().parents[2]
	if str(workspace_root) not in sys.path:
		sys.path.insert(0, str(workspace_root))
	from shared.models.tool import AdditionalPart, GeometryProfile, Tool

__all__ = ["Tool", "AdditionalPart", "GeometryProfile"]


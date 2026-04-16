"""Selector dialog package.

Keep this module import-light so importing one selector module does not force
loading all selector dialogs and their dependency trees.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .fixture_selector_dialog import FixtureSelectorDialog
	from .jaw_selector_dialog import JawSelectorDialog
	from .tool_selector_dialog import ToolSelectorDialog

__all__ = ["ToolSelectorDialog", "JawSelectorDialog", "FixtureSelectorDialog"]


def __getattr__(name: str):
	if name == "ToolSelectorDialog":
		from .tool_selector_dialog import ToolSelectorDialog as _ToolSelectorDialog

		return _ToolSelectorDialog
	if name == "JawSelectorDialog":
		from .jaw_selector_dialog import JawSelectorDialog as _JawSelectorDialog

		return _JawSelectorDialog
	if name == "FixtureSelectorDialog":
		from .fixture_selector_dialog import FixtureSelectorDialog as _FixtureSelectorDialog

		return _FixtureSelectorDialog
	raise AttributeError(name)

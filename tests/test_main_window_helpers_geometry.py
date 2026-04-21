from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
for _candidate in (_WORKSPACE,):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

import shared.ui.main_window_helpers as helpers  # noqa: E402


class _DummyFrameGeometry:
    def __init__(self, x: int, y: int, width: int, height: int):
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


class _DummyWindow:
    def __init__(self, hwnd: int = 123):
        self._hwnd = hwnd

    def winId(self) -> int:
        return self._hwnd

    def frameGeometry(self):
        return _DummyFrameGeometry(1, 2, 3, 4)

    def width(self) -> int:
        return 320

    def height(self) -> int:
        return 260

    def resize(self, _width: int, _height: int) -> None:
        raise AssertionError("resize fallback should not be used in this test")

    def move(self, _x: int, _y: int) -> None:
        raise AssertionError("move fallback should not be used in this test")


class TestMainWindowHelpersGeometry(unittest.TestCase):
    def test_current_window_rect_prefers_visible_frame_bounds(self):
        window = _DummyWindow()
        with (
            patch.object(helpers, "_visible_frame_bounds_from_hwnd", return_value=(20, 30, 400, 500)),
            patch.object(helpers, "_window_rect_from_hwnd", return_value=(12, 24, 416, 508)),
        ):
            self.assertEqual((20, 30, 400, 500), helpers.current_window_rect(window))

    def test_apply_frame_geometry_translates_visible_bounds_to_raw_rect(self):
        captured: list[tuple[int, int, int, int, int]] = []

        def _fake_set_window_pos(_hwnd, _insert_after, x, y, width, height, flags):
            captured.append((x, y, width, height, flags))
            return 1

        window = _DummyWindow()
        with (
            patch.object(helpers, "_window_frame_insets_from_hwnd", return_value=(8, 0, 8, 8)),
            patch.object(helpers.ctypes.windll.user32, "SetWindowPos", side_effect=_fake_set_window_pos),
        ):
            applied = helpers._apply_frame_geometry_once(window, 100, 200, 1200, 800)

        self.assertTrue(applied)
        self.assertEqual(1, len(captured))
        self.assertEqual((92, 200, 1216, 808), captured[0][:4])

    def test_apply_frame_geometry_uses_raw_rect_when_visible_insets_unavailable(self):
        captured: list[tuple[int, int, int, int, int]] = []

        def _fake_set_window_pos(_hwnd, _insert_after, x, y, width, height, flags):
            captured.append((x, y, width, height, flags))
            return 1

        window = _DummyWindow()
        with (
            patch.object(helpers, "_window_frame_insets_from_hwnd", return_value=None),
            patch.object(helpers.ctypes.windll.user32, "SetWindowPos", side_effect=_fake_set_window_pos),
        ):
            applied = helpers._apply_frame_geometry_once(window, 100, 200, 1200, 800)

        self.assertTrue(applied)
        self.assertEqual(1, len(captured))
        self.assertEqual((100, 200, 1200, 800), captured[0][:4])


if __name__ == "__main__":
    unittest.main()
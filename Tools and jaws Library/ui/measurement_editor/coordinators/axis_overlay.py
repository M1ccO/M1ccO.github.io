"""Axis overlay positioning and visibility controller.

Owns positioning and visibility of the axis-pick overlay and the axis-hint
overlay that float above the 3D preview container. State is injected via
callables so the dialog remains the single source of truth for "what is the
current pick target / axis value / measurement kind".
"""

from __future__ import annotations

from collections.abc import Callable


class AxisOverlayController:
    def __init__(
        self,
        axis_pick_overlay,
        axis_hint_overlay,
        axis_overlay_btns: dict,
        preview_container,
        preview_widget,
        active_kind: Callable,
        dist_axis_value: Callable,
        diam_axis_value: Callable,
        diam_is_complete: Callable,
        current_diam_item: Callable,
        pick_target: Callable,
        on_axis_selected: Callable,
        precise_mode_enabled: Callable,
    ):
        self._axis_pick_overlay = axis_pick_overlay
        self._axis_hint_overlay = axis_hint_overlay
        self._axis_overlay_btns = axis_overlay_btns
        self._preview_container = preview_container
        self._preview_widget = preview_widget
        self._active_kind = active_kind
        self._dist_axis_value = dist_axis_value
        self._diam_axis_value = diam_axis_value
        self._diam_is_complete = diam_is_complete
        self._current_diam_item = current_diam_item
        self._pick_target = pick_target
        self._on_axis_selected = on_axis_selected
        self._precise_mode_enabled = precise_mode_enabled

    def update_buttons(self) -> None:
        if not self._axis_overlay_btns:
            return
        kind = self._active_kind()
        active = self._dist_axis_value()
        allowed = {'direct', 'x', 'y', 'z'}
        if kind == 'diameter':
            active = self._diam_axis_value()
            allowed = {'direct', 'x', 'y', 'z'}
        for val, btn in self._axis_overlay_btns.items():
            btn.setVisible(val in allowed)
            btn.setChecked(val == active and val in allowed)

    def position_axis_overlay(self) -> None:
        if self._axis_pick_overlay is None or self._preview_container is None:
            return
        self._axis_pick_overlay.adjustSize()
        sh = self._axis_pick_overlay.sizeHint()
        margin = 8
        ow = max(sh.width(), 10)
        oh = max(sh.height(), 10)
        ch = self._preview_container.height()
        target_center_y = int(ch * 0.68)
        y = max(margin, min(ch - oh - margin, target_center_y - (oh // 2)))
        self._axis_pick_overlay.setGeometry(margin, y, ow, oh)

    def position_axis_hint_overlay(self) -> None:
        if self._axis_hint_overlay is None or self._preview_container is None:
            return
        self._axis_hint_overlay.adjustSize()
        sh = self._axis_hint_overlay.sizeHint()
        margin = 10
        ow = max(sh.width(), 10)
        oh = max(sh.height(), 10)
        self._axis_hint_overlay.setGeometry(margin, margin, ow, oh)

    def update_hint_visibility(self) -> None:
        kind = self._active_kind()
        show = kind in {'length', 'diameter', 'radius', 'angle'} and self._precise_mode_enabled()
        if self._preview_widget is not None:
            try:
                self._preview_widget.set_axis_orbit_visible(bool(show))
            except Exception:
                pass
        if self._axis_hint_overlay is not None:
            self._axis_hint_overlay.setVisible(False)

    def show(self) -> None:
        self.sync_visibility()

    def sync_visibility(self) -> None:
        if self._axis_pick_overlay is None:
            return
        show = False
        kind = self._active_kind()
        if kind == 'diameter' and self._current_diam_item() is not None:
            show = True
        else:
            pt = self._pick_target()
            if pt and pt.startswith('target_xyz:'):
                show = True
        self.update_buttons()
        if show:
            self.position_axis_overlay()
            self._axis_pick_overlay.setVisible(True)
            self._axis_pick_overlay.raise_()
            try:
                self._axis_pick_overlay.activateWindow()
            except Exception:
                pass
        else:
            self._axis_pick_overlay.setVisible(False)

    def on_axis_selected(self, axis_val: str) -> None:
        kind = self._active_kind()
        self._on_axis_selected(axis_val, kind)


__all__ = ["AxisOverlayController"]

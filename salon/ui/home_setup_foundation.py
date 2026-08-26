# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import _AxisSpring
from salon.ui.home_shared import (
    _FALLBACK_VIEWPORT_HEIGHT_PX,
    _FALLBACK_VIEWPORT_WIDTH_PX,
    Adw,
    Backdrop,
    Bindings,
    Callable,
    Gio,
    Gtk,
    ScaleManager,
    SizeReporter,
    ThemeManager,
    app_config,
    tile_config,
)
from salon.ui.home_viewport import _LayoutViewport


class HomeFoundationSetup(ServiceComponent):
    def _setup_foundation(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        self._owner._application = application
        self._owner._scale_manager = scale_manager
        self._owner._theme_manager = theme_manager
        self._owner._config_path = tile_config.default_config_path()
        self._owner._settings = Gio.Settings.new(app_config.APP_ID)
        self._owner._scale = scale_manager.scale.with_safe_area(
            self._owner._settings.get_double("safe-area-percent")
        )
        self._owner._bindings = Bindings(self._owner._settings.get_value("input-bindings").unpack())
        self._owner._settings.connect(
            "changed::input-bindings", lambda *_: self._owner._reload_bindings()
        )
        self._owner._binding_capture: Callable[[str, int], None] | None = None
        self._owner._viewport_width = _FALLBACK_VIEWPORT_WIDTH_PX
        self._owner._viewport_height = _FALLBACK_VIEWPORT_HEIGHT_PX
        self._owner._row_tops: list[float] = []
        self._owner._content_height_px = 0.0
        self._owner._toast_overlay = Adw.ToastOverlay()
        self._owner.append(self._owner._toast_overlay)
        self._owner._overlay = Gtk.Overlay()
        self._owner._toast_overlay.set_child(self._owner._overlay)
        self._owner._backdrop = Backdrop()
        self._owner._overlay.set_child(self._owner._backdrop)
        self._owner._apply_wallpaper()
        for key in ("changed::wallpaper-path", "changed::wallpaper-dim"):
            self._owner._settings.connect(key, lambda *_: self._owner._apply_wallpaper())
        self._owner._viewport = _LayoutViewport()
        self._owner._viewport.set_overflow(Gtk.Overflow.HIDDEN)
        self._owner._viewport_host = SizeReporter(
            self._owner._viewport, self._owner._on_viewport_resized, propagate_minimum=False
        )
        self._owner._viewport_host.set_hexpand(True)
        self._owner._viewport_host.set_vexpand(True)
        self._owner._overlay.add_overlay(self._owner._viewport_host)
        self._owner._rows_content = Gtk.Fixed()
        self._owner._viewport.put(self._owner._rows_content, 0, 0)
        self._owner._row_anchor = _AxisSpring(
            self._owner._viewport,
            self._owner._rows_content,
            vertical=True,
            on_value=lambda _value: self._owner._update_edge_fades(),
        )

# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import *
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomeFoundationSetup(ServiceComponent):
    def _setup_foundation(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        self._application = application
        self._scale_manager = scale_manager
        self._theme_manager = theme_manager
        self._scale = scale_manager.scale
        self._config_path = tile_config.default_config_path()
        self._settings = Gio.Settings.new(app_config.APP_ID)
        self._bindings = Bindings(self._settings.get_value("input-bindings").unpack())
        self._settings.connect("changed::input-bindings", lambda *_: self._reload_bindings())
        self._binding_capture: Callable[[str, int], None] | None = None
        self._viewport_width = _FALLBACK_VIEWPORT_WIDTH_PX
        self._viewport_height = _FALLBACK_VIEWPORT_HEIGHT_PX
        self._row_tops: list[float] = []
        self._content_height_px = 0.0
        self._toast_overlay = Adw.ToastOverlay()
        self.append(self._toast_overlay)
        self._overlay = Gtk.Overlay()
        self._toast_overlay.set_child(self._overlay)
        self._backdrop = Backdrop()
        self._overlay.set_child(self._backdrop)
        self._apply_wallpaper()
        for key in ("changed::wallpaper-path", "changed::wallpaper-dim"):
            self._settings.connect(key, lambda *_: self._apply_wallpaper())
        self._viewport = _LayoutViewport()
        self._viewport.set_overflow(Gtk.Overflow.HIDDEN)
        self._viewport_host = SizeReporter(
            self._viewport, self._on_viewport_resized, propagate_minimum=False
        )
        self._viewport_host.set_hexpand(True)
        self._viewport_host.set_vexpand(True)
        self._overlay.add_overlay(self._viewport_host)
        self._rows_content = Gtk.Fixed()
        self._viewport.put(self._rows_content, 0, 0)
        self._row_anchor = _AxisSpring(
            self._viewport,
            self._rows_content,
            vertical=True,
            on_value=lambda _value: self._update_edge_fades(),
        )

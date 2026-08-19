# SPDX-License-Identifier: GPL-3.0-or-later
"""The top-level application window.

Thin by design: hosts HomeView (rows, focus, launching) and forwards the two
things HomeView can't get any other way — its own active/inactive state,
which is half of the dual return-detection signal in §6.4, and its surface,
which is how ui/scale.py finds the monitor to size the whole interface from.

Salon must never try to raise, lower, or force-focus itself (Wayland forbids
self-raising); the window only ever reacts to focus changes, never causes
them.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw  # noqa: E402

from salon.ui.home import HomeView  # noqa: E402
from salon.ui.scale import ScaleManager  # noqa: E402
from salon.ui.theme import ThemeManager  # noqa: E402


class SalonWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        application: Adw.Application,
        scale_manager: ScaleManager,
        theme_manager: ThemeManager,
    ) -> None:
        super().__init__(application=application)
        self._scale_manager = scale_manager
        self.set_title("Salon")
        self.set_default_size(1920, 1080)
        home = HomeView(application, scale_manager, theme_manager)
        self.set_content(home)
        self.fullscreen()
        self.connect("map", lambda *_: self._on_mapped(home))
        self.connect(
            "notify::is-active",
            lambda window, _pspec: home.on_window_active_changed(window.get_property("is-active")),
        )

    def _on_mapped(self, home: HomeView) -> None:
        home.on_mapped()
        surface = self.get_surface()
        if surface is not None:
            # Only now is there a surface to ask which monitor we're on, and
            # so what one design unit is worth in pixels (§7.2).
            self._scale_manager.track_surface(surface)

# SPDX-License-Identifier: GPL-3.0-or-later
"""The Salon Gio.Application."""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from salon import config  # noqa: E402
from salon.ui.scale import ScaleManager  # noqa: E402
from salon.ui.theme import ThemeManager  # noqa: E402
from salon.ui.window import SalonWindow  # noqa: E402


class SalonApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=config.APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window: SalonWindow | None = None
        self.scale_manager = ScaleManager()
        self.theme_manager = ThemeManager(Gio.Settings.new(config.APP_ID))

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._register_resources()
        self._load_css()

    def do_activate(self) -> None:
        if self._window is None:
            self._window = SalonWindow(
                application=self,
                scale_manager=self.scale_manager,
                theme_manager=self.theme_manager,
            )
        self._window.present()

    def _register_resources(self) -> None:
        resource_path = os.environ.get("SALON_GRESOURCE_PATH", config.RESOURCE_PATH)
        resource = Gio.Resource.load(resource_path)
        Gio.resources_register(resource)

    def _load_css(self) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        provider = Gtk.CssProvider()
        provider.load_from_resource(f"{config.RESOURCE_BASE_PATH}/style/salon.css")
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # The du-derived custom properties salon.css reads through var()
        # (§7.2). Installed at a higher priority so it wins, and reloaded
        # whenever the window lands on a monitor of a different height.
        self.scale_manager.install(display)
        # Above that again: the one colour token the user can change at
        # runtime (§6.8 Appearance).
        self.theme_manager.install(display)

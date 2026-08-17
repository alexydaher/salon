"""The top-level application window.

POC scope: hosts HomeView, a hardcoded, keyboard-navigable set of tiles that
actually launch. The real row/anchoring/backdrop system (M4) replaces
HomeView later; the window itself stays this thin.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw  # noqa: E402

from salon.ui.home import HomeView  # noqa: E402


class SalonWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application)
        self.set_title("Salon")
        self.set_default_size(1920, 1080)
        home = HomeView()
        self.set_content(home)
        self.fullscreen()
        self.connect("map", lambda *_: home.grab_focus())

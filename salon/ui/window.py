"""The top-level application window.

M0 scope: an empty fullscreen window in the correct background colour. Rows,
focus handling, and the backdrop arrive in later milestones (see the
implementation plan's M3/M4).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402


class SalonWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application)
        self.set_title("Salon")
        self.set_default_size(1920, 1080)
        self.set_content(Gtk.Box())
        self.fullscreen()

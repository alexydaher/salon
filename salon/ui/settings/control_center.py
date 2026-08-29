# SPDX-License-Identifier: GPL-3.0-or-later
"""Handing a system setting to GNOME (§1).

Salon is not a settings panel. Display resolution, the clock, region,
accessibility and the desktop's own power rules all belong to
gnome-control-center, and the rows that open it are marked with `↗` so
"this leaves Salon" is visible before the press rather than after it.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.core import sandbox  # noqa: E402


def open_panel(panel: str, on_error: Callable[[str], None]) -> None:
    """Inside Flatpak this goes through `flatpak-spawn --host`, the same
    prefix every launched application gets. gnome-control-center is a host
    application like any other, and there was never a reason for the one
    Salon opens itself to take a different route than the one the user pins
    to a tile."""
    try:
        Gio.Subprocess.new(
            [*sandbox.host_prefix(), "gnome-control-center", panel],
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
        )
    except GLib.Error:
        on_error("GNOME Settings isn't installed, so this can't be opened from here.")

# SPDX-License-Identifier: GPL-3.0-or-later
"""Small, failure-safe Gio desktop-entry helpers."""

from __future__ import annotations

import gi

gi.require_version("GioUnix", "2.0")
from gi.repository import GioUnix, GLib  # noqa: E402


def load(desktop_id: str) -> GioUnix.DesktopAppInfo | None:
    """Load an entry without trusting the binding's nullability.

    ``g_desktop_app_info_new()`` returns ``NULL`` when the entry is not in
    the current desktop-entry database. That is routine inside Flatpak:
    Salon discovers host entries with ``flatpak-spawn``, while Gio still
    searches the sandbox's database. PyGObject currently turns that NULL
    into ``TypeError`` instead of the annotated ``None``, so normalize both
    outcomes for every caller.
    """
    try:
        return GioUnix.DesktopAppInfo.new(desktop_id)
    except (GLib.Error, TypeError):
        return None

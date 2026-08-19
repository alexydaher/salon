# SPDX-License-Identifier: GPL-3.0-or-later
"""The installed-applications provider: one row of everything on the machine.

Off by default (`show-apps-row`). A fresh GNOME install has well over a
hundred desktop entries, and a row that long is not something anyone scrolls
on a television — search already covers "start something I didn't make a
tile for". This exists for the case the brief does name: a machine used as a
console, where the user genuinely wants every game and app reachable from
the home screen without curating a catalogue first.

It also earns its place as the third built-in by being the one that is
actually slow: it reads every `applications` directory on the system, which
is exactly the kind of work `core/provider.py`'s deadline exists for.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio  # noqa: E402

from salon.core.model import Row  # noqa: E402
from salon.core.provider import Provider, ProviderContext  # noqa: E402
from salon.services import appinfo  # noqa: E402

PROVIDER_ID = "apps"
ROW_ID = "installed-apps"
_SETTINGS_KEY = "show-apps-row"


class InstalledAppsProvider(Provider):
    id = PROVIDER_ID
    title = "All applications"
    # Last: discovered content sits below anything the user arranged.
    priority = 90

    def __init__(self, settings: Gio.Settings) -> None:
        self._settings = settings

    def rows(self, context: ProviderContext) -> list[Row]:
        if not self._settings.get_boolean(_SETTINGS_KEY):
            return []
        # Ids are namespaced with "app:" by appinfo, so an installed app can
        # never collide with a tile the user named the same thing.
        tiles = appinfo.scan_installed()
        if not tiles:
            return []
        return [
            Row(
                id=ROW_ID,
                title="All applications",
                tiles=tiles,
                provider_id=PROVIDER_ID,
                tile_aspect="square",
            )
        ]

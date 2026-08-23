# SPDX-License-Identifier: GPL-3.0-or-later
"""The recents provider: a row of recently launched tiles.

Backed by the `recent-tile-ids` GSettings key rather than a file — it's a
handful of strings rewritten on every launch, which is exactly what
GSettings is for (§5).

Ids are resolved against the user's *config*, not against rows another
provider produced. That's what lets this run concurrently with the static
provider instead of after it. The one exception is an `app:` id, which
comes from the all-apps grid or from search and is deliberately never
written into tiles.json; those are resolved against the installed-app scan,
exactly as providers/favourites.py does it.
"""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio  # noqa: E402

from salon.core.model import Row, Tile  # noqa: E402
from salon.core.provider import Provider, ProviderContext  # noqa: E402
from salon.services import appinfo  # noqa: E402

PROVIDER_ID = "recents"
ROW_ID = "recents"
_MAX_RECENTS = 8
_SETTINGS_KEY = "recent-tile-ids"


def push_recent(settings: Gio.Settings, tile_id: str) -> None:
    ids = [i for i in settings.get_strv(_SETTINGS_KEY) if i != tile_id]
    ids.insert(0, tile_id)
    settings.set_strv(_SETTINGS_KEY, ids[:_MAX_RECENTS])


class RecentsProvider(Provider):
    id = PROVIDER_ID
    title = "Recents"
    # First row on the screen: the thing most likely to be wanted again is
    # the thing most recently used.
    priority = 10

    def __init__(self, settings: Gio.Settings) -> None:
        self._settings = settings

    def rows(self, context: ProviderContext) -> list[Row]:
        tiles_by_id: dict[str, Tile] = {
            tile.id: tile for row in context.config.rows for tile in row.tiles
        }
        wanted = self._settings.get_strv(_SETTINGS_KEY)

        # Anything started from the all-apps grid or from search has no
        # entry in tiles.json — its id is `app:something.desktop`, and
        # resolving only against the catalogue silently dropped every one of
        # them. The row then claimed the user had recently launched nothing
        # but the four tiles they had made by hand, which is the opposite of
        # what Recents is for. Resolved the same way Favourites does it, and
        # the installed-app scan is only paid for when there is something to
        # resolve with it.
        missing = [i for i in wanted if i not in tiles_by_id and i.startswith(appinfo.ID_PREFIX)]
        if missing:
            tiles_by_id.update({tile.id: tile for tile in appinfo.scan_installed()})

        tiles = [tiles_by_id[i] for i in wanted if i in tiles_by_id]
        # An empty row is worse than no row — it reads as a rendering fault.
        if not tiles:
            return []
        return [Row(id=ROW_ID, title="Recents", tiles=tiles, provider_id=PROVIDER_ID)]

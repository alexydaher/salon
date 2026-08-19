# SPDX-License-Identifier: GPL-3.0-or-later
"""The favourites provider: a pinned row the user builds by hand.

Recents answers "what did I just use"; this answers "what do I always
use", which is a different question and the one a television actually gets
asked. It sits above recents so the first thing under the cursor at boot is
the handful of things this household watches, not whatever was opened last.

Backed by the `favourite-tile-ids` GSettings key and populated from the tile
options menu (OPTIONS on any tile, anywhere — home screen or the all-apps
grid). Ids are resolved against the user's *config*, exactly as recents
does, so this can run concurrently with every other provider instead of
after them: a tile can only be a favourite if it exists on disk.

Order is the user's, not the catalogue's — the list is stored in the order
things were pinned, and the row is built by walking that list.
"""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio  # noqa: E402

from salon.core.model import Row, Tile  # noqa: E402
from salon.core.provider import Provider, ProviderContext  # noqa: E402
from salon.services import appinfo  # noqa: E402

PROVIDER_ID = "favourites"
ROW_ID = "favourites"
_SETTINGS_KEY = "favourite-tile-ids"


def favourite_ids(settings: Gio.Settings) -> list[str]:
    return list(settings.get_strv(_SETTINGS_KEY))


def is_favourite(settings: Gio.Settings, tile_id: str) -> bool:
    return tile_id in settings.get_strv(_SETTINGS_KEY)


def toggle_favourite(settings: Gio.Settings, tile_id: str) -> bool:
    """Pin or unpin, returning the state it ended up in."""
    ids = list(settings.get_strv(_SETTINGS_KEY))
    if tile_id in ids:
        ids.remove(tile_id)
        settings.set_strv(_SETTINGS_KEY, ids)
        return False
    ids.append(tile_id)
    settings.set_strv(_SETTINGS_KEY, ids)
    return True


def forget(settings: Gio.Settings, tile_id: str) -> None:
    """Drop an id that no longer resolves — called when a tile is deleted,
    so the key doesn't accumulate ids for things that stopped existing."""
    ids = [i for i in settings.get_strv(_SETTINGS_KEY) if i != tile_id]
    settings.set_strv(_SETTINGS_KEY, ids)


class FavouritesProvider(Provider):
    id = PROVIDER_ID
    title = "Favourites"
    # Ahead of recents (10): a pinned row is a deliberate choice and should
    # not be pushed down the screen by whatever happened to run last.
    priority = 5

    def __init__(self, settings: Gio.Settings) -> None:
        self._settings = settings

    def rows(self, context: ProviderContext) -> list[Row]:
        tiles_by_id: dict[str, Tile] = {
            tile.id: tile for row in context.config.rows for tile in row.tiles
        }
        wanted = favourite_ids(self._settings)

        # An app pinned from the all-apps grid has no entry in tiles.json —
        # it isn't a tile the user made, it's an application that exists.
        # Rather than silently writing one into their catalogue behind their
        # back, resolve those ids against the installed-app scan, and only
        # pay for that scan when there is at least one to resolve. This
        # already runs on a worker thread under the provider deadline.
        missing = [i for i in wanted if i not in tiles_by_id and i.startswith(appinfo.ID_PREFIX)]
        if missing:
            tiles_by_id.update({tile.id: tile for tile in appinfo.scan_installed()})

        tiles = [tiles_by_id[i] for i in wanted if i in tiles_by_id]
        # An empty row is worse than no row — it reads as a rendering fault,
        # and until something is pinned there is nothing to say.
        if not tiles:
            return []
        return [Row(id=ROW_ID, title="Favourites", tiles=tiles, provider_id=PROVIDER_ID)]

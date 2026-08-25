# SPDX-License-Identifier: GPL-3.0-or-later
"""Provider composing installed games from supported library adapters."""

from __future__ import annotations

import json
import sqlite3

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio  # noqa: E402

from salon.core import gamelib  # noqa: E402
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile  # noqa: E402
from salon.core.provider import Provider, ProviderContext  # noqa: E402
from salon.providers.game_sources import (  # noqa: E402
    heroic_games,
    lutris_games,
    retroarch_games,
    steam_games,
    steam_roots,
)

PROVIDER_ID = "games"
ROW_ID = "games"
_SETTINGS_KEY = "show-games-row"
_MAX_GAMES = 60

__all__ = [
    "GamesProvider",
    "collect_games",
    "heroic_games",
    "lutris_games",
    "retroarch_games",
    "steam_games",
    "steam_roots",
]


def _tile(game: gamelib.LibraryGame) -> Tile:
    return Tile(
        id=game.id,
        title=game.title,
        subtitle=game.source,
        launch=LaunchSpec(
            kind=LaunchKind.COMMAND,
            target=game.launch[0],
            args=tuple(game.launch[1:]),
            fullscreen=True,
        ),
        artwork=game.artwork,
        icon_name=None,
        accent=None,
        tags=(game.source.lower(),),
    )


def collect_games() -> list[gamelib.LibraryGame]:
    """Collect every source independently and return a stable title order."""
    found: list[gamelib.LibraryGame] = []
    for source in (steam_games, heroic_games, lutris_games, retroarch_games):
        try:
            found.extend(source())
        except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError):
            continue
    found.sort(key=lambda game: (game.title.casefold(), game.id))
    return found


class GamesProvider(Provider):
    id = PROVIDER_ID
    title = "Games"
    priority = 80

    def __init__(self, settings: Gio.Settings) -> None:
        self._settings = settings

    def rows(self, context: ProviderContext) -> list[Row]:
        if not self._settings.get_boolean(_SETTINGS_KEY):
            return []
        games = collect_games()
        if not games:
            return []
        return [
            Row(
                id=ROW_ID,
                title="Games",
                tiles=[_tile(game) for game in games[:_MAX_GAMES]],
                provider_id=PROVIDER_ID,
                tile_aspect="poster",
            )
        ]

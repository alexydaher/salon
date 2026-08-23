# SPDX-License-Identifier: GPL-3.0-or-later
"""The games provider: every installed game, from every library, as tiles.

`core/gamelib.py` holds the parsing; this holds the filesystem knowledge —
where each launcher keeps its catalogue, where it keeps its artwork, and
what argv actually starts a game.

Three things shape the design:

* **Never talk to a launcher, only to its files.** Asking Steam for its
  library means Steam must be running, which on a television it is not
  until something starts it. Every path below is a file the launcher leaves
  on disk whether it is running or not.
* **Each source fails to nothing.** A missing Heroic, a corrupt playlist
  and an unreadable Lutris database each cost their own games and nothing
  else. `core/provider.py` already isolates the provider as a whole; this
  isolates the sources within it, because "my Steam games vanished when I
  uninstalled RetroArch" is exactly the kind of report a plugin layer is
  supposed to make impossible.
* **Artwork is local or nothing.** Steam and Heroic have already downloaded
  cover art for everything installed; using what is on disk means a games
  row that looks right on first paint with no network at all.

Off by default. A machine with no games gains an empty row it did not ask
for, and the scan costs a directory walk per library — `show-games-row`
turns it on, and Settings → Providers explains what it found.

**Untested against a real library**, like `core/gamelib.py` — see the note
there. Every path here was written from the documented layouts.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio  # noqa: E402

from salon.core import gamelib  # noqa: E402
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile  # noqa: E402
from salon.core.provider import Provider, ProviderContext  # noqa: E402

PROVIDER_ID = "games"
ROW_ID = "games"
_SETTINGS_KEY = "show-games-row"

# Steam's own cap on a home-screen row. A library of nine hundred games is
# not something anyone scrolls with a D-pad; the all-apps grid's shape is
# what that wants, and search finds any of them by name regardless.
_MAX_GAMES = 60


def _home() -> Path:
    return Path(os.environ.get("HOME", str(Path.home())))


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(_home() / ".local" / "share")))


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config")))


def _read(path: Path, limit: int = 4 * 1024 * 1024) -> str | None:
    """A file, or None for any reason at all.

    Bounded: these are other applications' files, and a games row is not
    worth reading an arbitrarily large one into memory over.
    """
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# --- Steam ---------------------------------------------------------------

def steam_roots() -> list[Path]:
    """Where Steam itself is installed. Both packagings, and the symlink
    farm `~/.steam` keeps for compatibility with everything ever written
    against it."""
    candidates = [
        _data_home() / "Steam",
        _home() / ".steam" / "steam",
        _home() / ".steam" / "root",
        _home() / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
    ]
    seen: set[Path] = set()
    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not (resolved / "steamapps").is_dir():
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def _steam_command(root: Path) -> tuple[str, ...]:
    """How to start Steam for a game in this root.

    A Flatpak Steam cannot be started by running `steam`, and a native one
    cannot be started through `flatpak run`; getting this wrong is a tile
    that does nothing at all.
    """
    if ".var/app/com.valvesoftware.Steam" in str(root):
        return ("flatpak", "run", "com.valvesoftware.Steam")
    return ("steam",)


def _steam_artwork(root: Path, appid: str) -> str | None:
    """The cover Steam already downloaded, if it did.

    Ordered by what looks best on a tile. A user's own Steam Grid override
    wins outright — someone who went and set custom art meant it. Then the
    portrait library capsule, then the landscape header, which is the one
    every game has.

    Two cache layouts, because Steam changed it in 2024 from a flat
    directory of `<appid>_<kind>.jpg` to one directory per appid.
    """
    cache = root / "appcache" / "librarycache"
    candidates = [
        *(
            grid / f"{appid}p{suffix}"
            for grid in _steam_grid_dirs(root)
            for suffix in (".jpg", ".png")
        ),
        cache / appid / "library_600x900.jpg",
        cache / f"{appid}_library_600x900.jpg",
        cache / appid / "header.jpg",
        cache / f"{appid}_header.jpg",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _steam_grid_dirs(root: Path) -> Iterator[Path]:
    """Every logged-in account's custom-artwork directory."""
    userdata = root / "userdata"
    try:
        entries = sorted(userdata.iterdir())
    except OSError:
        return
    for entry in entries:
        grid = entry / "config" / "grid"
        if grid.is_dir():
            yield grid


def steam_games() -> list[gamelib.LibraryGame]:
    games: list[gamelib.LibraryGame] = []
    seen: set[str] = set()
    for root in steam_roots():
        command = _steam_command(root)
        vdf = _read(root / "steamapps" / "libraryfolders.vdf") or ""
        # The install root is always a library, whether or not it lists
        # itself — on a single-drive install it frequently does not.
        libraries = [root, *(Path(p) for p in gamelib.library_paths(vdf))]
        for library in libraries:
            steamapps = library / "steamapps"
            try:
                manifests = sorted(steamapps.glob("appmanifest_*.acf"))
            except OSError:
                continue
            for manifest in manifests:
                text = _read(manifest)
                app = gamelib.steam_app(text) if text else None
                if app is None or app.appid in seen:
                    continue
                seen.add(app.appid)
                games.append(
                    gamelib.LibraryGame(
                        id=f"steam:{app.appid}",
                        title=app.name,
                        source="Steam",
                        launch=(*command, "-applaunch", app.appid),
                        artwork=_steam_artwork(root, app.appid),
                    )
                )
    return games


# --- Heroic --------------------------------------------------------------

def heroic_games() -> list[gamelib.LibraryGame]:
    bases = [
        _config_home() / "heroic",
        _home() / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic",
    ]
    games: list[gamelib.LibraryGame] = []
    for base in bases:
        cache = base / "store_cache"
        for filename, runner in (
            ("legendary_library.json", "legendary"),
            ("gog_library.json", "gog"),
            ("nile_library.json", "nile"),
        ):
            text = _read(cache / filename)
            if text:
                games.extend(gamelib.heroic_games(text, runner))
    return games


# --- Lutris --------------------------------------------------------------

def lutris_games() -> list[gamelib.LibraryGame]:
    """Lutris keeps its library in SQLite, so this is a query rather than a
    parse — which is why it has no counterpart in core/gamelib.py.

    Opened read-only through a URI so a Lutris that happens to be running
    is neither blocked nor corrupted, and so a database mid-write fails
    this source rather than the provider.
    """
    candidates = [
        _data_home() / "lutris" / "pga.db",
        _home() / ".var" / "app" / "net.lutris.Lutris" / "data" / "lutris" / "pga.db",
    ]
    games: list[gamelib.LibraryGame] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        except sqlite3.Error:
            continue
        try:
            rows = connection.execute(
                "SELECT slug, name, installed, coverart FROM games "
                "WHERE installed = 1 AND hidden = 0 ORDER BY name"
            ).fetchall()
        except sqlite3.Error:
            # Schema drift across Lutris versions costs Lutris's games and
            # nothing else.
            rows = []
        finally:
            connection.close()
        for slug, name, _installed, cover in rows:
            if not slug or not name:
                continue
            art = str(cover) if cover else None
            games.append(
                gamelib.LibraryGame(
                    id=f"lutris:{slug}",
                    title=str(name),
                    source="Lutris",
                    launch=("lutris", f"lutris:rungame/{slug}"),
                    artwork=art if art and Path(art).is_file() else None,
                )
            )
    return games


# --- RetroArch -----------------------------------------------------------

def retroarch_games() -> list[gamelib.LibraryGame]:
    bases = [
        _config_home() / "retroarch",
        _home() / ".var" / "app" / "org.libretro.RetroArch" / "config" / "retroarch",
    ]
    games: list[gamelib.LibraryGame] = []
    for base in bases:
        playlists = base / "playlists"
        try:
            files = sorted(playlists.glob("*.lpl"))
        except OSError:
            continue
        for playlist in files:
            text = _read(playlist)
            if text:
                games.extend(gamelib.retroarch_games(text, playlist.name))
    return games


# --- the provider --------------------------------------------------------

def _tile(game: gamelib.LibraryGame) -> Tile:
    return Tile(
        id=game.id,
        title=game.title,
        subtitle=game.source,
        launch=LaunchSpec(
            kind=LaunchKind.COMMAND,
            target=game.launch[0],
            args=tuple(game.launch[1:]),
            # A game is the one thing on a television that is unambiguously
            # meant to own the whole screen.
            fullscreen=True,
        ),
        artwork=game.artwork,
        icon_name=None,
        accent=None,
        tags=(game.source.lower(),),
    )


def collect_games() -> list[gamelib.LibraryGame]:
    """Every source, each isolated from the others.

    A source that raises contributes nothing and says nothing: it is not
    the provider's failure, and reporting "Lutris is broken" on a machine
    with no Lutris would be noise. The provider's own outcome already
    reports how many games were found in total.
    """
    found: list[gamelib.LibraryGame] = []
    for source in (steam_games, heroic_games, lutris_games, retroarch_games):
        try:
            found.extend(source())
        except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError):
            continue
    # Stable and scannable: a games row is browsed, not ranked.
    found.sort(key=lambda game: (game.title.casefold(), game.id))
    return found


class GamesProvider(Provider):
    id = PROVIDER_ID
    title = "Games"
    # Above the all-applications row and below anything hand-arranged: on a
    # machine used as a console this is the row that matters, but it is
    # still discovered content.
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
                # Portrait: Steam and Heroic both ship 600x900 cover art,
                # and a poster row is what that artwork was drawn for.
                tile_aspect="poster",
            )
        ]

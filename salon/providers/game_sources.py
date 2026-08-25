# SPDX-License-Identifier: GPL-3.0-or-later
"""Filesystem adapters for installed game libraries."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from salon.core import gamelib


def _home() -> Path:
    return Path(os.environ.get("HOME", str(Path.home())))


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(_home() / ".local" / "share")))


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config")))


def _read(path: Path, limit: int = 4 * 1024 * 1024) -> str | None:
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def steam_roots() -> list[Path]:
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
        if resolved not in seen and (resolved / "steamapps").is_dir():
            seen.add(resolved)
            roots.append(resolved)
    return roots


def _steam_command(root: Path) -> tuple[str, ...]:
    if ".var/app/com.valvesoftware.Steam" in str(root):
        return ("flatpak", "run", "com.valvesoftware.Steam")
    return ("steam",)


def _steam_grid_dirs(root: Path) -> Iterator[Path]:
    try:
        entries = sorted((root / "userdata").iterdir())
    except OSError:
        return
    for entry in entries:
        grid = entry / "config" / "grid"
        if grid.is_dir():
            yield grid


def _steam_artwork(root: Path, appid: str) -> str | None:
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
    return next((str(path) for path in candidates if path.is_file()), None)


def steam_games() -> list[gamelib.LibraryGame]:
    games: list[gamelib.LibraryGame] = []
    seen: set[str] = set()
    for root in steam_roots():
        text = _read(root / "steamapps" / "libraryfolders.vdf") or ""
        libraries = [root, *(Path(path) for path in gamelib.library_paths(text))]
        for library in libraries:
            for manifest in sorted((library / "steamapps").glob("appmanifest_*.acf")):
                contents = _read(manifest)
                app = gamelib.steam_app(contents) if contents else None
                if app is None or app.appid in seen:
                    continue
                seen.add(app.appid)
                games.append(
                    gamelib.LibraryGame(
                        id=f"steam:{app.appid}",
                        title=app.name,
                        source="Steam",
                        launch=(*_steam_command(root), "-applaunch", app.appid),
                        artwork=_steam_artwork(root, app.appid),
                    )
                )
    return games


def heroic_games() -> list[gamelib.LibraryGame]:
    bases = [
        _config_home() / "heroic",
        _home() / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic",
    ]
    games: list[gamelib.LibraryGame] = []
    for base in bases:
        for filename, runner in (
            ("legendary_library.json", "legendary"),
            ("gog_library.json", "gog"),
            ("nile_library.json", "nile"),
        ):
            text = _read(base / "store_cache" / filename)
            if text:
                games.extend(gamelib.heroic_games(text, runner))
    return games


def lutris_games() -> list[gamelib.LibraryGame]:
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
            rows = []
        finally:
            connection.close()
        for slug, name, _installed, cover in rows:
            if not slug or not name:
                continue
            artwork = str(cover) if cover else None
            games.append(
                gamelib.LibraryGame(
                    id=f"lutris:{slug}",
                    title=str(name),
                    source="Lutris",
                    launch=("lutris", f"lutris:rungame/{slug}"),
                    artwork=artwork if artwork and Path(artwork).is_file() else None,
                )
            )
    return games


def retroarch_games() -> list[gamelib.LibraryGame]:
    bases = [
        _config_home() / "retroarch",
        _home() / ".var" / "app" / "org.libretro.RetroArch" / "config" / "retroarch",
    ]
    games: list[gamelib.LibraryGame] = []
    for base in bases:
        for playlist in sorted((base / "playlists").glob("*.lpl")):
            text = _read(playlist)
            if text:
                games.extend(gamelib.retroarch_games(text, playlist.name))
    return games

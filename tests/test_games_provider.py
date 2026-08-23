# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the game libraries on disk (salon/providers/games.py).

`core/gamelib.py` is tested against file *contents*; this is tested against
a file *tree*, because the half that goes wrong in practice is where things
live: which directory Steam's Flatpak uses, that the install root is a
library even when it does not list itself, and that a missing launcher
costs nothing.

The tree below is built from the documented layouts rather than copied off
a real installation — there is no Steam on the machine this was written on.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("gi")

from salon.providers import games  # noqa: E402


def _manifest(appid: str, name: str, flags: str = "4") -> str:
    return f'"AppState" {{ "appid" "{appid}" "name" "{name}" "StateFlags" "{flags}" }}'


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    return tmp_path


def _make_steam(home: Path, *, second_library: Path | None = None) -> Path:
    root = home / ".local" / "share" / "Steam"
    (root / "steamapps").mkdir(parents=True)
    entries = [f'"0" {{ "path" "{root}" }}']
    if second_library is not None:
        (second_library / "steamapps").mkdir(parents=True)
        entries.append(f'"1" {{ "path" "{second_library}" }}')
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders" { ' + " ".join(entries) + " }"
    )
    return root


def test_nothing_installed_finds_nothing(fake_home: Path) -> None:
    """The common case on a desktop, and it must not raise."""
    assert games.collect_games() == []
    assert games.steam_roots() == []


def test_steam_games_across_two_libraries(fake_home: Path, tmp_path: Path) -> None:
    second = tmp_path / "mnt" / "games"
    root = _make_steam(fake_home, second_library=second)
    (root / "steamapps" / "appmanifest_620.acf").write_text(_manifest("620", "Portal 2"))
    (second / "steamapps" / "appmanifest_400.acf").write_text(_manifest("400", "Portal"))
    (root / "steamapps" / "appmanifest_228980.acf").write_text(
        _manifest("228980", "Steamworks Common Redistributables")
    )

    found = games.steam_games()
    assert [game.title for game in found] == ["Portal 2", "Portal"]
    assert found[0].id == "steam:620"
    assert found[0].launch == ("steam", "-applaunch", "620")


def test_the_install_root_counts_even_if_it_does_not_list_itself(fake_home: Path) -> None:
    """A single-drive install frequently has a libraryfolders.vdf that
    names only other drives, or none at all."""
    root = fake_home / ".local" / "share" / "Steam"
    (root / "steamapps").mkdir(parents=True)
    (root / "steamapps" / "libraryfolders.vdf").write_text('"libraryfolders" { }')
    (root / "steamapps" / "appmanifest_620.acf").write_text(_manifest("620", "Portal 2"))
    assert [game.title for game in games.steam_games()] == ["Portal 2"]


def test_a_flatpak_steam_is_launched_through_flatpak(fake_home: Path) -> None:
    """`steam -applaunch` does not exist on a machine whose Steam is a
    Flatpak, and a tile that runs it does nothing at all."""
    root = fake_home / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
    (root / "steamapps").mkdir(parents=True)
    (root / "steamapps" / "appmanifest_620.acf").write_text(_manifest("620", "Portal 2"))
    found = games.steam_games()
    assert found[0].launch == ("flatpak", "run", "com.valvesoftware.Steam", "-applaunch", "620")


def test_a_game_in_two_libraries_is_listed_once(fake_home: Path, tmp_path: Path) -> None:
    second = tmp_path / "mnt" / "games"
    root = _make_steam(fake_home, second_library=second)
    (root / "steamapps" / "appmanifest_620.acf").write_text(_manifest("620", "Portal 2"))
    (second / "steamapps" / "appmanifest_620.acf").write_text(_manifest("620", "Portal 2"))
    assert len(games.steam_games()) == 1


def test_steam_artwork_prefers_a_users_own_override(fake_home: Path) -> None:
    """Someone who went and set custom Steam Grid art meant it."""
    root = _make_steam(fake_home)
    (root / "steamapps" / "appmanifest_620.acf").write_text(_manifest("620", "Portal 2"))
    cache = root / "appcache" / "librarycache" / "620"
    cache.mkdir(parents=True)
    (cache / "library_600x900.jpg").write_bytes(b"official")
    grid = root / "userdata" / "12345" / "config" / "grid"
    grid.mkdir(parents=True)
    (grid / "620p.jpg").write_bytes(b"mine")
    assert games.steam_games()[0].artwork == str(grid / "620p.jpg")


def test_steam_falls_back_through_both_cache_layouts(fake_home: Path) -> None:
    """Steam moved from a flat directory to one per appid in 2024, and both
    are on real machines."""
    root = _make_steam(fake_home)
    (root / "steamapps" / "appmanifest_620.acf").write_text(_manifest("620", "Portal 2"))
    cache = root / "appcache" / "librarycache"
    cache.mkdir(parents=True)
    (cache / "620_header.jpg").write_bytes(b"old layout")
    assert games.steam_games()[0].artwork == str(cache / "620_header.jpg")


def test_heroic_and_retroarch_are_read_from_their_own_trees(fake_home: Path) -> None:
    cache = fake_home / ".config" / "heroic" / "store_cache"
    cache.mkdir(parents=True)
    (cache / "legendary_library.json").write_text(
        json.dumps({"library": [{"app_name": "x", "title": "Hades", "is_installed": True}]})
    )
    playlists = fake_home / ".config" / "retroarch" / "playlists"
    playlists.mkdir(parents=True)
    (playlists / "Nintendo - SNES.lpl").write_text(
        json.dumps({"items": [{"path": "/roms/z.sfc", "label": "Zelda", "core_path": "DETECT"}]})
    )
    titles = [game.title for game in games.collect_games()]
    assert titles == ["Hades", "Zelda"]


def test_lutris_is_read_read_only(fake_home: Path) -> None:
    path = fake_home / ".local" / "share" / "lutris" / "pga.db"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE games (id INTEGER PRIMARY KEY, slug TEXT, name TEXT, "
        "installed INTEGER, hidden INTEGER, coverart TEXT)"
    )
    connection.executemany(
        "INSERT INTO games (slug, name, installed, hidden, coverart) VALUES (?,?,?,?,?)",
        [("hollow-knight", "Hollow Knight", 1, 0, None), ("uninstalled", "Gone", 0, 0, None)],
    )
    connection.commit()
    connection.close()

    found = games.lutris_games()
    assert [game.title for game in found] == ["Hollow Knight"]
    assert found[0].launch == ("lutris", "lutris:rungame/hollow-knight")


def test_a_broken_source_costs_only_its_own_games(fake_home: Path) -> None:
    """"My Steam games vanished when I uninstalled RetroArch" is the report
    this exists to make impossible."""
    root = _make_steam(fake_home)
    (root / "steamapps" / "appmanifest_620.acf").write_text(_manifest("620", "Portal 2"))
    playlists = fake_home / ".config" / "retroarch" / "playlists"
    playlists.mkdir(parents=True)
    (playlists / "Broken.lpl").write_text("{ this is not json")
    lutris = fake_home / ".local" / "share" / "lutris" / "pga.db"
    lutris.parent.mkdir(parents=True)
    lutris.write_bytes(b"not a database at all")

    assert [game.title for game in games.collect_games()] == ["Portal 2"]

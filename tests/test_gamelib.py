# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading other launchers' game libraries (salon/core/gamelib.py).

The rules worth testing are the filters, not the parsing: which entries are
games and which are runtimes, and which are installed rather than merely
owned. Getting those wrong does not produce an error, it produces a home
screen offering to launch "Steamworks Common Redistributables" next to two
hundred games the machine does not have.

Fixtures, not real files — there is no Steam on the machine this was written
on. See the module docstring in core/gamelib.py.
"""

from __future__ import annotations

import json

from salon.core.gamelib import (
    heroic_games,
    library_paths,
    parse_vdf,
    retroarch_games,
    steam_app,
)

MODERN_LIBRARYFOLDERS = """
"libraryfolders"
{
	"0"
	{
		"path"		"/home/alexy/.local/share/Steam"
		"label"		""
		"apps"
		{
			"620"		"7351678485"
			"228980"		"52734688"
		}
	}
	"1"
	{
		"path"		"/mnt/games/SteamLibrary"
		"apps"
		{
			"1145360"		"12345"
		}
	}
}
"""


def _manifest(appid: str, name: str, flags: str = "4") -> str:
    return f"""
"AppState"
{{
	"appid"		"{appid}"
	"Universe"		"1"
	"name"		"{name}"
	"StateFlags"		"{flags}"
	"installdir"		"{name}"
}}
"""


def test_nested_blocks_survive_parsing() -> None:
    """The nesting is the meaning: a library's "apps" block has appids for
    keys, and a parser that flattened it could not tell those from the
    library's own fields."""
    parsed = parse_vdf(MODERN_LIBRARYFOLDERS)
    folders = parsed["libraryfolders"]
    assert isinstance(folders, dict)
    assert folders["0"]["apps"]["620"] == "7351678485"
    assert folders["1"]["path"] == "/mnt/games/SteamLibrary"


def test_every_library_root_is_found() -> None:
    assert library_paths(MODERN_LIBRARYFOLDERS) == [
        "/home/alexy/.local/share/Steam",
        "/mnt/games/SteamLibrary",
    ]


def test_the_ancient_shape_still_reads() -> None:
    """Valve's older libraryfolders.vdf put the path in the value."""
    ancient = '"LibraryFolders" { "TimeNextStatsReport" "1" "1" "/mnt/second" }'
    assert library_paths(ancient) == ["/mnt/second"]


def test_comments_and_escapes_do_not_derail_it() -> None:
    text = '"AppState" { // a comment\n "appid" "1" "name" "Say \\"Hi\\"" "StateFlags" "4" }'
    app = steam_app(text)
    assert app is not None
    assert app.name == 'Say "Hi"'


def test_a_truncated_file_yields_what_it_can() -> None:
    """One corrupt manifest must cost one game, not the row."""
    assert parse_vdf('"AppState" { "appid" "620" "name"') == {"AppState": {"appid": "620"}}


def test_an_installed_game_is_a_game() -> None:
    app = steam_app(_manifest("620", "Portal 2"))
    assert app is not None
    assert (app.appid, app.name) == ("620", "Portal 2")


def test_a_queued_download_is_not_installed() -> None:
    """A manifest appears the moment a download is queued. StateFlags 1026
    is 'update started' without StateFullyInstalled."""
    assert steam_app(_manifest("620", "Portal 2", flags="1026")) is None


def test_redistributables_and_runtimes_are_not_games() -> None:
    assert steam_app(_manifest("228980", "Steamworks Common Redistributables")) is None
    assert steam_app(_manifest("1628350", "Steam Linux Runtime 3.0 (sniper)")) is None
    assert steam_app(_manifest("99999", "Proton 9.0")) is None


def test_a_game_that_merely_starts_like_a_runtime_is_kept() -> None:
    """The filter matches a prefix rather than a substring, so a game
    genuinely called this is not swallowed by it."""
    app = steam_app(_manifest("42", "Protonwar"))
    assert app is not None
    assert app.name == "Protonwar"


def test_heroic_lists_only_installed_titles() -> None:
    """An Epic account collects years of free weekly giveaways; the cache
    holds all of them and the machine has almost none."""
    library = json.dumps(
        {
            "library": [
                {
                    "app_name": "Fortnite",
                    "title": "Fortnite",
                    "is_installed": False,
                },
                {
                    "app_name": "abc123",
                    "title": "Hades",
                    "is_installed": True,
                    "art_square": "https://example.com/hades.png",
                },
            ]
        }
    )
    games = heroic_games(library, "legendary")
    assert [g.title for g in games] == ["Hades"]
    assert games[0].id == "heroic:legendary:abc123"
    assert games[0].launch == ("xdg-open", "heroic://launch/legendary/abc123")
    assert games[0].artwork == "https://example.com/hades.png"


def test_heroic_nonsense_is_no_games_rather_than_an_exception() -> None:
    assert heroic_games("not json at all", "gog") == []
    assert heroic_games("[]", "gog") == []


def test_a_retroarch_playlist_becomes_launchable_argv() -> None:
    playlist = json.dumps(
        {
            "default_core_path": "/usr/lib/libretro/snes9x_libretro.so",
            "items": [
                {"path": "/roms/Chrono Trigger.sfc", "label": "Chrono Trigger",
                 "core_path": "DETECT"},
                {"path": "/roms/Zelda.sfc", "label": "Zelda",
                 "core_path": "/usr/lib/libretro/bsnes_libretro.so"},
            ],
        }
    )
    games = retroarch_games(playlist, "Nintendo - SNES.lpl")
    assert [g.title for g in games] == ["Chrono Trigger", "Zelda"]
    # DETECT is not a core: RetroArch can only resolve it from a playlist it
    # is reading itself, so the ROM is handed over without one.
    assert games[0].launch == ("retroarch", "/roms/Chrono Trigger.sfc")
    assert games[1].launch == (
        "retroarch", "-L", "/usr/lib/libretro/bsnes_libretro.so", "/roms/Zelda.sfc",
    )
    assert games[0].source == "Nintendo - SNES"

# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading the game libraries other launchers keep on disk. Pure — no gi.

Salon's competition for anyone with a controller is not another desktop
launcher, it is Flex Launcher and Plasma Bigscreen, and what people build
those into is a console. A console whose home screen cannot list the games
already installed on the machine is a curiosity: every one of them has to be
typed in by hand as a `COMMAND` tile, with its own artwork found and
downloaded separately, and then done again for the next game.

Four libraries cover almost every Linux game install, and all four keep
their catalogue in a file this can read without asking the launcher to be
running:

* **Steam** — `libraryfolders.vdf` names the library roots, and each root's
  `steamapps/appmanifest_<appid>.acf` names one installed game. Both are
  Valve's KeyValues format, which is what `parse_vdf` is for.
* **Heroic** (Epic and GOG) — JSON store caches.
* **Lutris** — an SQLite database, read by the provider rather than here.
* **RetroArch** — playlists, which are JSON.

This module holds the parsing and the filtering, because those are the
parts with rules worth testing: which entries are games and which are
runtimes, which are installed and which are merely known about.

**Untested against a real library.** There is no Steam, Heroic, Lutris or
RetroArch on the machine this was written on, so every test below runs
against fixtures written from the file formats rather than against files a
launcher produced. The formats are stable and long-documented, but that is
a weaker claim than the rest of the codebase makes and it is recorded here
rather than left to be discovered.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# Valve's KeyValues: quoted tokens, braces for nesting, // to end of line.
# Written as a tokenizer rather than a regex-per-field because the nesting
# is what carries the meaning — `libraryfolders.vdf` has an "apps" block
# inside each library whose keys are appids, and a field-scraping regex
# cannot tell those from the library's own keys.
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*', re.DOTALL)
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}

# StateFlags bit 2 (value 4) is StateFullyInstalled. A manifest exists from
# the moment a download is queued, so without this check a library of five
# games and forty wishlisted ones lists forty-five.
STATE_FULLY_INSTALLED = 4

# Appids that are infrastructure rather than games. Steam installs these
# into the same library with the same kind of manifest, and a home screen
# offering to launch "Steamworks Common Redistributables" is a bug report.
TOOL_APPIDS = frozenset(
    {
        "228980",  # Steamworks Common Redistributables
        "1070560",  # Steam Linux Runtime 1.0 (scout)
        "1391110",  # Steam Linux Runtime 2.0 (soldier)
        "1628350",  # Steam Linux Runtime 3.0 (sniper)
        "1493710",  # Proton Experimental
    }
)

# Anything whose name begins like this is a compatibility tool. Matched on a
# prefix rather than a substring so a game legitimately called something
# like "Protonwar" is not swallowed by it.
_TOOL_PREFIXES = ("Proton ", "Proton-", "Steam Linux Runtime", "Steamworks ")


def _unescape(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            out.append(_ESCAPES.get(text[index + 1], text[index + 1]))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def parse_vdf(text: str) -> dict[str, object]:
    """Valve KeyValues to nested dicts. Never raises on malformed input.

    A truncated or corrupt file returns whatever was parseable up to the
    damage rather than an exception: this runs inside a provider, where the
    cost of being strict is that one bad file removes the whole games row
    instead of one game from it.
    """
    root: dict[str, object] = {}
    stack: list[dict[str, object]] = [root]
    pending: str | None = None
    for match in _TOKEN.finditer(text):
        quoted, brace = match.group(1), match.group(2)
        if quoted is not None:
            value = _unescape(quoted)
            if pending is None:
                pending = value
            else:
                stack[-1][pending] = value
                pending = None
        elif brace == "{":
            child: dict[str, object] = {}
            if pending is not None:
                stack[-1][pending] = child
                pending = None
            stack.append(child)
        elif brace == "}":
            pending = None
            if len(stack) > 1:
                stack.pop()
    return root


def _section(node: object) -> dict[str, object]:
    return node if isinstance(node, dict) else {}


def _string(node: object) -> str:
    return node if isinstance(node, str) else ""


def library_paths(vdf_text: str) -> list[str]:
    """Every Steam library root named in `libraryfolders.vdf`.

    Handles both shapes Valve has shipped: the modern one where each
    numbered entry is a block with a "path", and the ancient one where the
    numbered key *is* the path.
    """
    parsed = parse_vdf(vdf_text)
    folders = _section(parsed.get("libraryfolders") or parsed.get("LibraryFolders"))
    paths: list[str] = []
    for key, value in folders.items():
        if isinstance(value, dict):
            path = _string(value.get("path"))
            if path:
                paths.append(path)
        elif isinstance(value, str) and key.isdigit():
            paths.append(value)
    return paths


@dataclass(frozen=True, slots=True)
class SteamApp:
    appid: str
    name: str


def steam_app(manifest_text: str) -> SteamApp | None:
    """One `appmanifest_*.acf`, or None if it is not an installed game."""
    state = _section(parse_vdf(manifest_text).get("AppState"))
    appid = _string(state.get("appid"))
    name = _string(state.get("name")).strip()
    if not appid or not name:
        return None
    try:
        flags = int(_string(state.get("StateFlags")) or "0")
    except ValueError:
        flags = 0
    if not flags & STATE_FULLY_INSTALLED:
        return None
    if appid in TOOL_APPIDS or name.startswith(_TOOL_PREFIXES):
        return None
    return SteamApp(appid=appid, name=name)


@dataclass(frozen=True, slots=True)
class LibraryGame:
    """One game from any of the four sources, in Salon's own terms."""

    id: str
    """Namespaced (`steam:620`), so two libraries owning a game with the
    same name cannot collide, and so a tile id survives a rename."""
    title: str
    source: str
    launch: tuple[str, ...]
    """argv, before any sandbox prefix."""
    artwork: str | None = None


def heroic_games(library_json: str, runner: str) -> list[LibraryGame]:
    """Heroic's store cache for one runner (`legendary` for Epic, `gog`).

    Only installed titles: Heroic caches the whole store library, which for
    an Epic account with years of free weekly giveaways is several hundred
    games the machine does not have.
    """
    try:
        parsed = json.loads(library_json)
    except (json.JSONDecodeError, TypeError):
        return []
    entries = parsed.get("library") if isinstance(parsed, dict) else parsed
    if not isinstance(entries, list):
        return []
    games: list[LibraryGame] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("is_installed"):
            continue
        app_name = str(entry.get("app_name") or "")
        title = str(entry.get("title") or "").strip()
        if not app_name or not title:
            continue
        art = entry.get("art_square") or entry.get("art_cover")
        games.append(
            LibraryGame(
                id=f"heroic:{runner}:{app_name}",
                title=title,
                source="Heroic",
                # Heroic registers this scheme; going through the launcher
                # rather than the game's own binary is what gets the cloud
                # saves, the Wine prefix and the DRM wrapper it needs.
                launch=("xdg-open", f"heroic://launch/{runner}/{app_name}"),
                artwork=str(art) if isinstance(art, str) and art.startswith("http") else None,
            )
        )
    return games


def retroarch_games(playlist_json: str, playlist_name: str) -> list[LibraryGame]:
    """One RetroArch playlist (`.lpl`), which is JSON despite the name."""
    try:
        parsed = json.loads(playlist_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, dict):
        return []
    items = parsed.get("items")
    default_core = str(parsed.get("default_core_path") or "")
    if not isinstance(items, list):
        return []
    system = playlist_name.removesuffix(".lpl")
    games: list[LibraryGame] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        label = str(item.get("label") or "").strip()
        core = str(item.get("core_path") or "") or default_core
        if not path or not label:
            continue
        # DETECT means "ask RetroArch to work the core out", which it can
        # only do with a playlist it is reading itself — launching the ROM
        # with no core would open RetroArch's menu instead of the game.
        argv = ("retroarch", "-L", core, path) if core and core != "DETECT" else ("retroarch", path)
        games.append(
            LibraryGame(
                id=f"retroarch:{system}:{label}",
                title=label,
                source=system or "RetroArch",
                launch=argv,
            )
        )
    return games

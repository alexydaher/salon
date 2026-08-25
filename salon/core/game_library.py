# SPDX-License-Identifier: GPL-3.0-or-later
"""Launcher-independent game records and JSON library parsers."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LibraryGame:
    """One game from an installed library, expressed as launchable argv."""

    id: str
    title: str
    source: str
    launch: tuple[str, ...]
    artwork: str | None = None


def heroic_games(library_json: str, runner: str) -> list[LibraryGame]:
    """Return the installed titles in one Heroic store cache."""
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
                launch=("xdg-open", f"heroic://launch/{runner}/{app_name}"),
                artwork=str(art) if isinstance(art, str) and art.startswith("http") else None,
            )
        )
    return games


def retroarch_games(playlist_json: str, playlist_name: str) -> list[LibraryGame]:
    """Return games from one RetroArch JSON playlist."""
    try:
        parsed = json.loads(playlist_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        return []
    default_core = str(parsed.get("default_core_path") or "")
    system = playlist_name.removesuffix(".lpl")
    games: list[LibraryGame] = []
    for item in parsed["items"]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        label = str(item.get("label") or "").strip()
        core = str(item.get("core_path") or "") or default_core
        if not path or not label:
            continue
        argv = (
            ("retroarch", "-L", core, path)
            if core and core != "DETECT"
            else ("retroarch", path)
        )
        games.append(
            LibraryGame(
                id=f"retroarch:{system}:{label}",
                title=label,
                source=system or "RetroArch",
                launch=argv,
            )
        )
    return games

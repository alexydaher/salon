# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed-application discovery (§6.6, §6.8).

Search covers the tile catalogue *and* every installed application, so the
user can start anything on the machine without adding a tile for it first.
Scanning the desktop-entry database touches every `applications` directory
on the system, which is far too slow to do on the frame clock, so it runs
on a worker thread and delivers back through `GLib.idle_add` (§10: no
blocking I/O on the main loop).

Results are `Tile`s, so search results render with exactly the same widget,
artwork resolution and launch path as catalogue tiles — an installed app
found through search is not a second-class kind of thing.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core.model import LaunchKind, LaunchSpec, Tile  # noqa: E402

# Namespaced so an installed app can never collide with a user's tile id —
# they share an id space once both are in a search result list.
ID_PREFIX = "app:"


def tile_for(app_info: Gio.AppInfo) -> Tile:
    desktop_id = app_info.get_id() or app_info.get_name()
    icon = app_info.get_icon()
    return Tile(
        id=f"{ID_PREFIX}{desktop_id}",
        title=app_info.get_display_name() or app_info.get_name(),
        subtitle=app_info.get_description(),
        launch=LaunchSpec(kind=LaunchKind.DESKTOP, target=desktop_id),
        artwork=None,
        icon_name=icon.to_string() if icon is not None else None,
        accent=None,
        tags=("installed",),
    )


def scan_installed() -> list[Tile]:
    """Synchronous scan, for callers already on a worker thread (the apps
    provider runs under `core/provider.py`'s deadline, which is itself a
    thread — handing it a second one would just be a callback with extra
    steps)."""
    return _scan()


def _scan() -> list[Tile]:
    tiles = [
        tile_for(app_info)
        for app_info in Gio.AppInfo.get_all()
        # should_show() honours NoDisplay, OnlyShowIn and Hidden, which is
        # what keeps settings panels, MIME handlers and other non-launchable
        # entries out of the results.
        if app_info.should_show()
    ]
    tiles.sort(key=lambda tile: tile.title.casefold())
    return tiles


def list_installed_async(callback: Callable[[list[Tile]], None]) -> None:
    """Scan on a worker thread; call `callback` on the main loop."""

    def worker() -> None:
        try:
            tiles = _scan()
        except Exception:  # noqa: BLE001 — a broken .desktop file must not kill search
            tiles = []
        GLib.idle_add(lambda: _deliver(callback, tiles))

    threading.Thread(target=worker, name="salon-appinfo", daemon=True).start()


def _deliver(callback: Callable[[list[Tile]], None], tiles: list[Tile]) -> bool:
    callback(tiles)
    return GLib.SOURCE_REMOVE


def search_pairs(tiles: Iterable[Tile]) -> list[tuple[str, str]]:
    """(id, title) pairs in the shape core.ranking.rank expects."""
    return [(tile.id, tile.title) for tile in tiles]

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
import unicodedata
from collections.abc import Callable, Iterable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core import sandbox  # noqa: E402
from salon.core.model import LaunchKind, LaunchSpec, Tile  # noqa: E402
from salon.core.starter import StarterDiscovery  # noqa: E402
from salon.services import host_appinfo  # noqa: E402

# Namespaced so an installed app can never collide with a user's tile id —
# they share an id space once both are in a search result list.
ID_PREFIX = "app:"


def sort_key(title: str) -> str:
    """Where a title belongs in an A-Z list.

    `casefold()` alone puts every accented name after "Z", because that is
    where the code points are: "Éditeur de texte" sorted after "Zoom" and
    landed under the phone's "#" heading, several screens from the E it
    reads as. Folding the combining marks off first files it under E, which
    is both where somebody looks for it and where the index rail says it is.
    """
    stripped = "".join(
        part
        for part in unicodedata.normalize("NFD", title)
        if not unicodedata.combining(part)
    )
    return stripped.casefold()


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
    if sandbox.in_flatpak():
        try:
            return _scan_host()
        except (host_appinfo.HostScanError, ValueError, TypeError, KeyError):
            # A host without Python (or an older Flatpak without host-spawn)
            # still gets the entries Gio can see instead of losing the page.
            pass
    return _scan_local()


def _scan_local() -> list[Tile]:
    tiles = [
        tile_for(app_info)
        for app_info in Gio.AppInfo.get_all()
        # should_show() honours NoDisplay, OnlyShowIn and Hidden, which is
        # what keeps settings panels, MIME handlers and other non-launchable
        # entries out of the results.
        if app_info.should_show()
    ]
    tiles.sort(key=lambda tile: sort_key(tile.title))
    return tiles


def _scan_host() -> list[Tile]:
    records = host_appinfo.scan()
    tiles = [_tile_for_host_record(record) for record in records]
    tiles.sort(key=lambda tile: sort_key(tile.title))
    return tiles


def _tile_for_host_record(record: object) -> Tile:
    if not isinstance(record, dict):
        raise TypeError("host application inventory contained a non-object")
    desktop_id = record["id"]
    title = record["name"]
    if not isinstance(desktop_id, str) or not isinstance(title, str):
        raise TypeError("host application inventory contained an invalid id or name")
    description = record.get("description")
    icon = record.get("icon")
    if description is not None and not isinstance(description, str):
        raise TypeError("host application inventory contained an invalid description")
    if icon is not None and not isinstance(icon, str):
        raise TypeError("host application inventory contained an invalid icon")
    return Tile(
        id=f"{ID_PREFIX}{desktop_id}",
        title=title,
        subtitle=description,
        launch=LaunchSpec(kind=LaunchKind.DESKTOP, target=desktop_id),
        artwork=None,
        icon_name=icon,
        accent=None,
        tags=("installed",),
    )


def list_installed_async(callback: Callable[[list[Tile]], None]) -> None:
    """Scan on a worker thread; call `callback` on the main loop."""

    def worker() -> None:
        try:
            tiles = _scan()
        except Exception:  # noqa: BLE001 — a broken .desktop file must not kill search
            tiles = []
        GLib.idle_add(lambda: _deliver(callback, tiles))

    threading.Thread(target=worker, name="salon-appinfo", daemon=True).start()


def discover_starter_async(callback: Callable[[StarterDiscovery], None]) -> None:
    """Discover installed tiles and useful default handlers off the UI loop."""

    def worker() -> None:
        try:
            tiles = tuple(_scan())
            browser_id = _info_id(Gio.AppInfo.get_default_for_uri_scheme("http"))
            file_manager_id = _info_id(
                Gio.AppInfo.get_default_for_type("inode/directory", False)
            )
        except Exception:  # noqa: BLE001 — startup remains useful with web fallbacks
            tiles = ()
            browser_id = None
            file_manager_id = None
        discovery = StarterDiscovery(tiles, browser_id, file_manager_id)
        GLib.idle_add(lambda: _deliver_starter(callback, discovery))

    threading.Thread(target=worker, name="salon-starter-appinfo", daemon=True).start()


def _info_id(info: Gio.AppInfo | None) -> str | None:
    return None if info is None else (info.get_id() or info.get_name())


def _deliver(callback: Callable[[list[Tile]], None], tiles: list[Tile]) -> bool:
    callback(tiles)
    return GLib.SOURCE_REMOVE


def _deliver_starter(
    callback: Callable[[StarterDiscovery], None], discovery: StarterDiscovery
) -> bool:
    callback(discovery)
    return GLib.SOURCE_REMOVE


def search_pairs(tiles: Iterable[Tile]) -> list[tuple[str, str]]:
    """(id, title) pairs in the shape core.ranking.rank expects."""
    return [(tile.id, tile.title) for tile in tiles]

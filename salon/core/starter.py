# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure policy for Salon's editable, television-oriented starter catalogue."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from salon.core.config import Config
from salon.core.config_serialization import config_to_dict
from salon.core.editing import slugify, uniquify
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile

MAX_STARTER_APPS = 6

_GAME_APP_IDS = (
    ("steam", "com.valvesoftware.steam"),
    ("com.heroicgameslauncher.hgl",),
    ("net.lutris.lutris",),
)
_MEDIA_APP_IDS = (
    ("tv.kodi.kodi", "kodi"),
    ("tv.plex.plexhtpc",),
    ("org.videolan.vlc", "vlc"),
    ("io.github.celluloid-player.celluloid", "io.github.celluloid_player.celluloid"),
)
_GEFORCE_NOW_IDS = ("com.nvidia.geforcenow",)


@dataclass(frozen=True, slots=True)
class StarterDiscovery:
    installed: tuple[Tile, ...]
    browser_id: str | None = None
    file_manager_id: str | None = None


def pending_starter_config() -> Config:
    """Useful immediately while the installed-application scan is running."""
    return Config(rows=_starter_rows([], geforce_now=None))


def build_starter_config(discovery: StarterDiscovery) -> Config:
    apps = _select_apps(discovery)
    geforce_now = _find_known(discovery.installed, (_GEFORCE_NOW_IDS,))
    return Config(rows=_starter_rows(apps, geforce_now=geforce_now))


def is_legacy_seed(config: Config) -> bool:
    """True only for the complete, byte-semantics-equivalent 0.2 starter."""
    return config_to_dict(config) == config_to_dict(Config(rows=_legacy_seed_rows()))


def fingerprint(config: Config) -> dict[str, object]:
    """Snapshot the persisted state before asynchronous discovery begins."""
    return config_to_dict(config)


def can_finalize(
    current: Config, disk: Config | None, expected: dict[str, object]
) -> bool:
    """Only an untouched memory/disk pair may receive discovered tiles."""
    return fingerprint(current) == expected and (
        disk is None or fingerprint(disk) == expected
    )


def _normal_id(value: str) -> str:
    result = value.casefold()
    return result.removesuffix(".desktop")


def _by_target(installed: Iterable[Tile]) -> dict[str, Tile]:
    return {_normal_id(tile.launch.target): tile for tile in installed}


def _find_known(installed: Iterable[Tile], groups: Iterable[tuple[str, ...]]) -> Tile | None:
    by_id = _by_target(installed)
    for aliases in groups:
        for app_id in aliases:
            found = by_id.get(_normal_id(app_id))
            if found is not None:
                return found
    return None


def _select_apps(discovery: StarterDiscovery) -> list[Tile]:
    by_id = _by_target(discovery.installed)
    selected: list[Tile] = []
    chosen_targets: set[str] = set()

    def add(tile: Tile | None) -> None:
        if tile is None or len(selected) >= MAX_STARTER_APPS:
            return
        target = _normal_id(tile.launch.target)
        if target in chosen_targets:
            return
        chosen_targets.add(target)
        selected.append(tile)

    def default(app_id: str | None) -> Tile | None:
        return None if app_id is None else by_id.get(_normal_id(app_id))

    # Balance the first screen before filling it: browser, one game launcher,
    # one media app, and files are more useful on a TV than six near-identical
    # launchers from a single category.
    add(default(discovery.browser_id))
    add(_find_known(discovery.installed, _GAME_APP_IDS))
    add(_find_known(discovery.installed, _MEDIA_APP_IDS))
    add(default(discovery.file_manager_id))
    for group in (*_GAME_APP_IDS, *_MEDIA_APP_IDS):
        add(_find_known(discovery.installed, (group,)))
    editable: list[Tile] = []
    taken: set[str] = set()
    for tile in selected:
        copied = _editable_app(tile, taken)
        editable.append(copied)
        taken.add(copied.id)
    return editable


def _editable_app(tile: Tile, taken: set[str]) -> Tile:
    tile_id = uniquify(slugify(tile.title), taken)
    return Tile(
        id=tile_id,
        title=tile.title,
        subtitle=tile.subtitle,
        launch=LaunchSpec(kind=LaunchKind.DESKTOP, target=tile.launch.target),
        artwork=None,
        icon_name=tile.icon_name,
        accent=None,
        tags=("installed",),
    )


def _installed_service(tile_id: str, title: str, tile: Tile, accent: str) -> Tile:
    return Tile(
        id=tile_id,
        title=title,
        subtitle=tile.subtitle,
        launch=LaunchSpec(kind=LaunchKind.DESKTOP, target=tile.launch.target),
        artwork=None,
        icon_name=tile.icon_name,
        accent=accent,
        tags=("installed",),
    )


def _web_tile(tile_id: str, title: str, url: str, accent: str | None = None) -> Tile:
    return Tile(
        id=tile_id,
        title=title,
        subtitle=None,
        launch=LaunchSpec(kind=LaunchKind.URL, target=url, browser_profile=tile_id),
        artwork=None,
        icon_name="web-browser-symbolic",
        accent=accent,
    )


def _starter_rows(apps: list[Tile], *, geforce_now: Tile | None) -> list[Row]:
    geforce_tile = (
        _installed_service("geforce-now", "GeForce NOW", geforce_now, "#76B900")
        if geforce_now is not None
        else _web_tile("geforce-now", "GeForce NOW", "https://play.geforcenow.com/", "#76B900")
    )
    return [
        Row(id="apps", title="Apps", provider_id="static", tiles=apps),
        Row(
            id="streaming",
            title="Streaming",
            provider_id="static",
            tiles=[
                _web_tile("netflix", "Netflix", "https://www.netflix.com/", "#E50914"),
                _web_tile("prime-video", "Prime Video", "https://www.primevideo.com/", "#00A8E1"),
                _web_tile("disney-plus", "Disney+", "https://www.disneyplus.com/", "#113CCF"),
                _web_tile("youtube", "YouTube", "https://www.youtube.com/", "#FF0000"),
                geforce_tile,
            ],
        ),
    ]
    # There was a third row here, "Web", holding one link to gnome.org. It
    # demonstrated that a URL tile exists — to somebody who had not asked —
    # by spending a whole row and a heading on a project homepage nobody
    # opens from a sofa. Adding a web tile is two presses in the editor and
    # the Streaming row above is already five worked examples of one.


def _legacy_seed_rows() -> list[Row]:
    def desktop(tile_id: str, title: str, target: str, icon: str) -> Tile:
        return Tile(tile_id, title, None, LaunchSpec(LaunchKind.DESKTOP, target), None, icon, None)

    return [
        Row(
            id="apps",
            title="Apps",
            provider_id="static",
            tiles=[
                desktop("files", "Files", "org.gnome.Nautilus", "org.gnome.Nautilus"),
                desktop(
                    "text-editor", "Text Editor", "org.gnome.TextEditor", "org.gnome.TextEditor"
                ),
                desktop("calculator", "Calculator", "org.gnome.Calculator", "org.gnome.Calculator"),
                desktop("chrome", "Chrome", "com.google.Chrome", "com.google.Chrome"),
                Tile(
                    "settings",
                    "Settings",
                    None,
                    LaunchSpec(LaunchKind.BUILTIN, "settings"),
                    None,
                    "preferences-system-symbolic",
                    None,
                ),
            ],
        ),
        Row(
            id="streaming",
            title="Streaming",
            provider_id="static",
            tiles=[
                _web_tile("netflix", "Netflix", "https://www.netflix.com", "#E50914"),
                _web_tile("prime-video", "Prime Video", "https://www.primevideo.com", "#00A8E1"),
                Tile(
                    "geforce-now",
                    "GeForce NOW",
                    None,
                    LaunchSpec(LaunchKind.FLATPAK, "com.nvidia.geforcenow"),
                    None,
                    "com.nvidia.geforcenow",
                    "#76B900",
                ),
            ],
        ),
        Row(
            id="web",
            title="Web",
            provider_id="static",
            tiles=[_web_tile("gnome-org", "GNOME.org", "https://www.gnome.org")],
        ),
    ]

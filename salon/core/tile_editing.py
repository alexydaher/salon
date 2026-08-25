# SPDX-License-Identifier: GPL-3.0-or-later
"""Construction and behavior-preserving mutation of catalogue tiles."""

from __future__ import annotations

from dataclasses import replace

from salon.core.config import Config
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile


def _find_row(config: Config, row_id: str) -> Row | None:
    return next((row for row in config.rows if row.id == row_id), None)


def _slugify(text: str) -> str:
    from salon.core.editing import slugify

    return slugify(text)


def _uniquify(base: str, taken: set[str]) -> str:
    from salon.core.editing import uniquify

    return uniquify(base, taken)


def add_tile(config: Config, row_id: str, tile: Tile) -> Tile | None:
    row = _find_row(config, row_id)
    if row is None:
        return None
    tile.id = _uniquify(tile.id, {existing.id for existing in row.tiles})
    row.tiles.append(tile)
    return tile


def remove_tile(config: Config, row_id: str, tile_id: str) -> bool:
    row = _find_row(config, row_id)
    if row is None:
        return False
    tile = next((item for item in row.tiles if item.id == tile_id), None)
    if tile is None:
        return False
    row.tiles.remove(tile)
    return True


def move_tile(config: Config, row_id: str, tile_id: str, delta: int) -> bool:
    row = _find_row(config, row_id)
    if row is None:
        return False
    for index, tile in enumerate(row.tiles):
        if tile.id != tile_id:
            continue
        target = index + delta
        if not 0 <= target < len(row.tiles):
            return False
        row.tiles.pop(index)
        row.tiles.insert(target, tile)
        return True
    return False


def move_tile_to_row(config: Config, from_row_id: str, tile_id: str, to_row_id: str) -> bool:
    source = _find_row(config, from_row_id)
    destination = _find_row(config, to_row_id)
    if source is None or destination is None or source is destination:
        return False
    tile = next((item for item in source.tiles if item.id == tile_id), None)
    if tile is None:
        return False
    source.tiles.remove(tile)
    tile.id = _uniquify(tile.id, {item.id for item in destination.tiles})
    destination.tiles.append(tile)
    return True


def new_tile(
    config: Config,
    row_id: str,
    *,
    title: str,
    kind: LaunchKind,
    target: str,
    icon_name: str | None = None,
    browser_profile: str | None = None,
) -> Tile:
    row = _find_row(config, row_id)
    taken = {tile.id for tile in row.tiles} if row is not None else set()
    tile_id = _uniquify(_slugify(title), taken)
    if kind is LaunchKind.URL and browser_profile is None:
        browser_profile = tile_id
    return Tile(
        id=tile_id,
        title=title,
        subtitle=None,
        launch=LaunchSpec(kind=kind, target=target, browser_profile=browser_profile),
        artwork=None,
        icon_name=icon_name,
        accent=None,
    )


def set_launch_target(tile: Tile, target: str) -> None:
    tile.launch = replace(tile.launch, target=target)


def set_launch_kind(tile: Tile, kind: LaunchKind) -> None:
    profile = tile.launch.browser_profile if kind is LaunchKind.URL else None
    tile.launch = replace(tile.launch, kind=kind, browser_profile=profile)


def set_fullscreen(tile: Tile, enabled: bool) -> None:
    tile.launch = replace(tile.launch, fullscreen=enabled)


def set_spatial_nav(tile: Tile, enabled: bool) -> None:
    tile.launch = replace(tile.launch, spatial_nav=enabled)

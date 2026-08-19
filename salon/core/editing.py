# SPDX-License-Identifier: GPL-3.0-or-later
"""Catalogue mutation: add, edit, reorder and remove rows and tiles. Pure.

M8's whole point is that the catalogue is editable in the app, so the
mutations themselves live here rather than in the settings widgets — they
are exactly the logic that has to keep working when someone rearranges a
row with a controller, and exactly the logic a widget test could never
reach (§0: test the pure layers).

Everything here mutates a `Config` in place and reports whether it did
anything. That mirrors how the editor actually works — load once, mutate,
save — and avoids deep-copying a tree of mutable dataclasses on every
keypress just to look functional.

Two invariants are enforced rather than assumed, because the catalogue is
now written by a UI instead of by hand:

* ids are unique where `core/catalog.py` requires them to be (row ids
  catalogue-wide, tile ids within their row), so a new tile can never make
  the catalogue unloadable;
* a move that would run off either end is refused rather than silently
  clamped, so the caller can render §6.2's rubber-band instead of pretending
  something happened.
"""

from __future__ import annotations

import re

from salon.core.config import Config
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

DEFAULT_ROW_TITLE = "New row"


def slugify(text: str) -> str:
    """A stable, readable id fragment. Falls back to "item" so a title made
    entirely of punctuation or non-Latin script still yields a usable id
    (uniquify() will then number it)."""
    slug = _SLUG_STRIP.sub("-", text.strip().lower()).strip("-")
    return slug or "item"


def uniquify(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    index = 2
    while f"{base}-{index}" in taken:
        index += 1
    return f"{base}-{index}"


def row_ids(config: Config) -> set[str]:
    return {row.id for row in config.rows}


def find_row(config: Config, row_id: str) -> Row | None:
    for row in config.rows:
        if row.id == row_id:
            return row
    return None


def find_tile(config: Config, row_id: str, tile_id: str) -> Tile | None:
    row = find_row(config, row_id)
    if row is None:
        return None
    for tile in row.tiles:
        if tile.id == tile_id:
            return tile
    return None


# --- rows ----------------------------------------------------------------


def add_row(config: Config, title: str = DEFAULT_ROW_TITLE) -> Row:
    row = Row(
        id=uniquify(slugify(title), row_ids(config)),
        title=title,
        tiles=[],
        provider_id="static",
    )
    config.rows.append(row)
    return row


def remove_row(config: Config, row_id: str) -> bool:
    row = find_row(config, row_id)
    if row is None:
        return False
    config.rows.remove(row)
    return True


def move_row(config: Config, row_id: str, delta: int) -> bool:
    row = find_row(config, row_id)
    if row is None:
        return False
    index = config.rows.index(row)
    target = index + delta
    if not (0 <= target < len(config.rows)):
        return False
    config.rows.pop(index)
    config.rows.insert(target, row)
    return True


def rename_row(config: Config, row_id: str, title: str) -> bool:
    row = find_row(config, row_id)
    if row is None:
        return False
    # The id deliberately does *not* follow the title: it's the key recents
    # and focus restoration are stored against, and renaming a row should
    # not silently forget where the user was.
    row.title = title or None
    return True


def set_row_aspect(config: Config, row_id: str, aspect: str) -> bool:
    row = find_row(config, row_id)
    if row is None or aspect not in ("wide", "square", "poster"):
        return False
    row.tile_aspect = aspect  # type: ignore[assignment]
    return True


# --- tiles ---------------------------------------------------------------


def add_tile(config: Config, row_id: str, tile: Tile) -> Tile | None:
    """Append `tile` to a row, renaming its id if that row already has one.

    Returns the tile as actually stored (its id may differ from the one
    passed in), or None if the row doesn't exist.
    """
    row = find_row(config, row_id)
    if row is None:
        return None
    tile.id = uniquify(tile.id, {t.id for t in row.tiles})
    row.tiles.append(tile)
    return tile


def remove_tile(config: Config, row_id: str, tile_id: str) -> bool:
    row = find_row(config, row_id)
    if row is None:
        return False
    for tile in row.tiles:
        if tile.id == tile_id:
            row.tiles.remove(tile)
            return True
    return False


def move_tile(config: Config, row_id: str, tile_id: str, delta: int) -> bool:
    row = find_row(config, row_id)
    if row is None:
        return False
    for index, tile in enumerate(row.tiles):
        if tile.id != tile_id:
            continue
        target = index + delta
        if not (0 <= target < len(row.tiles)):
            return False
        row.tiles.pop(index)
        row.tiles.insert(target, tile)
        return True
    return False


def move_tile_to_row(config: Config, from_row_id: str, tile_id: str, to_row_id: str) -> bool:
    """Relocate a tile between rows, renaming it if the destination already
    has that id — which is how the same app ends up in two rows."""
    source = find_row(config, from_row_id)
    destination = find_row(config, to_row_id)
    if source is None or destination is None or source is destination:
        return False
    for tile in source.tiles:
        if tile.id == tile_id:
            source.tiles.remove(tile)
            tile.id = uniquify(tile.id, {t.id for t in destination.tiles})
            destination.tiles.append(tile)
            return True
    return False


# --- tile construction ---------------------------------------------------


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
    """Build a tile with an id that won't collide inside `row_id`.

    URL tiles get their own browser profile by default: §6.3 wants one
    `--user-data-dir` per service so one sign-in can't disturb another's.
    """
    row = find_row(config, row_id)
    taken = {t.id for t in row.tiles} if row is not None else set()
    slug = uniquify(slugify(title), taken)
    if kind is LaunchKind.URL and browser_profile is None:
        browser_profile = slug
    return Tile(
        id=slug,
        title=title,
        subtitle=None,
        launch=LaunchSpec(kind=kind, target=target, browser_profile=browser_profile),
        artwork=None,
        icon_name=icon_name,
        accent=None,
    )


def set_launch_target(tile: Tile, target: str) -> None:
    """LaunchSpec is frozen, so changing where a tile points means replacing
    it — worth a helper so every call site doesn't have to remember which
    of the eight fields to carry across."""
    tile.launch = LaunchSpec(
        kind=tile.launch.kind,
        target=target,
        args=tile.launch.args,
        env=tile.launch.env,
        browser_profile=tile.launch.browser_profile,
        user_agent=tile.launch.user_agent,
        spatial_nav=tile.launch.spatial_nav,
        fullscreen=tile.launch.fullscreen,
    )


def set_launch_kind(tile: Tile, kind: LaunchKind) -> None:
    tile.launch = LaunchSpec(
        kind=kind,
        target=tile.launch.target,
        args=tile.launch.args,
        env=tile.launch.env,
        browser_profile=tile.launch.browser_profile if kind is LaunchKind.URL else None,
        user_agent=tile.launch.user_agent,
        spatial_nav=tile.launch.spatial_nav,
        fullscreen=tile.launch.fullscreen,
    )


def set_fullscreen(tile: Tile, enabled: bool) -> None:
    """URL tiles only: whether the browser window starts fullscreen. Native
    apps decide their own window state and no client can override it on
    Wayland, so there is deliberately no equivalent for the other kinds."""
    tile.launch = LaunchSpec(
        kind=tile.launch.kind,
        target=tile.launch.target,
        args=tile.launch.args,
        env=tile.launch.env,
        browser_profile=tile.launch.browser_profile,
        user_agent=tile.launch.user_agent,
        spatial_nav=tile.launch.spatial_nav,
        fullscreen=enabled,
    )


def set_spatial_nav(tile: Tile, enabled: bool) -> None:
    """§6.3 exposes this per tile because spatial navigation misbehaves on a
    minority of sites."""
    tile.launch = LaunchSpec(
        kind=tile.launch.kind,
        target=tile.launch.target,
        args=tile.launch.args,
        env=tile.launch.env,
        browser_profile=tile.launch.browser_profile,
        user_agent=tile.launch.user_agent,
        spatial_nav=enabled,
        fullscreen=tile.launch.fullscreen,
    )

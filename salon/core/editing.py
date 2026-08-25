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
from salon.core.model import Row, Tile

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


from salon.core.tile_editing import (  # noqa: E402
    add_tile,
    move_tile,
    move_tile_to_row,
    new_tile,
    remove_tile,
    set_fullscreen,
    set_launch_kind,
    set_launch_target,
    set_spatial_nav,
)

__all__ = [
    "DEFAULT_ROW_TITLE",
    "add_row",
    "add_tile",
    "find_row",
    "find_tile",
    "move_row",
    "move_tile",
    "move_tile_to_row",
    "new_tile",
    "remove_row",
    "remove_tile",
    "rename_row",
    "row_ids",
    "set_fullscreen",
    "set_launch_kind",
    "set_launch_target",
    "set_row_aspect",
    "set_spatial_nav",
    "slugify",
    "uniquify",
]

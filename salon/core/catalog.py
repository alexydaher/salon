# SPDX-License-Identifier: GPL-3.0-or-later
"""The in-memory catalog: rows assembled from providers, not read directly
from config (see §4). Pure — no gi.

`Catalog` is strict: duplicate ids raise, because a catalogue that reached
the widget layer with an ambiguous (row, col) lookup would misbehave in ways
that are very hard to trace back. `sanitize()` is the lenient front door for
provider output — it drops exactly what's ambiguous and says what it
dropped, so one bad tile id costs one row instead of the whole home screen.
"""

from __future__ import annotations

from salon.core.errors import CatalogError
from salon.core.model import Row, Tile


class Catalog:
    def __init__(self, rows: list[Row]) -> None:
        _check_unique_ids(rows)
        self.rows = rows

    def row_lengths(self) -> list[int]:
        return [len(row.tiles) for row in self.rows]

    def tile_at(self, row: int, col: int) -> Tile | None:
        if not (0 <= row < len(self.rows)):
            return None
        tiles = self.rows[row].tiles
        if not (0 <= col < len(tiles)):
            return None
        return tiles[col]

    def find(self, tile_id: str) -> tuple[int, int] | None:
        """Locate a tile by id, for focus restoration and recents.

        The same tile id can legitimately appear in more than one row (a
        recents row re-lists a tile that also lives in its "home" row) —
        this returns the first occurrence in row order."""
        for r, row in enumerate(self.rows):
            for c, tile in enumerate(row.tiles):
                if tile.id == tile_id:
                    return (r, c)
        return None


def sanitize(rows: list[Row]) -> tuple[list[Row], list[str]]:
    """Make `rows` safe to hand to `Catalog`, and report what that cost.

    §6.10's failure isolation, applied to the rows themselves rather than to
    the providers that produced them: a provider can be perfectly healthy and
    still emit two tiles with the same id. Raising there and falling back to
    an empty catalogue means one typo blanks the television.
    """
    kept: list[Row] = []
    problems: list[str] = []
    seen_rows: set[str] = set()
    for row in rows:
        if row.id in seen_rows:
            problems.append(f"Ignoring a second row with id {row.id!r}.")
            continue
        seen_rows.add(row.id)
        seen_tiles: set[str] = set()
        tiles: list[Tile] = []
        dropped: list[str] = []
        for tile in row.tiles:
            if tile.id in seen_tiles:
                dropped.append(tile.id)
                continue
            seen_tiles.add(tile.id)
            tiles.append(tile)
        if dropped:
            joined = ", ".join(sorted(set(dropped)))
            title = row.title or row.id
            problems.append(f"{title}: ignoring duplicate tile ids ({joined}).")
        if len(tiles) == len(row.tiles):
            kept.append(row)
        else:
            kept.append(
                Row(
                    id=row.id,
                    title=row.title,
                    tiles=tiles,
                    provider_id=row.provider_id,
                    tile_aspect=row.tile_aspect,
                )
            )
    return kept, problems


def _check_unique_ids(rows: list[Row]) -> None:
    """Row ids must be unique catalogue-wide, and a tile id must be unique
    *within its own row* (ambiguous column lookup otherwise) — but the same
    tile id is allowed to repeat across different rows, since a provider
    like recents deliberately re-lists a tile that already exists
    elsewhere in the catalogue."""
    seen_rows: set[str] = set()
    for row in rows:
        if row.id in seen_rows:
            raise CatalogError(f"Duplicate row id: {row.id!r}")
        seen_rows.add(row.id)
        seen_tiles_in_row: set[str] = set()
        for tile in row.tiles:
            if tile.id in seen_tiles_in_row:
                raise CatalogError(f"Duplicate tile id within row {row.id!r}: {tile.id!r}")
            seen_tiles_in_row.add(tile.id)

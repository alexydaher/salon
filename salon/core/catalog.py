"""In-memory tile catalog: ordering and mutation. Pure, no gi.

Assembled from providers (salon.providers), not read directly from config —
providers are async and live outside salon.core; this class only holds and
mutates already-resolved Row/Tile values handed to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from salon.core.errors import CatalogError
from salon.core.model import Row, Tile


@dataclass(slots=True)
class Catalog:
    _rows: list[Row] = field(default_factory=list)

    @property
    def rows(self) -> tuple[Row, ...]:
        return tuple(self._rows)

    def set_rows(self, rows: list[Row]) -> None:
        self._rows = list(rows)

    def row(self, row_id: str) -> Row:
        for row in self._rows:
            if row.id == row_id:
                return row
        raise CatalogError(f"No row with id {row_id!r}")

    def row_index(self, row_id: str) -> int:
        for index, row in enumerate(self._rows):
            if row.id == row_id:
                return index
        raise CatalogError(f"No row with id {row_id!r}")

    def add_row(self, row: Row, index: int | None = None) -> None:
        if any(r.id == row.id for r in self._rows):
            raise CatalogError(f"Row id {row.id!r} already exists")
        if index is None:
            self._rows.append(row)
        else:
            self._rows.insert(index, row)

    def remove_row(self, row_id: str) -> None:
        del self._rows[self.row_index(row_id)]

    def reorder_row(self, row_id: str, new_index: int) -> None:
        row = self._rows.pop(self.row_index(row_id))
        self._rows.insert(max(0, min(new_index, len(self._rows))), row)

    def find_tile(self, tile_id: str) -> tuple[Row, Tile] | None:
        for row in self._rows:
            for tile in row.tiles:
                if tile.id == tile_id:
                    return row, tile
        return None

    def add_tile(self, row_id: str, tile: Tile, index: int | None = None) -> None:
        row = self.row(row_id)
        if any(t.id == tile.id for t in row.tiles):
            raise CatalogError(f"Tile id {tile.id!r} already exists in row {row_id!r}")
        if index is None:
            row.tiles.append(tile)
        else:
            row.tiles.insert(index, tile)

    def remove_tile(self, row_id: str, tile_id: str) -> None:
        row = self.row(row_id)
        for i, tile in enumerate(row.tiles):
            if tile.id == tile_id:
                del row.tiles[i]
                return
        raise CatalogError(f"No tile {tile_id!r} in row {row_id!r}")

    def move_tile(self, row_id: str, tile_id: str, new_index: int) -> None:
        row = self.row(row_id)
        for i, tile in enumerate(row.tiles):
            if tile.id == tile_id:
                moved = row.tiles.pop(i)
                row.tiles.insert(max(0, min(new_index, len(row.tiles))), moved)
                return
        raise CatalogError(f"No tile {tile_id!r} in row {row_id!r}")

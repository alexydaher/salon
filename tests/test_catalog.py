# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from salon.core.catalog import Catalog, sanitize
from salon.core.errors import CatalogError
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile


def _tile(tile_id: str) -> Tile:
    return Tile(
        id=tile_id,
        title=tile_id,
        subtitle=None,
        launch=LaunchSpec(kind=LaunchKind.COMMAND, target="true"),
        artwork=None,
        icon_name=None,
        accent=None,
    )


def _row(row_id: str, *tile_ids: str) -> Row:
    return Row(
        id=row_id,
        title=row_id,
        tiles=[_tile(t) for t in tile_ids],
        provider_id="static",
    )


def _rows() -> list[Row]:
    return [
        Row(id="apps", title="Apps", tiles=[_tile("a"), _tile("b")], provider_id="static"),
        Row(id="games", title="Games", tiles=[_tile("c")], provider_id="static"),
    ]


def test_row_lengths() -> None:
    catalog = Catalog(_rows())
    assert catalog.row_lengths() == [2, 1]


def test_tile_at_valid_position() -> None:
    catalog = Catalog(_rows())
    tile = catalog.tile_at(0, 1)
    assert tile is not None
    assert tile.id == "b"


def test_tile_at_out_of_range_returns_none() -> None:
    catalog = Catalog(_rows())
    assert catalog.tile_at(5, 0) is None
    assert catalog.tile_at(0, 5) is None
    assert catalog.tile_at(-1, 0) is None


def test_find_locates_tile_by_id() -> None:
    catalog = Catalog(_rows())
    assert catalog.find("c") == (1, 0)


def test_find_missing_id_returns_none() -> None:
    catalog = Catalog(_rows())
    assert catalog.find("nope") is None


def test_duplicate_tile_id_raises() -> None:
    rows = [
        Row(id="apps", title="Apps", tiles=[_tile("a"), _tile("a")], provider_id="static"),
    ]
    with pytest.raises(CatalogError):
        Catalog(rows)


def test_same_tile_id_allowed_across_different_rows() -> None:
    # A recents-style row legitimately re-lists a tile that also lives in
    # its "home" row — this must not raise.
    rows = [
        Row(id="recents", title="Recents", tiles=[_tile("a")], provider_id="recents"),
        Row(id="apps", title="Apps", tiles=[_tile("a"), _tile("b")], provider_id="static"),
    ]
    catalog = Catalog(rows)
    assert catalog.find("a") == (0, 0)  # first occurrence, in row order


def test_duplicate_row_id_raises() -> None:
    rows = [
        Row(id="apps", title="Apps", tiles=[_tile("a")], provider_id="static"),
        Row(id="apps", title="Apps2", tiles=[_tile("b")], provider_id="static"),
    ]
    with pytest.raises(CatalogError):
        Catalog(rows)


def test_sanitize_drops_a_duplicate_row_and_says_so() -> None:
    rows = [_row("a"), _row("a"), _row("b")]
    kept, problems = sanitize(rows)
    assert [r.id for r in kept] == ["a", "b"]
    assert len(problems) == 1
    assert "a" in problems[0]


def test_sanitize_drops_a_duplicate_tile_but_keeps_its_row() -> None:
    rows = [_row("a", "x", "y", "x")]
    kept, problems = sanitize(rows)
    assert [t.id for t in kept[0].tiles] == ["x", "y"]
    assert len(problems) == 1
    assert "x" in problems[0]
    # The row survives — one bad id must not cost the whole row.
    assert len(kept) == 1


def test_sanitize_output_is_always_accepted_by_catalog() -> None:
    rows = [_row("a", "x", "x"), _row("a"), _row("b", "x")]
    kept, _ = sanitize(rows)
    catalog = Catalog(kept)  # must not raise
    assert [r.id for r in catalog.rows] == ["a", "b"]


def test_sanitize_preserves_row_aspect() -> None:
    rows = [Row(id="a", title="A", tiles=[_tile("x"), _tile("x")],
                provider_id="p", tile_aspect="poster")]
    kept, _ = sanitize(rows)
    assert kept[0].tile_aspect == "poster"

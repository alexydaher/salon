from __future__ import annotations

from salon.core.tokens import COLORS, TILE_SIZES, TYPE_SCALE, design_units_to_px


def test_colors_have_unique_names() -> None:
    names = [c.name for c in COLORS]
    assert len(names) == len(set(names))


def test_type_scale_and_tile_sizes_have_unique_names() -> None:
    assert len({t.name for t in TYPE_SCALE}) == len(TYPE_SCALE)
    assert len({t.name for t in TILE_SIZES}) == len(TILE_SIZES)


def test_design_units_to_px_at_reference_height() -> None:
    assert design_units_to_px(1080.0, 1080) == 1080.0
    assert design_units_to_px(100.0, 2160) == 200.0
    assert design_units_to_px(100.0, 540) == 50.0

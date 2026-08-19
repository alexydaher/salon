# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from salon.core import tokens
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


def test_browser_scale_factor_tracks_the_du_scale() -> None:
    """§6.3: the browser's device scale factor comes from the same du scale
    as the UI, so web pages are readable at three metres on a 4K TV."""
    assert tokens.browser_scale_factor(1080) == 1.0
    assert tokens.browser_scale_factor(2160) == 2.0
    assert tokens.browser_scale_factor(1440) == pytest.approx(1.33)


def test_browser_scale_factor_is_clamped() -> None:
    assert tokens.browser_scale_factor(720) == 1.0
    assert tokens.browser_scale_factor(8640) == 3.0


def test_every_type_token_is_readable_at_distance() -> None:
    """§7.2: nothing below MIN_READABLE_SIZE_DU renders anywhere."""
    for token in tokens.TYPE_SCALE:
        assert token.size_du >= tokens.MIN_READABLE_SIZE_DU, token.name


def test_tile_bleed_covers_the_focus_growth_and_the_bloom() -> None:
    """The transparent padding around a tile has to be big enough for both
    the focus scale-up and the bloom, or the row viewport clips them — the
    bug that made the focused tile's halo look sliced off."""
    tallest = max(t.height_du for t in tokens.TILE_SIZES)
    growth = tallest * (tokens.FOCUS_SCALE_FOCUSED - tokens.FOCUS_SCALE_REST) / 2
    bloom = tokens.BLOOM_BLUR_DU + tokens.BLOOM_OFFSET_DU
    assert tokens.TILE_BLEED_DU >= growth + bloom

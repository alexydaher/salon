# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure sizing policy for the All applications grid."""

from __future__ import annotations

from collections.abc import Sequence

from salon.core import tokens
from salon.ui.scale import Scale
from salon.ui.tile_geometry import TileMetrics, metrics_for


def grid_metrics(scale: Scale, tile_scale: float) -> TileMetrics:
    """The All Apps card contract at the shipped 55% preference.

    These are not Home's cards enlarged: the mockup deliberately keeps the
    four-column width while reducing the old 16:9 height to 138du.
    """
    factor = tile_scale / 0.55
    base = metrics_for(scale, "wide", size_scale=tile_scale)
    return TileMetrics(
        width=scale.du(308.0 * factor),
        height=scale.du(138.0 * factor),
        bleed=base.bleed,
        gap=scale.du(18.0),
        radius=scale.du(tokens.CORNER_RADIUS_DU),
        padding=scale.du(18.0 * factor),
        title_size=scale.du(20.0 * factor),
        subtitle_size=scale.du(14.0 * factor),
    )


def horizontal_origin(safe_margin: float, metrics: TileMetrics) -> float:
    return max(0.0, safe_margin - metrics.bleed)


def column_count(viewport_width: int, safe_margin: float, metrics: TileMetrics) -> int:
    if viewport_width <= 0:
        return 1
    left = horizontal_origin(safe_margin, metrics)
    usable = max(1.0, viewport_width - left - metrics.bleed - safe_margin)
    # +gap because the last column needs no trailing gap; without it the
    # grid loses a column whenever the remainder is smaller than one.
    return max(1, int((usable + metrics.gap) // metrics.step))


def grouped_rows(item_count: int, columns: int, group_starts: Sequence[int]) -> list[list[int]]:
    """Return the rows users actually see when every A-Z group starts fresh."""
    if item_count <= 0:
        return []
    columns = max(1, columns)
    starts = sorted({start for start in group_starts if 0 <= start < item_count})
    if not starts or starts[0] != 0:
        starts.insert(0, 0)
    ends = [*starts[1:], item_count]
    return [
        list(range(row_start, min(row_start + columns, end)))
        for start, end in zip(starts, ends, strict=True)
        for row_start in range(start, end, columns)
    ]


def linear_neighbor(index: int, item_count: int, delta: int) -> int | None:
    """Move in reading order, including across the end of a visual row."""
    target = index + delta
    return target if 0 <= target < item_count else None

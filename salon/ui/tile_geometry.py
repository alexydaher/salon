# SPDX-License-Identifier: GPL-3.0-or-later
"""Tile dimensions, typography, colors, and geometry constructors."""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Graphene, Gsk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

DISPLAY_FAMILY = "Archivo,Inter,Adwaita Sans,Cantarell,sans-serif"
BODY_FAMILY = "Inter,Adwaita Sans,Cantarell,sans-serif"


@dataclass(frozen=True, slots=True)
class TileMetrics:
    """Every pixel dimension a tile and the rows around it need, resolved
    from the du scale once per (scale, aspect) instead of recomputed per
    widget."""

    width: float
    height: float
    bleed: float
    gap: float
    radius: float

    @property
    def outer_width(self) -> float:
        return self.width + 2 * self.bleed

    @property
    def outer_height(self) -> float:
        return self.height + 2 * self.bleed

    @property
    def step(self) -> float:
        """Distance between two adjacent tiles' left edges."""
        return self.width + self.gap


def metrics_for(scale: Scale, aspect: str = "wide", *, size_scale: float = 1.0) -> TileMetrics:
    """`size_scale` is the user's tile-size preference (§6.8). The bleed
    scales with the card because it exists to hold the bloom and the
    focus growth, both of which are proportional to the card; the gap and
    the corner radius do not, because those are design constants."""
    size = tokens.tile_size(aspect)
    return TileMetrics(
        width=scale.du(size.width_du * size_scale),
        height=scale.du(size.height_du * size_scale),
        bleed=scale.du(tokens.TILE_BLEED_DU * size_scale),
        gap=scale.du(tokens.TILE_GAP_DU),
        radius=scale.du(tokens.CORNER_RADIUS_DU),
    )


# --- small colour/geometry helpers --------------------------------------


def _rgba(red: float, green: float, blue: float, alpha: float = 1.0) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red = red
    color.green = green
    color.blue = blue
    color.alpha = alpha
    return color


def _parse(value: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(value)
    return color


def _mix(base: Gdk.RGBA, other: Gdk.RGBA, amount: float) -> Gdk.RGBA:
    return _rgba(
        base.red + (other.red - base.red) * amount,
        base.green + (other.green - base.green) * amount,
        base.blue + (other.blue - base.blue) * amount,
        base.alpha + (other.alpha - base.alpha) * amount,
    )


def _with_alpha(color: Gdk.RGBA, alpha: float) -> Gdk.RGBA:
    return _rgba(color.red, color.green, color.blue, alpha)


def _rect(x: float, y: float, width: float, height: float) -> Graphene.Rect:
    rect = Graphene.Rect()
    rect.init(x, y, width, height)
    return rect


def _point(x: float, y: float) -> Graphene.Point:
    point = Graphene.Point()
    point.init(x, y)
    return point


def _rounded(rect: Graphene.Rect, radius: float) -> Gsk.RoundedRect:
    rounded = Gsk.RoundedRect()
    rounded.init_from_rect(rect, radius)
    return rounded


def _stops(*pairs: tuple[float, Gdk.RGBA]) -> list[Gsk.ColorStop]:
    result = []
    for offset, color in pairs:
        stop = Gsk.ColorStop()
        stop.offset = offset
        stop.color = color
        result.append(stop)
    return result


_TRANSPARENT = _rgba(0.0, 0.0, 0.0, 0.0)

_WEIGHTS = {
    400: Pango.Weight.NORMAL,
    500: Pango.Weight.MEDIUM,
    600: Pango.Weight.SEMIBOLD,
    700: Pango.Weight.BOLD,
}


def font_description(family: str, size_px: float, weight: int) -> Pango.FontDescription:
    description = Pango.FontDescription()
    description.set_family(family)
    description.set_weight(_WEIGHTS.get(weight, Pango.Weight.NORMAL))
    description.set_absolute_size(size_px * Pango.SCALE)
    return description

"""Design tokens — the single source of truth for Salon's visual system.

data/style/tokens.css is generated from COLORS by build-aux/gen-tokens-css.py
at build time. Sizes are expressed in design units (du); ui code converts
them to pixels at runtime via design_units_to_px() once the target monitor's
geometry is known. See the "du unit" note in the design brief: 1du =
viewport_height / 1080.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColorToken:
    name: str
    value: str


COLORS: tuple[ColorToken, ...] = (
    ColorToken("surface-0", "#0E1116"),
    ColorToken("surface-1", "#161B22"),
    ColorToken("surface-2", "#1F2630"),
    ColorToken("text-primary", "#F2EDE4"),
    ColorToken("text-secondary", "#9AA3AE"),
    ColorToken("accent", "#E8A33D"),
    ColorToken("accent-bloom", "rgba(232,163,61,0.22)"),
    ColorToken("danger", "#D9584B"),
)


@dataclass(frozen=True, slots=True)
class TypeToken:
    name: str
    size_du: float
    weight: int


TYPE_SCALE: tuple[TypeToken, ...] = (
    TypeToken("clock", 44.0, 700),
    TypeToken("row-heading", 34.0, 600),
    TypeToken("tile-title", 30.0, 600),
    TypeToken("tile-subtitle", 24.0, 400),
    TypeToken("settings-body", 26.0, 400),
)

MIN_READABLE_SIZE_DU: float = 22.0


@dataclass(frozen=True, slots=True)
class TileSizeToken:
    name: str
    width_du: float
    height_du: float


TILE_SIZES: tuple[TileSizeToken, ...] = (
    TileSizeToken("wide", 320.0, 180.0),
    TileSizeToken("square", 220.0, 220.0),
    TileSizeToken("poster", 200.0, 300.0),
)

TILE_GAP_DU: float = 28.0
ROW_GAP_DU: float = 56.0
CORNER_RADIUS_DU: float = 12.0

SAFE_AREA_DEFAULT_PERCENT: float = 4.5
SAFE_AREA_MIN_PERCENT: float = 2.0
SAFE_AREA_MAX_PERCENT: float = 8.0

FOCUS_SCALE_REST: float = 1.0
FOCUS_SCALE_FOCUSED: float = 1.09


def design_units_to_px(du: float, viewport_height_px: int) -> float:
    """Convert a design-unit value to pixels for a given viewport height."""
    scale = viewport_height_px / 1080.0
    return du * scale

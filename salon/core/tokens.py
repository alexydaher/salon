# SPDX-License-Identifier: GPL-3.0-or-later
"""Design tokens — the single source of truth for Salon's visual system.

Two paths out of this module, and the split is deliberate (§7.2):

* **Build time** — data/style/tokens.css is generated from COLORS by
  build-aux/gen-tokens-css.py. Only values that do *not* depend on viewport
  size live there: colours and font families. Never hand-edit that file.
* **Runtime** — everything sized in design units (du) is resolved to pixels
  by salon/ui/scale.py once the target monitor's geometry is known, and
  injected as CSS custom properties. 1du = viewport_height / 1080, so the
  same numbers below are correct on a 1080p TV and a 4K TV without a second
  design pass.

Nothing here imports gi, so the whole design system stays testable headlessly.
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


def color(name: str) -> str:
    """The raw hex/rgba string for a colour token, for code that draws
    outside CSS (the tile and backdrop render themselves in do_snapshot)."""
    for token in COLORS:
        if token.name == name:
            return token.value
    raise KeyError(name)


@dataclass(frozen=True, slots=True)
class TypeToken:
    name: str
    size_du: float
    weight: int


# Nothing below MIN_READABLE_SIZE_DU renders anywhere. If a size seems too
# large on a desktop monitor during development, it is correct — the design
# target is three metres away, not sixty centimetres.
TYPE_SCALE: tuple[TypeToken, ...] = (
    TypeToken("clock", 44.0, 700),
    TypeToken("date", 26.0, 400),
    TypeToken("row-heading", 34.0, 600),
    TypeToken("tile-title", 30.0, 600),
    TypeToken("tile-subtitle", 24.0, 400),
    TypeToken("settings-body", 26.0, 400),
    TypeToken("menu-item", 30.0, 600),
    TypeToken("overlay-title", 40.0, 700),
    TypeToken("overlay-body", 26.0, 400),
)

MIN_READABLE_SIZE_DU: float = 22.0


def type_token(name: str) -> TypeToken:
    for token in TYPE_SCALE:
        if token.name == name:
            return token
    raise KeyError(name)


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


def tile_size(aspect: str) -> TileSizeToken:
    for token in TILE_SIZES:
        if token.name == aspect:
            return token
    return TILE_SIZES[0]


TILE_GAP_DU: float = 28.0
ROW_GAP_DU: float = 56.0
CORNER_RADIUS_DU: float = 12.0
ROW_HEADING_GAP_DU: float = 14.0
STATUS_BAR_HEIGHT_DU: float = 76.0

# Transparent padding carried inside every tile widget's own footprint, so
# the focus scale-up and the bloom have somewhere to render without the row
# viewport's clip cutting into either. Has to comfortably exceed both the
# scale growth (TILE_HEIGHT * (FOCUS_SCALE_FOCUSED - 1) / 2) and the bloom's
# blur radius plus its downward offset — see ui/tile.py.
TILE_BLEED_DU: float = 56.0

# The "light-fall" bloom (§7.1/§7.3 stage 2): a blurred, accent-tinted copy
# of the focused tile's bounds rendered beneath its neighbours.
BLOOM_BLUR_DU: float = 26.0
BLOOM_OFFSET_DU: float = 10.0
BLOOM_ALPHA: float = 0.55
FOCUS_RING_DU: float = 3.0

SAFE_AREA_DEFAULT_PERCENT: float = 4.5
SAFE_AREA_MIN_PERCENT: float = 2.0
SAFE_AREA_MAX_PERCENT: float = 8.0

# The focused row's fixed vertical anchor (§6.1): rows above and below
# translate, the focused row does not move. Clamped against the content
# bounds by ui/home.py so a short catalogue doesn't float in dead space.
ROW_ANCHOR_FRACTION: float = 0.38

FOCUS_SCALE_REST: float = 1.0
FOCUS_SCALE_FOCUSED: float = 1.09

# Chrome's --force-device-scale-factor is computed from the same du scale as
# the UI and clamped to this range (§6.3): on a 4K TV a factor of 1.0 makes
# web UI unreadable at three metres.
BROWSER_SCALE_MIN: float = 1.0
BROWSER_SCALE_MAX: float = 3.0

REFERENCE_VIEWPORT_HEIGHT_PX: float = 1080.0


def design_units_to_px(du: float, viewport_height_px: int) -> float:
    """Convert a design-unit value to pixels for a given viewport height."""
    return du * (viewport_height_px / REFERENCE_VIEWPORT_HEIGHT_PX)


def browser_scale_factor(viewport_height_px: int) -> float:
    """The --force-device-scale-factor for spawned browser windows (§6.3),
    derived from the same du scale as the UI and clamped to [1.0, 3.0]."""
    raw = viewport_height_px / REFERENCE_VIEWPORT_HEIGHT_PX
    return max(BROWSER_SCALE_MIN, min(BROWSER_SCALE_MAX, round(raw, 2)))

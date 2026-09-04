# SPDX-License-Identifier: GPL-3.0-or-later
"""Design tokens — the single source of truth for Salon's visual system.

* **Build time** — data/style/tokens.css is generated from COLORS by
  build-aux/gen-tokens-css.py. Only values that do *not* depend on viewport
  size live there: colours and font families. Never hand-edit that file.
* **Runtime** — sizes in design units (du) are resolved to pixels
  by salon/ui/scale.py once the target monitor's geometry is known, and
  injected as CSS custom properties. 1du = viewport_height / 1080, so the
  same numbers below are correct on a 1080p TV and a 4K TV without a second
  design pass.

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
    ColorToken("danger", "#D9584B"),
)


def color(name: str) -> str:
    """The raw hex/rgba string for a colour token, for code that draws
    outside CSS (the tile and backdrop render themselves in do_snapshot).

    This is the *design default*. At runtime `ui/theme.py` may be showing a
    different palette; anything drawing on screen should ask that instead.
    """
    for token in COLORS:
        if token.name == name:
            return token.value
    raise KeyError(name)


# The accent is separate from theme surfaces.
THEMED_TOKENS = ("surface-0", "surface-1", "surface-2", "text-primary", "text-secondary")

# Four palettes, not forty. Flex Launcher's themability is a real advantage
# and the answer to it is not an unbounded skin system — it is a small set
# of palettes that were each checked against the same artwork, the same
# focus ring and the same text sizes. Anything more becomes a surface for
# unreadable combinations nobody tested.
PALETTES: dict[str, dict[str, str]] = {
    # The design default: a blue-black that keeps artwork looking neutral.
    "midnight": {
        "surface-0": "#0E1116",
        "surface-1": "#161B22",
        "surface-2": "#1F2630",
        "text-primary": "#F2EDE4",
        "text-secondary": "#9AA3AE",
    },
    # Hueless. For anyone whose panel makes the blue-black read as blue.
    "graphite": {
        "surface-0": "#121212",
        "surface-1": "#1C1C1C",
        "surface-2": "#282828",
        "text-primary": "#F0F0F0",
        "text-secondary": "#A0A0A0",
    },
    # Warm, for a room with warm lighting, where a cool grey looks grey.
    "ember": {
        "surface-0": "#14100D",
        "surface-1": "#1E1815",
        "surface-2": "#2B2320",
        "text-primary": "#F6EEE4",
        "text-secondary": "#B0A398",
    },
    # True black and brighter text: OLED panels draw no power for black
    # pixels and show no glow around them, and the higher contrast is the
    # one that survives a lit room.
    "contrast": {
        "surface-0": "#000000",
        "surface-1": "#101010",
        "surface-2": "#1E1E1E",
        "text-primary": "#FFFFFF",
        "text-secondary": "#C4C4C4",
    },
}

DEFAULT_PALETTE = "midnight"


def palette(name: str) -> dict[str, str]:
    """A named palette, falling back to the default for anything unknown —
    a hand-edited GSetting must not leave the interface unpainted."""
    return PALETTES.get(name, PALETTES[DEFAULT_PALETTE])


@dataclass(frozen=True, slots=True)
class TypeToken:
    name: str
    size_du: float
    weight: int


# Nothing below MIN_READABLE_SIZE_DU renders anywhere. If a size seems too
# large on a desktop monitor during development, it is correct — the design
# target is three metres away, not sixty centimetres.
TYPE_SCALE: tuple[TypeToken, ...] = (
    # The clock used to be 44/700, which made the time the heaviest and
    # brightest object on the home screen — heavier than a row heading and
    # competing with the tile the user is about to launch. Nothing on a
    # launcher outranks the thing OK will open. It is still the largest
    # item in its own corner, and now it is quieter than the rows.
    TypeToken("clock", 32.0, 600),
    TypeToken("date", 26.0, 400),
    TypeToken("row-heading", 34.0, 600),
    TypeToken("tile-title", 30.0, 600),
    TypeToken("tile-subtitle", 24.0, 400),
    TypeToken("settings-body", 26.0, 400),
    TypeToken("settings-group", 22.0, 700),
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
    # The Aurora Console card is deliberately a little squarer than 16:9.
    # At the shipped 55% scale this resolves to the mockup's 188 x 112du.
    TileSizeToken("wide", 342.0, 204.0),
    TileSizeToken("square", 220.0, 220.0),
    TileSizeToken("poster", 200.0, 300.0),
)


def tile_size(aspect: str) -> TileSizeToken:
    for token in TILE_SIZES:
        if token.name == aspect:
            return token
    return TILE_SIZES[0]


# Type scales with the card, floored at the readable size. The tile-size
# preference used to shrink the card and leave a 30du title inside it, so
# "smaller tiles" cost every title past eleven characters — "Living Room
# Radio" became "Living Room R…". A row is a proportional object: below
# 1.0 the type comes with it, the row heading included (60du of fixed
# overhead per row, so a whole size step once five rows have to fit).
def scaled_type_size_du(name: str, size_scale: float) -> float:
    """The du size of `name` at a given tile scale, floored at readable."""
    return max(MIN_READABLE_SIZE_DU, type_token(name).size_du * size_scale)


TILE_PADDING_DU: float = 20.0
TILE_GAP_DU: float = 16.0
ROW_GAP_DU: float = 30.0
CORNER_RADIUS_DU: float = 18.0
ROW_HEADING_GAP_DU: float = 14.0
STATUS_BAR_HEIGHT_DU: float = 76.0

CONSOLE_WIDTH_DU: float = 336.0
CONTENT_GUTTER_DU: float = 48.0
ACTION_BAR_HEIGHT_DU: float = 88.0
CONSOLE_GAP_DU: float = 18.0
# The rail's insets and its blocks' padding. Here rather than in the CSS
# generator because the sidebar sizes the now-playing card off them.
CONSOLE_INSET_X_DU: float = 30.0
CONSOLE_INSET_Y_DU: float = 34.0
CONSOLE_BLOCK_PAD_DU: float = 20.0
# The now-playing covers. The primary one is this size only while it sits
# beside the text; given the height it stands above it, block-wide.
NOW_PLAYING_COVER_DU: float = 76.0
NOW_PLAYING_SOURCE_COVER_DU: float = 30.0
# Transparent padding carried inside every tile widget's own footprint, so
# the focus scale-up has somewhere to render without the row viewport's clip
# cutting into it.
TILE_BLEED_DU: float = 56.0
FOCUS_RING_DU: float = 3.0

SAFE_AREA_DEFAULT_PERCENT: float = 4.5
SAFE_AREA_MIN_PERCENT: float = 2.0
SAFE_AREA_MAX_PERCENT: float = 8.0

# The focused row's fixed vertical anchor (§6.1): rows above and below
# translate, the focused row does not move. Clamped against the content
# bounds by ui/home.py so a short catalogue doesn't float in dead space.
ROW_ANCHOR_FRACTION: float = 0.38

FOCUS_SCALE_REST: float = 1.0
FOCUS_SCALE_FOCUSED: float = 1.045

# Chrome's --force-device-scale-factor is computed from the same du scale as
# the UI and clamped to this range (§6.3): on a 4K TV a factor of 1.0 makes
# web UI unreadable at three metres.
BROWSER_SCALE_MIN: float = 1.0
BROWSER_SCALE_MAX: float = 3.0

REFERENCE_VIEWPORT_HEIGHT_PX: float = 1080.0

# Bottom-corner chrome can sit closer to the panel edge than navigable
# content. Keeping this separate from the safe area lets the rows and top
# controls retain their television overscan protection while the two small
# home-screen readouts use the otherwise empty bottom edge.
BOTTOM_CHROME_MARGIN_DU: float = 22.0

# Two lines of type plus the space around them: the bottom strip that says
# what the cursor is on. Reserved in the home screen's bottom inset so the
# rows never scroll underneath it. A fallback only — `HomeView._bottom_inset`
# measures the real widget, because this figure cannot follow the safe-area
# preference or a font substitution.
DETAIL_BAR_HEIGHT_DU = 78.0

# One line of small type in a pill: `ui/legend.py`, bottom right. Used by
# `ui/remotehint.py` to stand clear of it, which is the only reason the
# height has to be known anywhere but inside the widget.
LEGEND_HEIGHT_DU = 46.0


def design_units_to_px(du: float, viewport_height_px: int) -> float:
    """Convert a design-unit value to pixels for a given viewport height."""
    return du * (viewport_height_px / REFERENCE_VIEWPORT_HEIGHT_PX)


def browser_scale_factor(viewport_height_px: int) -> float:
    """The --force-device-scale-factor for spawned browser windows (§6.3),
    derived from the same du scale as the UI and clamped to [1.0, 3.0]."""
    raw = viewport_height_px / REFERENCE_VIEWPORT_HEIGHT_PX
    return max(BROWSER_SCALE_MIN, min(BROWSER_SCALE_MAX, round(raw, 2)))

# SPDX-License-Identifier: GPL-3.0-or-later
"""The tile widget (§7.3): spring-driven scale, light-fall bloom, and the
four artwork levels of §7.4.

The tile draws itself in `do_snapshot` rather than nesting CSS-styled
boxes. That's not a stylistic preference — it's forced by three things the
GTK4 box model can't do:

* **scale on focus.** GTK4 CSS has no `transform`, so the 1.0 -> 1.09
  growth has to be a `Gsk.Transform` driven by an `Adw.SpringAnimation`.
* **the bloom** (§7.3 stage 2). A blurred, accent-tinted copy of the tile's
  bounds rendered *beneath* its neighbours needs `Gtk.Snapshot.push_blur`,
  which only exists inside a snapshot implementation.
* **the generated artwork cards** (§7.4 levels 3 and 4). A tile with no
  artwork must look designed, not broken: an icon centred on a gradient
  built from that icon's own dominant colour, with a vignette and the title
  in the display face. That's a gradient stack, not a background-image.

Everything is sized from the du scale (`ui/scale.py`), so a tile is
320x180du on a 1080p TV and twice that on an unscaled 4K one.

The widget's footprint is deliberately larger than its visual box by
`TileMetrics.bleed` on every side: room for the scale-up and the bloom to
render before the row viewport in ui/home.py clips. The padding is
transparent and `do_contains` excludes it, so neighbouring tiles' footprints
can overlap without either one stealing the other's clicks.
"""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, Graphene, Gsk, Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.services.artwork import Artwork, glow_color  # noqa: E402
from salon.ui import theme  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

# Tighter than the brief's literal 0.82/320 — that combination read as
# loose and bouncy on a real screen (see DECISIONS.md). A higher damping
# ratio cuts the overshoot almost entirely and a higher stiffness keeps it
# fast; it's still a spring, so reversing direction mid-flight settles
# physically instead of snapping onto a new curve.
SPRING_DAMPING_RATIO = 0.92
SPRING_MASS = 1.0
SPRING_STIFFNESS = 500.0

# Bundled faces aren't installed yet (data/fonts/ is empty), so both stacks
# end in generic families rather than assuming Archivo/Inter are present —
# Ubuntu, Fedora and the Flatpak runtimes disagree about what is.
# GTK collects an accessible tristate as a plain int; handing it the enum
# member boxes a GValue of the enum's own type and GTK warns and drops the
# update, so the state silently never lands.
_TRISTATE_TRUE = int(Gtk.AccessibleTristate.TRUE)
_TRISTATE_FALSE = int(Gtk.AccessibleTristate.FALSE)

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


def metrics_for(
    scale: Scale, aspect: str = "wide", *, size_scale: float = 1.0
) -> TileMetrics:
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


_SURFACE_0 = _parse(tokens.color("surface-0"))
_SURFACE_1 = _parse(tokens.color("surface-1"))
_TEXT_PRIMARY = _parse(tokens.color("text-primary"))
_TEXT_SECONDARY = _parse(tokens.color("text-secondary"))
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


class TileWidget(Gtk.Widget):
    """One tile. Focus drives a single 0..1 spring value; scale, bloom
    intensity, ring opacity and the brightness lift are all derived from it,
    so they can never disagree with each other mid-animation."""

    def __init__(
        self,
        tile: Tile,
        artwork: Artwork,
        metrics: TileMetrics,
        scale: Scale,
        *,
        animations_enabled: bool = True,
    ) -> None:
        super().__init__()
        self.tile = tile
        self._artwork = artwork
        self._metrics = metrics
        self._scale = scale
        self._animations_enabled = animations_enabled
        self._focus_amount = 0.0
        self._focused = False

        self.set_overflow(Gtk.Overflow.VISIBLE)

        # The tile paints itself, so there is no child label for GTK to
        # derive an accessible name from: to a screen reader this widget is
        # a blank rectangle unless it says what it is. Salon runs its own
        # focus model (nothing here ever takes GTK focus), so the *cursor*
        # is published as SELECTED here and as ACTIVE_DESCENDANT on the
        # container — the same aria-activedescendant pattern any composite
        # widget uses when the container keeps the keyboard focus.
        self.set_accessible_role(Gtk.AccessibleRole.BUTTON)
        self.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            [tile.title, tile.subtitle or ""],
        )
        self.update_state([Gtk.AccessibleState.SELECTED], [_TRISTATE_FALSE])

        target = Adw.CallbackAnimationTarget.new(self._on_focus_tick)
        self._animation = Adw.SpringAnimation.new(
            self,
            0.0,
            0.0,
            Adw.SpringParams.new(SPRING_DAMPING_RATIO, SPRING_MASS, SPRING_STIFFNESS),
            target,
        )

        title = tokens.type_token("tile-title")
        subtitle = tokens.type_token("tile-subtitle")
        self._title_font = font_description(DISPLAY_FAMILY, scale.du(title.size_du), title.weight)
        self._subtitle_font = font_description(
            BODY_FAMILY, scale.du(subtitle.size_du), subtitle.weight
        )

    @property
    def artwork_accent(self) -> Gdk.RGBA:
        """The colour this tile is built around — its explicit `accent`, the
        dominant colour of its artwork, or a hue hashed from its id. The
        backdrop and the launching overlay reuse it so the whole screen
        agrees about what colour the focused thing is."""
        return self._artwork.accent

    # --- geometry --------------------------------------------------------

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        if orientation == Gtk.Orientation.HORIZONTAL:
            size = round(self._metrics.outer_width)
        else:
            size = round(self._metrics.outer_height)
        return (size, size, -1, -1)

    def do_contains(self, x: float, y: float) -> bool:
        """Only the visual box is hit-testable, never the transparent bleed.

        Adjacent tiles' footprints overlap by design (the bleed is wider
        than the gap), so without this a click in the gap would land on
        whichever tile happened to be later in the child list rather than on
        the tile the user aimed at.
        """
        bleed = self._metrics.bleed
        return (
            bleed <= x <= bleed + self._metrics.width
            and bleed <= y <= bleed + self._metrics.height
        )

    # --- focus animation -------------------------------------------------

    def set_focused(self, focused: bool) -> None:
        if focused == self._focused:
            return
        self._focused = focused
        self.update_state(
            [Gtk.AccessibleState.SELECTED],
            [_TRISTATE_TRUE if focused else _TRISTATE_FALSE],
        )
        target_value = 1.0 if focused else 0.0
        if not self._animations_enabled:
            # §7.2's reduced-motion rule: focus changes become instant, but
            # the focus indicator itself must stay unmistakable — the ring
            # and bloom are drawn from the same value, so jumping it to the
            # endpoint keeps the treatment at full strength.
            self._on_focus_tick(target_value)
            return
        self._animation.set_value_from(self._focus_amount)
        self._animation.set_value_to(target_value)
        self._animation.play()

    def _on_focus_tick(self, value: float) -> None:
        self._focus_amount = value
        self.queue_draw()

    # --- drawing ---------------------------------------------------------

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        metrics = self._metrics
        focus = max(0.0, min(1.0, self._focus_amount))

        if focus > 0.01:
            self._snapshot_bloom(snapshot, focus)

        # Scale about the visual box's own centre. Gsk.Transform is
        # immutable with chaining semantics in PyGObject (§11) — every step
        # here returns a new transform rather than mutating the receiver.
        scale = tokens.FOCUS_SCALE_REST + focus * (
            tokens.FOCUS_SCALE_FOCUSED - tokens.FOCUS_SCALE_REST
        )
        center = _point(metrics.bleed + metrics.width / 2.0, metrics.bleed + metrics.height / 2.0)
        transform = Gsk.Transform.new().translate(center)
        transform = transform.scale(scale, scale)
        transform = transform.translate(_point(-center.x, -center.y))

        snapshot.save()
        snapshot.transform(transform)
        self._snapshot_card(snapshot, focus)
        snapshot.restore()

    def _snapshot_bloom(self, snapshot: Gtk.Snapshot, focus: float) -> None:
        """§7.1's light-fall: the focused tile casts a soft warm bloom onto
        its neighbours, as though a lamp turned toward it. Bounded to the
        tile's own footprint, so the blur cost stays small even on the weak
        HTPC GPUs §7.3 warns about — unlike a full-screen backdrop blur,
        this is a single small region and only ever one tile at a time."""
        metrics = self._metrics
        blur = self._scale.du(tokens.BLOOM_BLUR_DU)
        offset = self._scale.du(tokens.BLOOM_OFFSET_DU) * focus
        # Slightly *larger* than the tile, not inset: the card is opaque and
        # covers whatever is drawn under it, so a bloom confined to the
        # tile's own bounds is visible only as the few pixels of feather the
        # blur pushes past the edge. Spreading it wider is what turns the
        # effect from an outline into light spilling onto the neighbours.
        spread = metrics.width * 0.03

        bounds = _rect(
            metrics.bleed - spread,
            metrics.bleed - spread + offset,
            metrics.width + 2 * spread,
            metrics.height + 2 * spread,
        )
        snapshot.push_blur(blur)
        snapshot.append_color(
            _with_alpha(glow_color(self._artwork.accent), tokens.BLOOM_ALPHA * focus),
            bounds,
        )
        snapshot.pop()

    def _snapshot_card(self, snapshot: Gtk.Snapshot, focus: float) -> None:
        metrics = self._metrics
        rect = _rect(metrics.bleed, metrics.bleed, metrics.width, metrics.height)
        rounded = _rounded(rect, metrics.radius)

        snapshot.push_rounded_clip(rounded)
        if self._artwork.texture is not None:
            self._snapshot_texture(snapshot, rect)
        else:
            self._snapshot_generated(snapshot, rect)
        self._snapshot_vignette(snapshot, rect)
        self._snapshot_labels(snapshot, rect)
        if focus > 0.01:
            # A brightness lift, not just an outline — the focused tile is
            # meant to read as lit, and this is what carries that when
            # animations are off and the scale never happens.
            snapshot.append_color(_with_alpha(_TEXT_PRIMARY, 0.07 * focus), rect)
        snapshot.pop()

        # A hairline edge so a dark tile still separates from a dark
        # backdrop; the accent ring replaces it as focus comes up.
        hairline = max(1.0, self._scale.du(1.0))
        edge = _with_alpha(_TEXT_PRIMARY, 0.10 * (1.0 - focus))
        snapshot.append_border(rounded, [hairline] * 4, [edge] * 4)

        if focus > 0.01:
            ring_width = self._scale.du(tokens.FOCUS_RING_DU)
            ring = _with_alpha(theme.accent(), focus)
            snapshot.append_border(rounded, [ring_width] * 4, [ring] * 4)

    def _snapshot_texture(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
        """Cover-fit: fill the tile, crop the overflow, never letterbox."""
        texture = self._artwork.texture
        assert texture is not None
        width = float(texture.get_width())
        height = float(texture.get_height())
        if width <= 0 or height <= 0:
            return
        scale = max(rect.get_width() / width, rect.get_height() / height)
        drawn_width = width * scale
        drawn_height = height * scale
        snapshot.append_scaled_texture(
            texture,
            Gsk.ScalingFilter.TRILINEAR,
            _rect(
                rect.get_x() + (rect.get_width() - drawn_width) / 2.0,
                rect.get_y() + (rect.get_height() - drawn_height) / 2.0,
                drawn_width,
                drawn_height,
            ),
        )
        # Scrim under the title, so a light image never swallows the text.
        scrim_height = rect.get_height() * 0.55
        scrim = _rect(
            rect.get_x(), rect.get_y() + rect.get_height() - scrim_height,
            rect.get_width(), scrim_height,
        )
        snapshot.append_linear_gradient(
            scrim,
            _point(scrim.get_x(), scrim.get_y()),
            _point(scrim.get_x(), scrim.get_y() + scrim_height),
            _stops((0.0, _TRANSPARENT), (1.0, _with_alpha(_SURFACE_0, 0.92))),
        )

    def _snapshot_generated(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
        """§7.4 levels 3 and 4: an icon (or the title's initial) on a
        gradient derived from the tile's own colour. Generous padding, a
        soft top-light, and the title below — this has to look designed,
        because for most tiles it is what the user actually sees."""
        accent = self._artwork.accent
        top = _mix(_SURFACE_1, accent, 0.26)
        bottom = _mix(_SURFACE_0, accent, 0.07)
        snapshot.append_linear_gradient(
            rect,
            _point(rect.get_x(), rect.get_y()),
            _point(rect.get_x() + rect.get_width() * 0.35, rect.get_y() + rect.get_height()),
            _stops((0.0, top), (1.0, bottom)),
        )
        # A soft light from above — the room's lamp, not a UI highlight.
        snapshot.append_radial_gradient(
            rect,
            _point(rect.get_x() + rect.get_width() / 2.0, rect.get_y()),
            rect.get_width() * 0.85,
            rect.get_height() * 0.75,
            0.0,
            1.0,
            _stops((0.0, _with_alpha(_TEXT_PRIMARY, 0.08)), (1.0, _TRANSPARENT)),
        )

        icon_box = self._icon_box(rect)
        if self._artwork.icon is not None:
            self._snapshot_icon(snapshot, icon_box)
        else:
            self._snapshot_initial(snapshot, icon_box)

    def _icon_box(self, rect: Graphene.Rect) -> Graphene.Rect:
        """Centred in the space above the title band, not in the tile — an
        icon centred on the tile itself reads as sitting too low once the
        title is drawn under it."""
        title_band = self._scale.du(tokens.type_token("tile-title").size_du * 1.9)
        available_height = rect.get_height() - title_band
        size = min(available_height * 0.68, rect.get_width() * 0.34)
        return _rect(
            rect.get_x() + (rect.get_width() - size) / 2.0,
            rect.get_y() + (available_height - size) / 2.0,
            size,
            size,
        )

    def _snapshot_icon(self, snapshot: Gtk.Snapshot, box: Graphene.Rect) -> None:
        icon = self._artwork.icon
        assert icon is not None
        snapshot.save()
        snapshot.translate(_point(box.get_x(), box.get_y()))
        if self._artwork.icon_is_symbolic:
            # Symbolic icons are single-colour stencils; drawn plainly they
            # come out flat mid-grey, which is exactly the "unfinished"
            # look the generated card exists to avoid.
            icon.snapshot_symbolic(
                snapshot,
                box.get_width(),
                box.get_height(),
                [_with_alpha(_TEXT_PRIMARY, 0.92)],
            )
        else:
            icon.snapshot(snapshot, box.get_width(), box.get_height())
        snapshot.restore()

    def _snapshot_initial(self, snapshot: Gtk.Snapshot, box: Graphene.Rect) -> None:
        """§7.4 level 4: no artwork and no icon — the tile's initial, large
        and quiet, on the generated gradient."""
        initial = (self.tile.title or "?").strip()[:1].upper()
        layout = self.create_pango_layout(initial)
        layout.set_font_description(
            font_description(DISPLAY_FAMILY, box.get_height() * 0.95, 700)
        )
        width, height = layout.get_pixel_size()
        snapshot.save()
        snapshot.translate(
            _point(
                box.get_x() + (box.get_width() - width) / 2.0,
                box.get_y() + (box.get_height() - height) / 2.0,
            )
        )
        snapshot.append_layout(layout, _with_alpha(_TEXT_PRIMARY, 0.30))
        snapshot.restore()

    def _snapshot_labels(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
        padding = self._scale.du(20.0)
        available = rect.get_width() - 2 * padding

        subtitle_layout = None
        subtitle_height = 0.0
        if self.tile.subtitle:
            subtitle_layout = self._layout(self.tile.subtitle, self._subtitle_font, available)
            subtitle_height = subtitle_layout.get_pixel_size()[1]

        title_layout = self._layout(self.tile.title, self._title_font, available)
        title_height = title_layout.get_pixel_size()[1]

        bottom = rect.get_y() + rect.get_height() - padding
        if subtitle_layout is not None:
            snapshot.save()
            snapshot.translate(_point(rect.get_x() + padding, bottom - subtitle_height))
            snapshot.append_layout(subtitle_layout, _TEXT_SECONDARY)
            snapshot.restore()
            bottom -= subtitle_height + self._scale.du(2.0)

        snapshot.save()
        snapshot.translate(_point(rect.get_x() + padding, bottom - title_height))
        snapshot.append_layout(title_layout, _TEXT_PRIMARY)
        snapshot.restore()

    def _layout(
        self, text: str, font: Pango.FontDescription, width: float
    ) -> Pango.Layout:
        layout = self.create_pango_layout(text)
        layout.set_font_description(font)
        layout.set_width(int(width * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_single_paragraph_mode(True)
        return layout

    def _snapshot_vignette(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
        snapshot.append_radial_gradient(
            rect,
            _point(rect.get_x() + rect.get_width() / 2.0, rect.get_y() + rect.get_height() / 2.0),
            rect.get_width() * 0.72,
            rect.get_height() * 0.72,
            0.55,
            1.0,
            _stops((0.0, _TRANSPARENT), (1.0, _with_alpha(_SURFACE_0, 0.45))),
        )

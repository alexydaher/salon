# SPDX-License-Identifier: GPL-3.0-or-later
"""Interactive tile state; painting is delegated to focused renderers."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, Gsk, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.services.artwork import Artwork  # noqa: E402
from salon.ui import motion, theme  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

# Tighter than the brief's literal 0.82/320 — that combination read as
# loose and bouncy on a real screen. A higher damping
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

from salon.ui.tile_artwork_renderer import TileArtworkRenderer  # noqa: E402
from salon.ui.tile_geometry import (  # noqa: E402
    BODY_FAMILY,
    DISPLAY_FAMILY,
    TileMetrics,
    _point,
    _rect,
    _rounded,
    _with_alpha,
    font_description,
    metrics_for,  # noqa: F401 - compatibility re-export
)
from salon.ui.tile_text_renderer import TileTextRenderer  # noqa: E402


class TileWidget(Gtk.Widget, TileArtworkRenderer, TileTextRenderer):
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
        show_subtitle: bool = True,
    ) -> None:
        super().__init__()
        self.tile = tile
        self._artwork = artwork
        self._metrics = metrics
        self._scale = scale
        self._animations_enabled = animations_enabled
        self._show_subtitle = show_subtitle
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
            motion.spring_params(),
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
            bleed <= x <= bleed + self._metrics.width and bleed <= y <= bleed + self._metrics.height
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
            self.snapshot_bloom(snapshot, focus)

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

    def _snapshot_card(self, snapshot: Gtk.Snapshot, focus: float) -> None:
        metrics = self._metrics
        rect = _rect(metrics.bleed, metrics.bleed, metrics.width, metrics.height)
        rounded = _rounded(rect, metrics.radius)

        snapshot.push_rounded_clip(rounded)
        if self._artwork.texture is not None:
            self.snapshot_texture(snapshot, rect)
        else:
            self.snapshot_generated(snapshot, rect)
        self.snapshot_vignette(snapshot, rect)
        self.snapshot_labels(snapshot, rect)
        if focus > 0.01:
            # A brightness lift, not just an outline — the focused tile is
            # meant to read as lit, and this is what carries that when
            # animations are off and the scale never happens.
            snapshot.append_color(_with_alpha(theme.color("text-primary"), 0.07 * focus), rect)
        snapshot.pop()

        # A hairline edge so a dark tile still separates from a dark
        # backdrop; the accent ring replaces it as focus comes up.
        hairline = max(1.0, self._scale.du(1.0))
        edge = _with_alpha(theme.color("text-primary"), 0.10 * (1.0 - focus))
        snapshot.append_border(rounded, [hairline] * 4, [edge] * 4)

        if focus > 0.01:
            ring_width = self._scale.du(tokens.FOCUS_RING_DU)
            ring = _with_alpha(theme.accent(), focus)
            snapshot.append_border(rounded, [ring_width] * 4, [ring] * 4)

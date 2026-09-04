# SPDX-License-Identifier: GPL-3.0-or-later
"""Artwork, icon, bloom, and generated-card painting for a tile."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Graphene, Gsk, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.services.artwork import glow_color  # noqa: E402
from salon.ui import theme  # noqa: E402
from salon.ui.tile_geometry import (  # noqa: E402
    _TRANSPARENT,
    DISPLAY_FAMILY,
    _mix,
    _point,
    _rect,
    _stops,
    _with_alpha,
    font_description,
)

# How much of the tile's own colour reaches its glass, top and bottom.
# Enough that a row of six reads as six things across a room; short of the
# phone's full wash. See `TileArtworkRenderer.snapshot_generated`.
_TINT_TOP = 0.30
_TINT_BOTTOM = 0.14


class TileArtworkRenderer:
    def snapshot_bloom(self, snapshot: Gtk.Snapshot, focus: float) -> None:
        """§7.1's light-fall: the focused tile casts a soft warm bloom onto
        its neighbours, as though a lamp turned toward it. Bounded to the
        tile's own footprint, so the blur cost stays small even on the weak
        HTPC GPUs §7.3 warns about — unlike a full-screen backdrop blur,
        this is a single small region and only ever one tile at a time."""
        metrics = self._metrics
        blur = metrics.bloom_blur
        offset = metrics.bloom_offset * focus
        # Slightly *larger* than the tile, not inset: the card is opaque and
        # covers whatever is drawn under it, so a bloom confined to the
        # tile's own bounds is visible only as the few pixels of feather the
        # blur pushes past the edge. Spreading it wider is what turns the
        # effect from an outline into light spilling onto the neighbours.
        spread = metrics.width * 0.02

        bounds = _rect(
            metrics.bleed - spread,
            metrics.bleed - spread + offset,
            metrics.width + 2 * spread,
            metrics.height + 2 * spread,
        )
        snapshot.push_blur(blur)
        snapshot.append_color(
            _with_alpha(glow_color(theme.accent()), tokens.BLOOM_ALPHA * focus),
            bounds,
        )
        snapshot.pop()

    def snapshot_texture(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
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
        scrim_height = rect.get_height() * 0.58
        scrim = _rect(
            rect.get_x(),
            rect.get_y() + rect.get_height() - scrim_height,
            rect.get_width(),
            scrim_height,
        )
        snapshot.append_linear_gradient(
            scrim,
            _point(scrim.get_x(), scrim.get_y()),
            _point(scrim.get_x(), scrim.get_y() + scrim_height),
            _stops(
                (0.0, _TRANSPARENT),
                (0.46, _with_alpha(theme.color("surface-0"), 0.16)),
                (1.0, _with_alpha(theme.color("surface-0"), 0.88)),
            ),
        )

    def snapshot_generated(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
        """§7.4 levels 3 and 4: an icon (or the title's initial) on the
        Aurora Console's smoked glass, tinted by the tile's own colour.

        The glass used to be identical on every card, reserving colour for
        focus. On screen that was the weakest thing in the interface: the
        shipped starter seeds five streaming services that all declare
        `icon_name="web-browser-symbolic"`, so the flagship row drew five
        identical rectangles — and the icon was what was meant to tell them
        apart. The phone remote, fed the same catalogue, draws each tile as
        its own accent gradient and is plainly more legible; one catalogue
        cannot have two answers, and the phone had the better one.

        A tint, not the phone's full wash: the row rhythm the neutral pane
        bought is worth keeping. `Artwork.accent` is the tile's explicit
        `accent`, else its artwork's dominant colour, else a hue hashed from
        its id, so a catalogue that sets no colours still gets
        distinguishable cards — §7.4's "hashed gradient". It also makes the
        editor's accent row mean something. See DECISIONS 2026-09-04.
        """
        accent = self._artwork.accent
        # Lift surface-2 just enough to retain an edge over a dark corner,
        # then keep enough transparency for the ambient fields to show
        # through.  This is the GTK/GSK counterpart of the mockup's
        # rgba(52, 68, 92, .42) pane.
        glass = _mix(theme.color("surface-2"), theme.color("text-primary"), 0.06)
        top = _with_alpha(_mix(glass, accent, _TINT_TOP), 0.66)
        bottom = _with_alpha(_mix(theme.color("surface-1"), accent, _TINT_BOTTOM), 0.54)
        snapshot.append_linear_gradient(
            rect,
            _point(rect.get_x(), rect.get_y()),
            _point(rect.get_x() + rect.get_width() * 0.22, rect.get_y() + rect.get_height()),
            _stops((0.0, top), (1.0, bottom)),
        )
        icon_box = self._icon_box(rect)
        if self._artwork.icon_texture is not None:
            self.snapshot_icon_texture(snapshot, icon_box)
        elif self._artwork.icon is not None:
            self.snapshot_icon(snapshot, icon_box)
        else:
            self.snapshot_initial(snapshot, icon_box)

    def _icon_box(self, rect: Graphene.Rect) -> Graphene.Rect:
        """Centred on the card horizontally, and centred in the space above
        the title band vertically.

        The whole card is a centred composition — mark over name, both on
        the card's own axis — so there is one line of symmetry rather than a
        mark and a title each doing their own thing. `snapshot_labels`
        centres the text against the same axis; the two have to agree or
        neither reads as deliberate.

        Vertical is centred in the space *above* the title band rather than
        in the tile: an icon centred on the tile itself reads as sitting too
        low once the title is drawn under it.
        """
        if self._horizontal_content:
            size = min(rect.get_height() * 0.46, rect.get_width() * 0.18)
            return _rect(
                rect.get_x() + self._metrics.padding,
                rect.get_y() + (rect.get_height() - size) / 2.0,
                size,
                size,
            )
        title_band = self._metrics.title_size * 1.9
        available_height = rect.get_height() - title_band
        # 40/112 in the reference Home card.  The previous 0.68 share made
        # generic icons about 25% larger than real app marks and caused the
        # artwork to dominate the name at sofa distance.
        size = min(rect.get_height() * 0.36, rect.get_width() * 0.24)
        return _rect(
            rect.get_x() + (rect.get_width() - size) / 2.0,
            rect.get_y() + (available_height - size) / 2.0,
            size,
            size,
        )

    def snapshot_icon_texture(self, snapshot: Gtk.Snapshot, box: Graphene.Rect) -> None:
        """A site's own icon, fit *inside* the icon box and never cropped.

        Contain-fit rather than the card's cover-fit: these arrive square,
        or nearly, and a site that ships a 180x120 mark should see it whole
        rather than have its edges cut off to make a square.
        """
        texture = self._artwork.icon_texture
        assert texture is not None
        width = float(texture.get_width())
        height = float(texture.get_height())
        if width <= 0 or height <= 0:
            return
        scale = min(box.get_width() / width, box.get_height() / height)
        drawn_width = width * scale
        drawn_height = height * scale
        # Centred in the box on both axes: the box is square and a
        # contain-fit leaves a tall, narrow mark short of it, so anything
        # but centring here would put that one tile's logo off the card's
        # axis while every neighbour sits on it.
        snapshot.append_scaled_texture(
            texture,
            Gsk.ScalingFilter.TRILINEAR,
            _rect(
                box.get_x() + (box.get_width() - drawn_width) / 2.0,
                box.get_y() + (box.get_height() - drawn_height) / 2.0,
                drawn_width,
                drawn_height,
            ),
        )

    def snapshot_icon(self, snapshot: Gtk.Snapshot, box: Graphene.Rect) -> None:
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
                [_with_alpha(theme.color("text-primary"), 0.92)],
            )
        else:
            icon.snapshot(snapshot, box.get_width(), box.get_height())
        snapshot.restore()

    def snapshot_initial(self, snapshot: Gtk.Snapshot, box: Graphene.Rect) -> None:
        """§7.4 level 4: no artwork and no icon — the tile's initial, large
        and quiet, on the generated gradient."""
        initial = (self.tile.title or "?").strip()[:1].upper()
        layout = self.create_pango_layout(initial)
        layout.set_font_description(font_description(DISPLAY_FAMILY, box.get_height() * 0.95, 700))
        width, height = layout.get_pixel_size()
        snapshot.save()
        # Centred on the glyph's own width, not the box's: a single letter
        # is much narrower than a box sized for the widest one ("I" against
        # a box sized for "W"), so using the box alone would leave the
        # initial off the axis the mark and the title share.
        snapshot.translate(
            _point(
                box.get_x() + (box.get_width() - width) / 2.0,
                box.get_y() + (box.get_height() - height) / 2.0,
            )
        )
        snapshot.append_layout(layout, _with_alpha(theme.color("text-primary"), 0.30))
        snapshot.restore()

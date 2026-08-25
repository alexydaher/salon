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


class TileArtworkRenderer:
    def snapshot_bloom(self, snapshot: Gtk.Snapshot, focus: float) -> None:
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
        scrim_height = rect.get_height() * 0.55
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
            _stops((0.0, _TRANSPARENT), (1.0, _with_alpha(theme.color("surface-0"), 0.92))),
        )

    def snapshot_generated(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
        """§7.4 levels 3 and 4: an icon (or the title's initial) on a
        gradient derived from the tile's own colour. Generous padding, a
        soft top-light, and the title below — this has to look designed,
        because for most tiles it is what the user actually sees."""
        accent = self._artwork.accent
        top = _mix(theme.color("surface-1"), accent, 0.26)
        bottom = _mix(theme.color("surface-0"), accent, 0.07)
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
            _stops((0.0, _with_alpha(theme.color("text-primary"), 0.08)), (1.0, _TRANSPARENT)),
        )

        icon_box = self._icon_box(rect)
        if self._artwork.icon_texture is not None:
            self.snapshot_icon_texture(snapshot, icon_box)
        elif self._artwork.icon is not None:
            self.snapshot_icon(snapshot, icon_box)
        else:
            self.snapshot_initial(snapshot, icon_box)

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
        snapshot.translate(
            _point(
                box.get_x() + (box.get_width() - width) / 2.0,
                box.get_y() + (box.get_height() - height) / 2.0,
            )
        )
        snapshot.append_layout(layout, _with_alpha(theme.color("text-primary"), 0.30))
        snapshot.restore()

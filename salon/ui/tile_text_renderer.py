# SPDX-License-Identifier: GPL-3.0-or-later
"""Text and vignette painting for a tile."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Graphene, Gtk, Pango  # noqa: E402

from salon.ui import theme  # noqa: E402
from salon.ui.tile_geometry import _TRANSPARENT, _point, _stops, _with_alpha  # noqa: E402


class TileTextRenderer:
    def snapshot_labels(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
        padding = self._scale.du(20.0)
        available = rect.get_width() - 2 * padding

        subtitle_layout = None
        subtitle_height = 0.0
        # Off on the home screen, where the detail strip carries the same
        # string one row down and the card was saying it twice; on in the
        # all-apps grid and in search results, which have no strip and
        # where the subtitle is often the only thing telling two
        # near-identically named .desktop entries apart.
        if self.tile.subtitle and self._show_subtitle:
            subtitle_layout = self._layout(self.tile.subtitle, self._subtitle_font, available)
            subtitle_height = subtitle_layout.get_pixel_size()[1]

        title_layout = self._layout(self.tile.title, self._title_font, available)
        title_height = title_layout.get_pixel_size()[1]

        bottom = rect.get_y() + rect.get_height() - padding
        if subtitle_layout is not None:
            snapshot.save()
            snapshot.translate(_point(rect.get_x() + padding, bottom - subtitle_height))
            snapshot.append_layout(subtitle_layout, theme.color("text-secondary"))
            snapshot.restore()
            bottom -= subtitle_height + self._scale.du(2.0)

        snapshot.save()
        snapshot.translate(_point(rect.get_x() + padding, bottom - title_height))
        snapshot.append_layout(title_layout, theme.color("text-primary"))
        snapshot.restore()

    def _layout(self, text: str, font: Pango.FontDescription, width: float) -> Pango.Layout:
        layout = self.create_pango_layout(text)
        layout.set_font_description(font)
        layout.set_width(int(width * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_single_paragraph_mode(True)
        return layout

    def snapshot_vignette(self, snapshot: Gtk.Snapshot, rect: Graphene.Rect) -> None:
        snapshot.append_radial_gradient(
            rect,
            _point(rect.get_x() + rect.get_width() / 2.0, rect.get_y() + rect.get_height() / 2.0),
            rect.get_width() * 0.72,
            rect.get_height() * 0.72,
            0.55,
            1.0,
            _stops((0.0, _TRANSPARENT), (1.0, _with_alpha(theme.color("surface-0"), 0.45))),
        )

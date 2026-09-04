# SPDX-License-Identifier: GPL-3.0-or-later
"""Layered card material and focus chrome for tiles."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Graphene, Gsk, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui import theme  # noqa: E402
from salon.ui.tile_geometry import (  # noqa: E402
    _TRANSPARENT,
    _point,
    _rect,
    _rounded,
    _stops,
    _with_alpha,
)


def _inset(rect: Graphene.Rect, amount: float) -> Graphene.Rect:
    return _rect(
        rect.get_x() + amount,
        rect.get_y() + amount,
        max(0.0, rect.get_width() - amount * 2.0),
        max(0.0, rect.get_height() - amount * 2.0),
    )


class TileSurfaceRenderer:
    """Paint a calm resting card and precise, layered focus treatment."""

    def _snapshot_card(self, snapshot: Gtk.Snapshot, focus: float) -> None:
        metrics = self._metrics
        rect = _rect(metrics.bleed, metrics.bleed, metrics.width, metrics.height)
        rounded = _rounded(rect, metrics.radius)

        self._snapshot_shadow(snapshot, rounded, focus)
        snapshot.push_rounded_clip(rounded)
        if self._artwork.texture is not None:
            self.snapshot_texture(snapshot, rect)
            self.snapshot_vignette(snapshot, rect)
        else:
            self.snapshot_generated(snapshot, rect)
        self._snapshot_surface_light(snapshot, rect, focus)
        self.snapshot_labels(snapshot, rect)
        snapshot.pop()
        self._snapshot_edge(snapshot, rect, rounded, focus)

    def _snapshot_shadow(
        self, snapshot: Gtk.Snapshot, rounded: Gsk.RoundedRect, focus: float
    ) -> None:
        # Keep elevation neutral. The accent belongs to the crisp focus ring,
        # not in a glow that spills beyond the selected tile.
        snapshot.append_outset_shadow(
            rounded,
            _with_alpha(theme.color("surface-0"), 0.28 + 0.10 * focus),
            0.0,
            self._scale.du(4.0 + 4.0 * focus),
            0.0,
            self._scale.du(14.0 + 8.0 * focus),
        )

    def _snapshot_surface_light(
        self, snapshot: Gtk.Snapshot, rect: Graphene.Rect, focus: float
    ) -> None:
        # A slim top light makes the glass edge legible. Focus strengthens
        # that reflection, rather than bleaching the entire card.
        height = rect.get_height() * 0.34
        sheen = _rect(rect.get_x(), rect.get_y(), rect.get_width(), height)
        snapshot.append_linear_gradient(
            sheen,
            _point(sheen.get_x(), sheen.get_y()),
            _point(sheen.get_x(), sheen.get_y() + height),
            _stops(
                (
                    0.0,
                    _with_alpha(theme.color("text-primary"), 0.055 + 0.035 * focus),
                ),
                (1.0, _TRANSPARENT),
            ),
        )

    def _snapshot_edge(
        self,
        snapshot: Gtk.Snapshot,
        rect: Graphene.Rect,
        rounded: Gsk.RoundedRect,
        focus: float,
    ) -> None:
        hairline = max(1.0, self._scale.du(1.0))
        neutral = _with_alpha(theme.color("text-primary"), 0.22 - 0.10 * focus)
        snapshot.append_border(rounded, [hairline] * 4, [neutral] * 4)
        if focus <= 0.01:
            return

        ring_width = self._scale.du(tokens.FOCUS_RING_DU)
        ring = _with_alpha(theme.accent(), 0.94 * focus)
        snapshot.append_border(rounded, [ring_width] * 4, [ring] * 4)

        # The inner glint keeps the focus edge crisp on both pale artwork
        # and very dark generated cards.
        inset = max(ring_width, self._scale.du(2.0))
        inner_rect = _inset(rect, inset)
        inner = _rounded(inner_rect, max(0.0, self._metrics.radius - inset))
        glint = _with_alpha(theme.color("text-primary"), 0.20 * focus)
        snapshot.append_border(inner, [hairline] * 4, [glint] * 4)

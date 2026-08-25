# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Layout, tile construction, and selection painting for the apps grid."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.focus import Bump, FocusModel  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services import appinfo  # noqa: E402
from salon.services.artwork import ArtworkResolver  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.tile import TileMetrics, TileWidget, metrics_for  # noqa: E402

_BUMP_DISTANCE_DU = 26.0
_TILE_SCALE = 1.0
_ASPECT = "square"


class AppsGridLayout:
    def __init__(self, owner: object) -> None:
        self._owner = owner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._owner, name)

    def _metrics(self) -> TileMetrics:
        return metrics_for(self._scale, _ASPECT, size_scale=_TILE_SCALE)

    def _origin(self, metrics: TileMetrics) -> tuple[float, float]:
        """Where the first tile *widget* goes inside the viewport.

        A widget sits `bleed` up and left of its own card, so the card lands
        at the safe margin while the glow it draws around itself still has
        room inside the clip. The horizontal origin can't go negative — that
        is exactly the clipping this fixes — so where the bleed is wider
        than the safe area (they're 56du and 54du at the reference size) the
        card starts at the bleed instead, two pixels right of the title.
        """
        return (max(0.0, self._safe_margin - metrics.bleed), 0.0)

    def _usable_width(self, metrics: TileMetrics) -> float:
        """The width the cards themselves may occupy: the viewport now runs
        edge to edge, and the safe area has to come back out of it."""
        left, _ = self._origin(metrics)
        return max(1.0, self._viewport_width - left - metrics.bleed - self._safe_margin)

    def _on_resized(self, width: int, height: int) -> None:
        self._viewport_width = width
        self._viewport_height = height
        metrics = self._metrics()
        # +gap because the last column needs no trailing gap; without it the
        # grid loses a column whenever the remainder is smaller than one.
        columns = max(1, int((self._usable_width(metrics) + metrics.gap) // metrics.step))
        if columns != self._columns:
            self._columns = columns
            self._rebuild()
        else:
            self._scroll_to_focused(animate=False)

    def _row_lengths(self) -> list[int]:
        rows, remainder = divmod(len(self._tiles), self._columns)
        lengths = [self._columns] * rows
        if remainder:
            lengths.append(remainder)
        return lengths

    def _rebuild(self) -> None:
        child = self._grid.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._grid.remove(child)
            child = next_child

        metrics = self._metrics()
        self._widgets = []
        for index, tile in enumerate(self._tiles):
            row, col = divmod(index, self._columns)
            artwork = self._artwork.resolve(tile, icon_size=round(metrics.height * 0.5))
            # Without the subtitle: at this card width every description
            # truncates to noise ("Access and m…", "Perform arith…"), and
            # the space it costs is what makes the title truncate too. The
            # description is shown in full for the focused app instead.
            widget = TileWidget(replace(tile, subtitle=None), artwork, metrics, self._scale)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_, i=index: self._click(i))
            widget.add_controller(click)
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", lambda *_, i=index: self._hover(i))
            widget.add_controller(motion)
            # Never a negative coordinate: the widget's transparent bleed is
            # what the bloom is drawn into, and a child placed above or left
            # of the viewport's own origin has that half of its glow clipped
            # away — which is the whole reason for _origin.
            left, top = self._origin(metrics)
            self._grid.put(
                widget,
                left + col * metrics.step,
                top + row * self._row_pitch(metrics),
            )
            self._widgets.append(widget)

        lengths = self._row_lengths()
        self._focus.set_row_lengths(lengths)
        left, top = self._origin(metrics)
        self._grid.set_size_request(
            max(1, round(left + self._columns * metrics.step + metrics.bleed)),
            # The trailing bleed is part of the content: without it the
            # scroll clamps with the last row's card flush against the
            # bottom edge and its bloom cut off there instead.
            max(1, round(top + len(lengths) * self._row_pitch(metrics) + metrics.bleed)),
        )
        self._legend.set_label(
            f"{len(self._tiles)} apps · OK opens · {Action.OPTIONS.value.upper()} "
            "pins one to Favourites · L1/R1 jumps a letter · BACK returns"
            if self._tiles
            else ""
        )
        if not self._tiles:
            self._set_hint("No applications were found on this machine.")
        self._rebuild_rail()
        self._update_selection(animate=False)

    # --- the A-Z rail ----------------------------------------------------

    @staticmethod
    def _initial(tile: Tile) -> str:
        """The letter a tile files under. Everything that isn't A-Z shares
        one bucket rather than getting a rail entry each — a rail with `0`,
        `2`, `4`, `7` and `Ø` in it is not a rail."""
        first = (tile.title or "?").strip()[:1].upper()
        return first if "A" <= first <= "Z" else "#"

    def _letters(self) -> list[tuple[str, int]]:
        """Each present letter and the index of its first tile, in order."""
        found: list[tuple[str, int]] = []
        seen: set[str] = set()
        for index, tile in enumerate(self._tiles):
            letter = self._initial(tile)
            if letter not in seen:
                seen.add(letter)
                found.append((letter, index))
        return found

    def _rebuild_rail(self) -> None:
        child = self._rail.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._rail.remove(child)
            child = following
        self._rail_labels = {}
        for letter, index in self._letters():
            label = Gtk.Label(label=letter)
            label.add_css_class("salon-letter")
            click = Gtk.GestureClick()
            click.connect("released", lambda *_, i=index: self._jump_to_index(i))
            label.add_controller(click)
            self._rail.append(label)
            self._rail_labels[letter] = label

    def _update_rail(self) -> None:
        tile = self.focused_tile
        current = self._initial(tile) if tile is not None else ""
        for letter, label in self._rail_labels.items():
            if letter == current:
                label.add_css_class("current")
            else:
                label.remove_css_class("current")

    def _jump_letter(self, delta: int) -> None:
        letters = self._letters()
        if not letters:
            return
        index = self._focused_index()
        # Which letter block the cursor is in right now.
        position = 0
        for i, (_letter, start) in enumerate(letters):
            if start <= index:
                position = i
            else:
                break
        # Going back from anywhere but the top of a block means "the top of
        # this block" — the same rule a music player's previous-track button
        # follows, and for the same reason: it is what a second press of the
        # button is for.
        if delta < 0 and letters[position][1] != index:
            target = position
        else:
            target = position + delta
        if not (0 <= target < len(letters)):
            distance = self._scale.du(_BUMP_DISTANCE_DU)
            self._scroll.bump(distance if delta < 0 else -distance)
            return
        self._jump_to_index(letters[target][1])

    def _row_pitch(self, metrics: TileMetrics) -> float:
        # Enough vertical room for the label under each card plus the gap.
        return metrics.height + metrics.gap

    def _focused_index(self) -> int:
        return self._focus.row * self._columns + self._focus.col

    def _update_selection(self, *, animate: bool = True) -> None:
        index = self._focused_index()
        for i, widget in enumerate(self._widgets):
            widget.set_focused(i == index)
        tile = self.focused_tile
        if tile is not None:
            self._set_hint(
                f"{tile.title} · {tile.subtitle}" if tile.subtitle else tile.title
            )
        self._update_rail()
        if 0 <= index < len(self._widgets):
            # Same aria-activedescendant pattern as the home screen: the
            # tiles never take GTK focus, so the container has to say which
            # of them the cursor is on.
            self._viewport.update_relation(
                [Gtk.AccessibleRelation.ACTIVE_DESCENDANT], [self._widgets[index]]
            )
        self._scroll_to_focused(animate=animate)

    def _scroll_to_focused(self, *, animate: bool) -> None:
        if not self._widgets or self._viewport_height <= 0:
            return
        metrics = self._metrics()
        pitch = self._row_pitch(metrics)
        _, origin_top = self._origin(metrics)
        # In viewport coordinates, including the bleed above the first card
        # and below the last, so a focused row is never scrolled to a
        # position where its own bloom is the thing hanging off the edge.
        top = origin_top + self._focus.row * pitch
        content_height = origin_top + len(self._row_lengths()) * pitch + metrics.bleed
        offset = 0.0
        if top + pitch + metrics.bleed > self._viewport_height:
            offset = self._viewport_height - (top + pitch + metrics.bleed)
        # Never past the end: a grid scrolled into empty space below the
        # last row reads as a rendering fault, and unlike the home screen
        # there is no anchor line here for the focused row to sit on.
        offset = max(min(0.0, self._viewport_height - content_height), min(0.0, offset))
        self._scroll.animate_to(offset) if animate else self._scroll.jump_to(offset)

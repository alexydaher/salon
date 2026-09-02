# SPDX-License-Identifier: GPL-3.0-or-later
"""Layout, tile construction, and selection painting for the apps grid."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.ui.appsgrid_alphabet import AppsGridAlphabet  # noqa: E402
from salon.ui.appsgrid_geometry import (  # noqa: E402
    column_count,
    grid_metrics,
    grouped_rows,
    horizontal_origin,
)
from salon.ui.tile import TileMetrics, TileWidget  # noqa: E402

_BUMP_DISTANCE_DU = 26.0


class AppsGridLayout(AppsGridAlphabet):
    def _metrics(self) -> TileMetrics:
        return grid_metrics(self._scale, self._tile_scale)

    def _column_count(self, metrics: TileMetrics) -> int:
        return column_count(self._viewport_width, self._safe_margin, metrics)

    def _relayout(self) -> None:
        """Recompute density and geometry after either scale changes."""
        self._columns = self._column_count(self._metrics())
        self._rebuild()

    def _origin(self, metrics: TileMetrics) -> tuple[float, float]:
        """Where the first tile *widget* goes inside the viewport.

        A widget sits `bleed` up and left of its own card, so the card lands
        at the safe margin while the glow it draws around itself still has
        room inside the clip. The horizontal origin can't go negative — that
        is exactly the clipping this fixes — so where the bleed is wider
        than the safe area (they're 56du and 54du at the reference size) the
        card starts at the bleed instead, two pixels right of the title.
        """
        return (horizontal_origin(self._safe_margin, metrics), 0.0)

    def _usable_width(self, metrics: TileMetrics) -> float:
        left, _ = self._origin(metrics)
        return max(1.0, self._viewport_width - left - metrics.bleed - self._safe_margin)

    def _on_resized(self, width: int, height: int) -> None:
        self._viewport_width = width
        self._viewport_height = height
        metrics = self._metrics()
        columns = self._column_count(metrics)
        if columns != self._columns:
            self._columns = columns
            self._rebuild()
        else:
            self._scroll_to_focused(animate=False)

    def _row_lengths(self) -> list[int]:
        return [len(row) for row in self._grid_rows]

    def _rebuild(self) -> None:
        focused_index = self._focused_index()
        child = self._grid.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._grid.remove(child)
            child = next_child

        metrics = self._metrics()
        self._widgets = []
        self._item_tops: list[float] = [0.0] * len(self._tiles)
        left, _ = self._origin(metrics)
        y = 0.0
        heading_height = self._scale.du(18.0)
        heading_gap = self._scale.du(13.0)
        group_gap = self._scale.du(26.0)
        letters = self._letters()
        self._grid_rows = grouped_rows(
            len(self._tiles), self._columns, [start for _letter, start in letters]
        )
        self._index_positions = {
            index: (row, col)
            for row, indices in enumerate(self._grid_rows)
            for col, index in enumerate(indices)
        }
        for group, (letter, start) in enumerate(letters):
            end = letters[group + 1][1] if group + 1 < len(letters) else len(self._tiles)
            count = end - start
            rows = max(1, (count + self._columns - 1) // self._columns)
            heading = self._group_heading(letter)
            heading.set_size_request(
                round(self._columns * metrics.step - metrics.gap), round(heading_height)
            )
            self._grid.put(
                heading,
                left + metrics.bleed,
                y + metrics.bleed - heading_height - heading_gap,
            )
            for local, index in enumerate(range(start, end)):
                row, col = divmod(local, self._columns)
                widget = self._tile_widget(index, metrics)
                top = y + row * self._row_pitch(metrics)
                self._grid.put(widget, left + col * metrics.step, top)
                self._item_tops[index] = top
                self._widgets.append(widget)
            y += (
                heading_height
                + heading_gap
                + rows * metrics.height
                + max(0, rows - 1) * metrics.gap
                + group_gap
            )

        lengths = self._row_lengths()
        self._focus.set_row_lengths(lengths)
        if focused_index in self._index_positions:
            self._focus.jump_to(*self._index_positions[focused_index])
        self._grid_content_height = max(0.0, y - group_gap + metrics.bleed)
        self._grid.set_size_request(
            max(1, round(left + self._columns * metrics.step + metrics.bleed)),
            max(1, round(self._grid_content_height)),
        )
        self._update_legend()
        if not self._tiles:
            self._set_hint("No applications were found on this machine.")
        self._rebuild_rail()
        self._update_selection(animate=False)

    def _tile_widget(self, index: int, metrics: TileMetrics) -> TileWidget:
        tile = self._tiles[index]
        artwork = self._artwork.resolve(tile, icon_size=round(self._scale.du(54.0)))
        widget = TileWidget(
            tile, artwork, metrics, self._scale, show_subtitle=False, horizontal_content=True
        )
        click = Gtk.GestureClick()
        click.connect("released", lambda *_, i=index: self._click(i))
        widget.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_, i=index: self._hover(i))
        widget.add_controller(motion)
        return widget

    def _group_heading(self, letter: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.add_css_class("salon-app-group-heading")
        box.set_spacing(self._scale.px(16.0))
        label = Gtk.Label(label=letter)
        label.set_valign(Gtk.Align.CENTER)
        box.append(label)
        rule = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        rule.set_hexpand(True)
        rule.set_valign(Gtk.Align.CENTER)
        box.append(rule)
        return box

    def _row_pitch(self, metrics: TileMetrics) -> float:
        # Enough vertical room for the label under each card plus the gap.
        return metrics.height + metrics.gap

    def _focused_index(self) -> int:
        row, col = self._focus.position
        if 0 <= row < len(self._grid_rows) and 0 <= col < len(self._grid_rows[row]):
            return self._grid_rows[row][col]
        return -1

    def _update_selection(self, *, animate: bool = True) -> None:
        index = self._focused_index()
        for i, widget in enumerate(self._widgets):
            widget.set_focused(not self._top_bar_focused and i == index)
        tile = self.focused_tile
        if tile is not None:
            self._bottom.set_selection(tile.title)
        self._update_rail()
        self._update_legend()
        if 0 <= index < len(self._widgets):
            # Same aria-activedescendant pattern as the home screen: the
            # tiles never take GTK focus, so the container has to say which
            # of them the cursor is on.
            self._viewport.update_relation(
                [Gtk.AccessibleRelation.ACTIVE_DESCENDANT], [self._widgets[index]]
            )
        self._scroll_to_focused(animate=animate)

    def _update_legend(self) -> None:
        return

    def _scroll_to_focused(self, *, animate: bool) -> None:
        if not self._widgets or self._viewport_height <= 0:
            return
        metrics = self._metrics()
        pitch = self._row_pitch(metrics)
        index = self._focused_index()
        if not 0 <= index < len(self._item_tops):
            return
        top = self._item_tops[index]
        content_height = self._grid_content_height
        offset = 0.0
        if top + pitch + metrics.bleed > self._viewport_height:
            offset = self._viewport_height - (top + pitch + metrics.bleed)
        # Never past the end: a grid scrolled into empty space below the
        # last row reads as a rendering fault, and unlike the home screen
        # there is no anchor line here for the focused row to sit on.
        offset = max(min(0.0, self._viewport_height - content_height), min(0.0, offset))
        self._scroll.animate_to(offset) if animate else self._scroll.jump_to(offset)

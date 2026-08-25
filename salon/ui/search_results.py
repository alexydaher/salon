# SPDX-License-Identifier: GPL-3.0-or-later
"""Search ranking, result layout, and result selection."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core import ranking  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.services import appinfo  # noqa: E402
from salon.ui.search_models import Pane  # noqa: E402
from salon.ui.tile import TileWidget, metrics_for  # noqa: E402

RESULT_COLUMNS = 3
_MAX_RESULTS = 60


class SearchResultsController:
    def _on_installed_scanned(self, tiles: list[Tile]) -> None:
        self._installed_tiles = tiles
        if self.get_visible():
            self._refresh_results()

    def _refresh_results(self) -> None:
        query = self._keyboard.text
        self._query_label.set_label(query or "Search")

        if not query.strip():
            # An empty query shows the catalogue rather than nothing: the
            # user opened search to go somewhere, and a blank screen makes
            # them type before it will admit anything exists.
            self._results = self._catalog_tiles[:_MAX_RESULTS]
        else:
            by_id = {tile.id: tile for tile in (*self._catalog_tiles, *self._installed_tiles)}
            # Catalogue entries first so ranking's stable sort gives them
            # priority over installed apps at equal score (§6.6).
            pairs = appinfo.search_pairs(self._catalog_tiles) + appinfo.search_pairs(
                self._installed_tiles
            )
            # The same call the phone's `/search` makes, deliberately: two
            # search surfaces that ordered or deduplicated results
            # differently would be two things to learn.
            self._results = [
                by_id[tile_id] for tile_id in ranking.rank_best(query, pairs, _MAX_RESULTS)
            ]

        self._update_hint()
        self._rebuild_result_widgets()

    def _update_hint(self) -> None:
        pairing_hint = self._keyboard.pairing_hint()
        if pairing_hint:
            self._hint_label.set_label(pairing_hint)
            return
        if self._results:
            self._hint_label.set_label("")
            return
        if self._keyboard.text.strip():
            # §6.11: say what happened and what to do about it.
            self._hint_label.set_label("Nothing matched. Try fewer letters.")
        else:
            self._hint_label.set_label("Type to search your tiles and installed apps.")

    def _row_lengths(self) -> list[int]:
        rows, remainder = divmod(len(self._results), RESULT_COLUMNS)
        lengths = [RESULT_COLUMNS] * rows
        if remainder:
            lengths.append(remainder)
        return lengths

    def _rebuild_result_widgets(self) -> None:
        child = self._results_content.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._results_content.remove(child)
            child = next_child

        metrics = metrics_for(self._scale)
        self._result_widgets = []
        for index, tile in enumerate(self._results):
            row, col = divmod(index, RESULT_COLUMNS)
            artwork = self._artwork.resolve(tile, icon_size=round(metrics.height * 0.5))
            widget = TileWidget(tile, artwork, metrics, self._scale)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_, i=index: self._click_result(i))
            widget.add_controller(click)
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", lambda *_, i=index: self._hover_result(i))
            widget.add_controller(motion)
            # Vertically the first row sits a full bleed down, so its bloom
            # is inside the clip rather than sheared off along the top edge.
            # Horizontally it stays at -bleed on purpose: the left edge of
            # this viewport is the boundary with the keyboard pane, the
            # three columns already fill the pane's width, and glow spilling
            # over the keys would be worse than glow that stops at them.
            self._results_content.put(
                widget,
                col * metrics.step - metrics.bleed,
                metrics.bleed + row * (metrics.height + metrics.gap) - metrics.bleed,
            )
            self._result_widgets.append(widget)

        self._results_focus.set_row_lengths(self._row_lengths())
        self._results_content.set_size_request(
            max(1, round(RESULT_COLUMNS * metrics.step)),
            max(
                1,
                round(
                    metrics.bleed
                    + len(self._row_lengths()) * (metrics.height + metrics.gap)
                    + metrics.bleed
                ),
            ),
        )
        if self._pane is Pane.RESULTS and not self._results:
            self._pane = Pane.KEYBOARD
        self._update_selection(animate=False)

    def _update_selection(self, *, animate: bool = True) -> None:
        index = self._focused_index()
        for i, widget in enumerate(self._result_widgets):
            widget.set_focused(self._pane is Pane.RESULTS and i == index)
        if self._pane is Pane.RESULTS and 0 <= index < len(self._result_widgets):
            self._results_viewport.update_relation(
                [Gtk.AccessibleRelation.ACTIVE_DESCENDANT], [self._result_widgets[index]]
            )
        self._keyboard.refresh()
        if self._pane is Pane.KEYBOARD:
            self.add_css_class("keyboard-pane")
        else:
            self.remove_css_class("keyboard-pane")
        self._scroll_to_focused(animate=animate)

    def _focused_index(self) -> int:
        return self._results_focus.row * RESULT_COLUMNS + self._results_focus.col

    def _on_results_resized(self, width: int, height: int) -> None:
        self._results_height = height
        self._scroll_to_focused(animate=False)

    def _scroll_to_focused(self, *, animate: bool) -> None:
        if self._pane is not Pane.RESULTS or not self._result_widgets:
            return
        metrics = metrics_for(self._scale)
        row_height = metrics.height + metrics.gap
        # Card positions, not widget positions: the content carries a bleed
        # of padding at the top and bottom so the first and last rows' bloom
        # is inside the clip.
        card_top = metrics.bleed + self._results_focus.row * row_height
        viewport_height = self._results_height or self._results_viewport.get_height()
        if viewport_height <= 0:
            return
        content_height = 2 * metrics.bleed + len(self._row_lengths()) * row_height
        # Keep the focused row fully visible, and never scroll past either
        # end of the grid.
        lowest = min(0.0, viewport_height - content_height)
        desired = 0.0
        if card_top + metrics.height + metrics.bleed > viewport_height:
            desired = metrics.bleed - card_top
        target = max(lowest, min(0.0, desired))
        self._results_scroll.animate_to(target) if animate else self._results_scroll.jump_to(target)

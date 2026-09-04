# SPDX-License-Identifier: GPL-3.0-or-later
"""Search ranking, result layout, and result selection."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core import ranking  # noqa: E402
from salon.core.focus import Bump  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services import appinfo  # noqa: E402
from salon.ui.search_hints import _KEYBOARD_HINTS, _RESULT_HINTS  # noqa: E402
from salon.ui.search_models import Pane, result_columns  # noqa: E402
from salon.ui.tile import TileWidget, metrics_for  # noqa: E402

_MAX_RESULTS = 60
# How far a card slides and settles when the cursor pushes past an end.
_BUMP_DISTANCE_DU = 26.0


class SearchResultsController:
    def current_text(self) -> str:
        """What is in the query box, for the phone to mirror: two keyboards
        pointed at one box have to agree about what is in it."""
        return self._keyboard.text

    def _on_installed_scanned(self, tiles: list[Tile]) -> None:
        self._installed_tiles = tiles
        self._installed_loading = False
        if self.get_visible():
            self._refresh_results()

    def _refresh_results(self) -> None:
        query = self._keyboard.text
        self._query_label.set_label(query or "Search")
        if not query.strip():
            # An empty query shows the catalogue rather than nothing: a
            # blank screen makes you type before it admits anything exists.
            self._results = self._catalog_tiles[:_MAX_RESULTS]
        else:
            by_id = {tile.id: tile for tile in (*self._catalog_tiles, *self._installed_tiles)}
            # Catalogue entries first so ranking's stable sort gives them
            # priority over installed apps at equal score (§6.6).
            pairs = appinfo.search_pairs(self._catalog_tiles) + appinfo.search_pairs(
                self._installed_tiles
            )
            # The same call the phone's `/search` makes: two search surfaces
            # that ranked differently would be two things to learn.
            self._results = [
                by_id[tile_id] for tile_id in ranking.rank_best(query, pairs, _MAX_RESULTS)
            ]

        self._update_hint()
        self._rebuild_result_widgets()

    def _update_hint(self) -> None:
        pairing_hint = self._keyboard.pairing_hint()
        status: list[str] = []
        if pairing_hint:
            status.append(pairing_hint)
        if self._installed_loading:
            status.append("Checking installed apps…")
        if self._results:
            count = len(self._results)
            status.append(f"{count} result{'s' if count != 1 else ''}")
            self._hint_label.set_label(" · ".join(status))
            return
        if self._keyboard.text.strip():
            # §6.11: say what happened and what to do about it.
            status.append("Nothing matched. Try fewer letters.")
        else:
            status.append("Type to search your tiles and installed apps.")
        self._hint_label.set_label(" · ".join(status))

    def _row_lengths(self) -> list[int]:
        columns = self._result_columns
        rows, remainder = divmod(len(self._results), columns)
        lengths = [columns] * rows
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
            row, col = divmod(index, self._result_columns)
            artwork = self._artwork.resolve(tile, icon_size=round(metrics.height * 0.5))
            widget = TileWidget(tile, artwork, metrics, self._scale)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_, i=index: self._click_result(i))
            widget.add_controller(click)
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", lambda *_, i=index: self._hover_result(i))
            widget.add_controller(motion)
            # Vertically a full bleed down, so the first row's focused scale
            # is inside the clip. Horizontally at -bleed on purpose: this
            # viewport's left edge borders the keyboard, so the tile itself
            # remains aligned with the results pane.
            self._results_content.put(
                widget,
                col * metrics.step - metrics.bleed,
                metrics.bleed + row * (metrics.height + metrics.gap) - metrics.bleed,
            )
            self._result_widgets.append(widget)

        self._results_focus.set_row_lengths(self._row_lengths())
        self._results_content.set_size_request(
            max(1, round(self._result_columns * metrics.step - metrics.gap + 2 * metrics.bleed)),
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

    def _click_result(self, index: int) -> None:
        if not (0 <= index < len(self._results)):
            return
        self._pane = Pane.RESULTS
        self._results_focus.jump_to(*divmod(index, self._result_columns))
        self._update_selection()
        self._launch_focused()

    def _hover_result(self, index: int) -> None:
        if not self._pointer_active or not (0 <= index < len(self._results)):
            return
        position = divmod(index, self._result_columns)
        if self._pane is Pane.RESULTS and self._results_focus.position == position:
            return
        self._pane = Pane.RESULTS
        self._results_focus.jump_to(*position)
        self._update_selection()

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
        self._refresh_bottom_bar(index)
        self._scroll_to_focused(animate=animate)

    def _refresh_bottom_bar(self, index: int) -> None:
        """What the buttons do here, and what the cursor rests on. Keyed on
        the pane: OK types a letter on one side and opens an app on the
        other."""
        on_results = self._pane is Pane.RESULTS
        self._bottom.set_hints(_RESULT_HINTS if on_results else _KEYBOARD_HINTS)
        tile = self._results[index] if on_results and 0 <= index < len(self._results) else None
        if tile is None:
            self._bottom.set_selection("")
            return
        self._bottom.set_selection(tile.title, tile.subtitle or "")

    def _focused_index(self) -> int:
        return self._results_focus.row * self._result_columns + self._results_focus.col

    def _on_results_resized(self, width: int, height: int) -> None:
        self._results_height = height
        self._results_width = width
        if self._sync_result_columns():
            self._rebuild_result_widgets()  # the shape changed, so every position did
            return
        self._scroll_to_focused(animate=False)

    def _sync_result_columns(self) -> bool:
        """Adopt the column count the measured pane can hold; report whether
        it changed. The design count is a ceiling, not a promise."""
        metrics = metrics_for(self._scale)
        columns = result_columns(self._results_width, metrics.step, metrics.gap)
        if columns == self._result_columns:
            return False
        self._result_columns = columns
        return True

    def _scroll_to_focused(self, *, animate: bool) -> None:
        if self._pane is not Pane.RESULTS or not self._result_widgets:
            return
        metrics = metrics_for(self._scale)
        row_height = metrics.height + metrics.gap
        # Card positions, not widget positions: the content carries bleed
        # padding at the top and bottom so the first and last rows' focused
        # scale stays inside the clip.
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

    # --- crossing between the two panes ----------------------------------
    # Here rather than in `search.py`: both halves are about the grid —
    # whether there are results to cross *to*, and what it does at an end.

    def _handle_keyboard_direction(self, action: Action) -> None:
        if self._keyboard.move(action):
            self._update_selection()
            return
        if action is Action.RIGHT and self._results:
            self._pane = Pane.RESULTS
            self._update_selection()

    def _handle_results_direction(self, action: Action) -> None:
        change = self._results_focus.handle(action)
        if change.moved:
            self._update_selection()
            return
        if change.bump is Bump.LEFT:
            self._pane = Pane.KEYBOARD
            self._update_selection()
            return
        if change.bump is not Bump.NONE:
            distance = self._scale.du(_BUMP_DISTANCE_DU)
            if change.bump is Bump.UP:
                self._results_scroll.bump(distance)
            elif change.bump is Bump.DOWN:
                self._results_scroll.bump(-distance)

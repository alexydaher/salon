# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-screen search (§6.6).

Searches the tile catalogue and every installed application at once, ranked
catalogue-first, filtered live on each keystroke. Results are ordinary
`TileWidget`s, so an app found by search gets the same artwork, the same
focus treatment and the same launch path as one the user put on the home
screen — it is not a different kind of thing.

The screen is two panes side by side: the keyboard on the left, results on
the right. RIGHT off the keyboard's last column crosses into the results,
LEFT off the results' first column crosses back. That's the whole
interaction model, and it's the reason the keyboard's own edge behaviour
(`KeyboardModel.move` returning False) is a return value rather than a
silent clamp.

Text can also arrive from a phone on the LAN (§6.12); the pairing server
runs only while this overlay is open and is torn down when it closes.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.core import ranking, tokens  # noqa: E402
from salon.core.focus import Bump, FocusModel  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services import appinfo  # noqa: E402
from salon.services.artwork import ArtworkResolver  # noqa: E402
from salon.services.pairing import PairingServer  # noqa: E402
from salon.ui.keyboardpane import KeyboardPane  # noqa: E402
from salon.ui.motion import AxisSpring, SizeReporter  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.tile import TileWidget, metrics_for  # noqa: E402

RESULT_COLUMNS = 3
_MAX_RESULTS = 60
_BUMP_DISTANCE_DU = 26.0

# Smaller than the home screen's key cell so the keyboard leaves room for
# three columns of results beside it on a 1080p screen.
_KEY_CELL_DU = 64.0


class Pane(Enum):
    KEYBOARD = auto()
    RESULTS = auto()


class SearchOverlay(Gtk.Box):
    def __init__(
        self,
        scale: Scale,
        artwork: ArtworkResolver,
        pairing: PairingServer,
        *,
        on_launch: Callable[[Tile], None],
        on_close: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-search")
        self.set_visible(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._scale = scale
        self._artwork = artwork
        self._on_launch = on_launch
        self._on_close = on_close

        self._catalog_tiles: list[Tile] = []
        self._installed_tiles: list[Tile] = []
        self._results: list[Tile] = []
        self._results_height = 0
        self._result_widgets: list[TileWidget] = []
        self._pane = Pane.KEYBOARD
        self._pointer_active = False

        self._results_focus = FocusModel([])

        # The scrim covers the whole screen; the *content* is inset to the
        # safe area. Insetting the root instead left the home screen and the
        # clock showing through the margins behind it.
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.append(self._content)

        self._query_label = Gtk.Label(label="")
        self._query_label.add_css_class("salon-search-query")
        self._query_label.set_halign(Gtk.Align.START)
        self._query_label.set_ellipsize(Pango.EllipsizeMode.START)
        self._content.append(self._query_label)

        self._hint_label = Gtk.Label()
        self._hint_label.add_css_class("salon-search-hint")
        self._hint_label.set_halign(Gtk.Align.START)
        self._hint_label.set_wrap(True)
        self._content.append(self._hint_label)

        self._body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._body.set_vexpand(True)
        self._content.append(self._body)

        self._keyboard = KeyboardPane(
            scale,
            pairing,
            on_key_pressed=self._press_key,
            on_text_changed=self._refresh_results,
            cell_du=_KEY_CELL_DU,
        )
        self._body.append(self._keyboard)

        self._results_viewport = Gtk.Fixed()
        self._results_viewport.set_overflow(Gtk.Overflow.HIDDEN)
        self._results_viewport.set_accessible_role(Gtk.AccessibleRole.GRID)
        self._results_viewport.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Search results"]
        )
        # Wrapped, and reporting a zero minimum: a Gtk.Fixed measures to fit
        # its children, so a long result list would ask to be taller than
        # the window, be allocated it, and then scroll nowhere because every
        # row would test as already on screen. Same defect the apps grid
        # had; same fix.
        self._results_host = SizeReporter(
            self._results_viewport, self._on_results_resized, propagate_minimum=False
        )
        self._results_host.set_hexpand(True)
        self._results_host.set_vexpand(True)
        self._body.append(self._results_host)

        self._results_content = Gtk.Fixed()
        self._results_viewport.put(self._results_content, 0, 0)
        self._results_scroll = AxisSpring(
            self._results_viewport, self._results_content, vertical=True
        )

        self._apply_scale(scale)

    # --- lifecycle -------------------------------------------------------

    def open(self, catalog_tiles: list[Tile]) -> None:
        self._catalog_tiles = catalog_tiles
        self._keyboard.reset()
        self._results_focus = FocusModel([])
        self._pane = Pane.KEYBOARD
        self.set_visible(True)
        self._refresh_results()
        # Scanning every .desktop file on the system is far too slow for the
        # frame clock, so results start as catalogue-only and widen when the
        # scan lands (§10: no blocking I/O on the main loop).
        appinfo.list_installed_async(self._on_installed_scanned)

    def close(self) -> None:
        self.set_visible(False)
        self._on_close()

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._keyboard.set_scale(scale)
        self._apply_scale(scale)
        self._rebuild_result_widgets()

    def _apply_scale(self, scale: Scale) -> None:
        margin = scale.px(
            tokens.REFERENCE_VIEWPORT_HEIGHT_PX * tokens.SAFE_AREA_DEFAULT_PERCENT / 100.0
        )
        self._content.set_margin_start(margin)
        self._content.set_margin_end(margin)
        self._content.set_margin_top(margin)
        self._content.set_margin_bottom(margin)
        self._content.set_spacing(scale.px(8.0))
        self._body.set_spacing(scale.px(48.0))
        self._body.set_margin_top(scale.px(24.0))

    def set_pointer_active(self, active: bool) -> None:
        self._pointer_active = active
        self._keyboard.set_hover_enabled(active)

    # --- results ---------------------------------------------------------

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
            ordered = ranking.rank(query, pairs)
            seen: set[str] = set()
            results: list[Tile] = []
            for tile_id in ordered:
                if tile_id in seen:
                    continue
                seen.add(tile_id)
                results.append(by_id[tile_id])
                if len(results) >= _MAX_RESULTS:
                    break
            self._results = results

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
            self._hint_label.set_label(
                "Nothing matched. Try fewer letters."
            )
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
        self._results_scroll.animate_to(target) if animate else self._results_scroll.jump_to(
            target
        )

    # --- input -----------------------------------------------------------

    def handle_action(self, action: Action) -> None:
        if action is Action.BACK:
            self.close()
            return
        if action is Action.OK:
            if self._pane is Pane.KEYBOARD:
                self._press_key()
            else:
                self._launch_focused()
            return
        if self._pane is Pane.KEYBOARD:
            self._handle_keyboard_direction(action)
        else:
            self._handle_results_direction(action)

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

    def _press_key(self) -> None:
        result = self._keyboard.press()
        if result.done:
            if self._results:
                self._pane = Pane.RESULTS
                self._update_selection()
            return
        if result.changed:
            self._results_focus = FocusModel([])
            self._refresh_results()
        else:
            self._update_selection()

    def _launch_focused(self) -> None:
        index = self._focused_index()
        if 0 <= index < len(self._results):
            tile = self._results[index]
            self.close()
            self._on_launch(tile)

    def _click_result(self, index: int) -> None:
        if not (0 <= index < len(self._results)):
            return
        self._pane = Pane.RESULTS
        self._results_focus.jump_to(*divmod(index, RESULT_COLUMNS))
        self._update_selection()
        self._launch_focused()

    def _hover_result(self, index: int) -> None:
        if not self._pointer_active or not (0 <= index < len(self._results)):
            return
        position = divmod(index, RESULT_COLUMNS)
        if self._pane is Pane.RESULTS and self._results_focus.position == position:
            return
        self._pane = Pane.RESULTS
        self._results_focus.jump_to(*position)
        self._update_selection()


# SPDX-License-Identifier: GPL-3.0-or-later
"""The all-apps grid: every installed application, A–Z, on one screen.

Search already finds anything by name, but searching is what you do when you
know what you want. Browsing is what you do when you don't, and a launcher
with no way to see what's on the machine makes the answer to "what can this
thing do" a typing exercise. Every ten-foot platform has this screen. The
`show-apps-row` setting still exists and still works, but a hundred and
fifty desktop entries in a single horizontal row is the one shape that
information cannot be scanned in; a grid is.

The grid is a `Gtk.Fixed` of `TileWidget`s inside a clipping viewport
translated by a spring — the same mechanism the home rows and the search
results use, for the same reason (the selection drives the scroll here, not
the reverse). Columns are computed from the real viewport width rather than
fixed, so the same code fills a 1080p panel and a 4K one.

Two things about the geometry are load-bearing, and both were wrong here
first:

* **The viewport reports a zero minimum height** (`SizeReporter`'s
  `propagate_minimum=False`). A `Gtk.Fixed` measures to fit its children,
  so the viewport asked to be as tall as all eight rows of applications —
  and, being an overlay child, got it. Everything below the first screenful
  was allocated off the bottom of the window, and `_scroll_to_focused`
  compared the focused row against a "viewport height" of 2012px on a
  1080px screen, concluded nothing was ever off-screen, and never scrolled.
  DOWN moved the selection into rows nobody could see.
* **The cards are inset by one `bleed` from the viewport's edges.** A tile's
  widget is `bleed` larger than its card on every side, and that padding is
  where the focus bloom and the 1.09 scale-up are drawn. Placing the first
  row and column at `-bleed` put the card flush with the viewport corner and
  its glow *outside* it, where the clip cut it off — the top and left of
  every edge tile's hover lighting, square. The viewport spans the full
  window width for the same reason the home rows do, so the only horizontal
  clip is the screen edge.

The tiles are ordinary `TileWidget`s built from `services/appinfo`'s `Tile`s,
so an app opened from here takes exactly the same launch path as one the user
put on the home screen, and OPTIONS over it offers the same pin/add actions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.focus import Bump, FocusModel  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services import appinfo  # noqa: E402
from salon.services.artwork import ArtworkResolver  # noqa: E402
from salon.ui import motion  # noqa: E402
from salon.ui.motion import AxisSpring, SizeReporter  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.tile import TileMetrics, TileWidget, metrics_for  # noqa: E402

_BUMP_DISTANCE_DU = 26.0

# A square tile at full size: seven columns and four and a bit rows on a
# 1080p panel, so around thirty apps are visible at once. Denser than this
# was tried and rejected — at 0.78 the card is 172px wide and "Calculator"
# ellipsised to "Calcul…", which defeats the point of a browsable grid.
_TILE_SCALE = 1.0
_ASPECT = "square"


class AppsGrid(Gtk.Box, motion.FadesIn):
    """Reachable from the top bar's grid button. Owns nothing but its own
    view of the installed-app scan; the launch itself goes back out through
    the same `on_launch` the home screen and search use."""

    def __init__(
        self,
        scale: Scale,
        artwork: ArtworkResolver,
        *,
        on_launch: Callable[[Tile], None],
        on_close: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._init_fade()
        self.add_css_class("salon-search")  # the same full-bleed dark field
        self.set_visible(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._scale = scale
        self._artwork = artwork
        self._on_launch = on_launch
        self._on_close = on_close

        self._tiles: list[Tile] = []
        self._widgets: list[TileWidget] = []
        self._columns = 1
        self._focus = FocusModel([])
        self._pointer_active = False
        self._viewport_width = 0
        self._viewport_height = 0
        self._safe_margin = 0.0

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.append(self._content)

        self._title = Gtk.Label(label="All apps")
        self._title.add_css_class("salon-search-query")
        self._title.set_halign(Gtk.Align.START)
        self._content.append(self._title)

        # The full name and description of whatever the cursor is on.
        # The cards themselves cannot carry this: at seven columns a card is
        # 240px wide and "Advanced Network Configuration" ellipsises to
        # "Advanced…", which put two different apps on screen both reading
        # "Documen…". One full-width line under the heading says what the
        # card cannot.
        self._hint = Gtk.Label()
        self._hint.add_css_class("salon-search-hint")
        self._hint.set_halign(Gtk.Align.START)
        self._hint.set_ellipsize(Pango.EllipsizeMode.END)
        self._content.append(self._hint)

        # The A–Z rail. Two hundred applications at seven columns is
        # twenty-nine rows of D-pad; the shoulder buttons cross a letter at
        # a time, and this is what says where that lands. Horizontal rather
        # than a column down the side, because a side rail would narrow the
        # viewport and the viewport has to reach the screen edge for the
        # edge tiles' bloom to have somewhere to go.
        self._rail = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._rail.add_css_class("salon-letter-rail")
        self._rail.set_halign(Gtk.Align.START)
        self._rail_labels: dict[str, Gtk.Label] = {}
        self._content.append(self._rail)

        self._viewport = Gtk.Fixed()
        self._viewport.set_overflow(Gtk.Overflow.HIDDEN)
        self._viewport.set_accessible_role(Gtk.AccessibleRole.GRID)
        self._viewport.update_property(
            [Gtk.AccessibleProperty.LABEL], ["All applications, A to Z"]
        )
        self._grid = Gtk.Fixed()
        self._viewport.put(self._grid, 0, 0)
        self._scroll = AxisSpring(self._viewport, self._grid, vertical=True)

        self._viewport_host = SizeReporter(
            self._viewport, self._on_resized, propagate_minimum=False
        )
        self._viewport_host.set_hexpand(True)
        self._viewport_host.set_vexpand(True)
        self._content.append(self._viewport_host)

        # Where Settings puts its legend, for the same reason: what the
        # buttons do belongs at the bottom edge, out of the way of the
        # thing the eye is actually scanning.
        self._legend = Gtk.Label()
        self._legend.add_css_class("salon-settings-legend")
        self._legend.set_halign(Gtk.Align.START)
        self._legend.set_ellipsize(Pango.EllipsizeMode.END)
        self._content.append(self._legend)

        self.set_scale(scale)

    # --- lifecycle -------------------------------------------------------

    def open(self) -> None:
        self.set_visible(True)
        self._begin_fade()
        # Always from the top. The cursor is stored as (row, column) and
        # the column count depends on the viewport, so a position kept
        # across a close and reopen can be reinterpreted against a
        # different width and land on a different app than it left.
        self._focus.jump_to(0, 0)
        self._set_hint("Loading the application list…")
        # Scanning every .desktop file on the system is far too slow for the
        # frame clock (§10), so the grid opens empty and fills a moment
        # later rather than freezing on the way in.
        appinfo.list_installed_async(self._on_scanned)

    def close(self) -> None:
        self.set_visible(False)
        self._on_close()

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        margin = scale.px(
            tokens.REFERENCE_VIEWPORT_HEIGHT_PX * tokens.SAFE_AREA_DEFAULT_PERCENT / 100.0
        )
        # The safe area is applied to the text, not to the whole column:
        # the viewport underneath has to reach the screen edges so an edge
        # tile's bloom has somewhere to go. The cards inside it are inset
        # back to the same margin — see _origin.
        self._safe_margin = float(margin)
        self._title.set_margin_start(margin)
        self._title.set_margin_end(margin)
        self._hint.set_margin_start(margin)
        self._hint.set_margin_end(margin)
        self._legend.set_margin_start(margin)
        self._legend.set_margin_end(margin)
        self._rail.set_margin_start(margin)
        self._rail.set_margin_end(margin)
        self._rail.set_spacing(scale.px(4.0))
        self._content.set_margin_top(margin)
        self._content.set_margin_bottom(margin)
        self._content.set_spacing(scale.px(8.0))
        self._rebuild()

    def set_pointer_active(self, active: bool) -> None:
        self._pointer_active = active

    @property
    def focused_tile(self) -> Tile | None:
        index = self._focused_index()
        if 0 <= index < len(self._tiles):
            return self._tiles[index]
        return None

    # --- data ------------------------------------------------------------

    def _on_scanned(self, tiles: list[Tile]) -> None:
        # Already sorted case-insensitively by appinfo, which is the order
        # this screen wants: an A–Z grid is scannable, a ranked one is not.
        self._tiles = tiles
        self._rebuild()

    def _set_hint(self, text: str) -> None:
        self._hint.set_label(text)

    # --- layout ----------------------------------------------------------

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

    # --- input -----------------------------------------------------------

    def handle_action(self, action: Action) -> None:
        if action is Action.BACK:
            self.close()
            return
        if action is Action.OK:
            tile = self.focused_tile
            if tile is not None:
                self._on_launch(tile)
            return
        if action in (Action.PREV_GROUP, Action.NEXT_GROUP):
            self._jump_letter(-1 if action is Action.PREV_GROUP else 1)
            return
        change = self._focus.handle(action)
        if change.moved:
            self._update_selection()
        elif change.bump is not Bump.NONE:
            distance = self._scale.du(_BUMP_DISTANCE_DU)
            if change.bump is Bump.UP:
                self._scroll.bump(distance)
            elif change.bump is Bump.DOWN:
                self._scroll.bump(-distance)

    def _click(self, index: int) -> None:
        self._jump_to_index(index)
        tile = self.focused_tile
        if tile is not None:
            self._on_launch(tile)

    def _hover(self, index: int) -> None:
        if self._pointer_active:
            self._jump_to_index(index)

    def _jump_to_index(self, index: int) -> None:
        row, col = divmod(index, self._columns)
        self._focus.jump_to(row, col)
        self._update_selection()

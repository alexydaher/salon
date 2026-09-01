# SPDX-License-Identifier: GPL-3.0-or-later
"""All-applications overlay and its input lifecycle."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.focus import Bump, FocusModel  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services import appinfo  # noqa: E402
from salon.services.artwork import ArtworkResolver  # noqa: E402
from salon.ui import motion  # noqa: E402
from salon.ui.actionbar import SelectionActionBar  # noqa: E402
from salon.ui.appsgrid_geometry import linear_neighbor  # noqa: E402
from salon.ui.appsgrid_layout import AppsGridLayout  # noqa: E402
from salon.ui.motion import AxisSpring, SizeReporter  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.tile import TileWidget  # noqa: E402

_BUMP_DISTANCE_DU = 26.0

class AppsGrid(Gtk.Overlay, motion.FadesIn, AppsGridLayout):
    def __init__(
        self,
        scale: Scale,
        artwork: ArtworkResolver,
        *,
        tile_scale: float,
        on_launch: Callable[[Tile], None],
        on_close: Callable[[], None],
        on_focus_top_bar: Callable[[], None],
        on_count: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._init_fade()
        self.add_css_class("salon-search")
        self.add_css_class("salon-apps-grid")
        self.set_visible(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._scale = scale
        self._tile_scale = tile_scale
        self._artwork = artwork
        self._on_launch = on_launch
        self._on_close = on_close
        self._on_focus_top_bar = on_focus_top_bar
        self._on_count = on_count

        self._tiles: list[Tile] = []
        self._widgets: list[TileWidget] = []
        self._columns = 1
        self._grid_rows: list[list[int]] = []
        self._index_positions: dict[int, tuple[int, int]] = {}
        self._focus = FocusModel([])
        self._pointer_active = False
        self._top_bar_focused = False
        self._viewport_width = 0
        self._viewport_height = 0
        self._safe_margin = 0.0

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self._content)

        self._header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._content.append(self._header)
        self._title = Gtk.Label(label="All applications")
        self._title.add_css_class("salon-search-query")
        self._title.set_halign(Gtk.Align.START)
        self._header.append(self._title)
        self._count = Gtk.Label(label="")
        self._count.add_css_class("salon-search-hint")
        self._count.set_halign(Gtk.Align.START)
        self._header.append(self._count)

        # The rail floats beside the viewport, whose end margin reserves the
        # same strip, so tiles and shortcuts cannot sit underneath it.
        self._rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._rail.add_css_class("salon-letter-rail")
        self._rail.add_css_class("salon-letter-rail-vertical")
        self._rail.set_halign(Gtk.Align.END)
        self._rail.set_valign(Gtk.Align.FILL)
        self._rail_labels: dict[str, Gtk.Label] = {}

        self._viewport = Gtk.Fixed()
        self._viewport.set_overflow(Gtk.Overflow.HIDDEN)
        self._viewport.set_accessible_role(Gtk.AccessibleRole.GRID)
        self._viewport.update_property([Gtk.AccessibleProperty.LABEL], ["All applications, A to Z"])
        self._grid = Gtk.Fixed()
        self._viewport.put(self._grid, 0, 0)
        self._scroll = AxisSpring(self._viewport, self._grid, vertical=True)

        self._viewport_host = SizeReporter(
            self._viewport, self._on_resized, propagate_minimum=False
        )
        self._viewport_host.set_hexpand(True)
        self._viewport_host.set_vexpand(True)
        self._body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._body.set_vexpand(True)
        self._body.append(self._viewport_host)
        self._content.append(self._body)

        self._bottom = SelectionActionBar(
            scale,
            (
                (Action.OK, "Open"),
                (Action.OPTIONS, "More"),
                ("D-PAD", "Browse"),
                (Action.BACK, "Home"),
            ),
        )
        self._content.append(self._bottom)
        self.add_overlay(self._rail)

        self.set_scale(scale)

    # --- lifecycle -------------------------------------------------------

    def open(self) -> None:
        self.set_visible(True)
        self._begin_fade()
        self._focus.jump_to(0, 0)
        self._set_hint("Loading the application list…")
        appinfo.list_installed_async(self._on_scanned)

    def close(self) -> None:
        self.set_visible(False)
        self._on_close()

    def set_input_device(self, source: str, family: str) -> None:
        self._bottom.set_input_device(source, family)

    def set_scale(self, scale: Scale, *, tile_scale: float | None = None) -> None:
        self._scale = scale
        if tile_scale is not None:
            self._tile_scale = tile_scale
        margin = scale.safe_margin_px
        self._safe_margin = float(margin)
        self._content.set_margin_start(scale.px(tokens.CONSOLE_WIDTH_DU))
        self._header.set_margin_start(margin)
        self._header.set_margin_end(margin)
        self._header.set_margin_top(max(0, margin - scale.px(18.0)))
        self._header.set_spacing(scale.px(18.0))
        self._rail.set_margin_start(0)
        self._rail.set_margin_end(margin)
        self._rail.set_margin_top(scale.px(104.0))
        self._rail.set_margin_bottom(scale.px(112.0))
        self._rail.set_spacing(0)
        self._rail.set_size_request(scale.px(52.0), -1)
        self._body.set_margin_end(scale.px(104.0))
        self._viewport_host.set_margin_top(scale.px(26.0))
        self._bottom.set_scale(scale)
        self._content.set_margin_top(0)
        self._content.set_margin_bottom(0)
        self._content.set_spacing(scale.px(12.0))
        self._relayout()

    def set_pointer_active(self, active: bool) -> None:
        self._pointer_active = active

    def set_top_bar_focused(self, focused: bool) -> None:
        """Give the shared shortcut bar the only strong focus highlight."""
        if self._top_bar_focused == focused:
            return
        self._top_bar_focused = focused
        self._update_selection(animate=False)

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
        self._count.set_label(f"{len(tiles)} installed")
        if self._on_count is not None:
            self._on_count(len(tiles))
        self._rebuild()

    def _set_hint(self, text: str) -> None:
        self._bottom.set_selection(text)

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
        if action in (Action.LEFT, Action.RIGHT):
            step = -1 if action is Action.LEFT else 1
            target = linear_neighbor(self._focused_index(), len(self._tiles), step)
            if target is not None:
                self._jump_to_index(target)
            else:
                distance = self._scale.du(_BUMP_DISTANCE_DU)
                self._scroll.bump(distance if step < 0 else -distance)
            return
        change = self._focus.handle(action)
        if change.moved:
            self._update_selection()
        elif change.bump is not Bump.NONE:
            if change.bump is Bump.UP:
                self._on_focus_top_bar()
                return
            distance = self._scale.du(_BUMP_DISTANCE_DU)
            if change.bump is Bump.DOWN:
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
        position = self._index_positions.get(index)
        if position is None:
            return
        row, col = position
        self._focus.jump_to(row, col)
        self._update_selection()

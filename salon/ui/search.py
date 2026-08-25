# SPDX-License-Identifier: GPL-3.0-or-later
"""Search overlay lifecycle, keyboard input, and launch actions."""

from __future__ import annotations

from collections.abc import Callable

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
from salon.services.pairing import PairingServer  # noqa: E402
from salon.ui import motion  # noqa: E402
from salon.ui.hardware_text import HardwareTextInput  # noqa: E402
from salon.ui.keyboardpane import KeyboardPane  # noqa: E402
from salon.ui.motion import AxisSpring, SizeReporter  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.search_models import Pane  # noqa: E402
from salon.ui.search_results import SearchResultsController  # noqa: E402
from salon.ui.tile import TileWidget  # noqa: E402

RESULT_COLUMNS = 3
_BUMP_DISTANCE_DU = 26.0

# Leaves room for three result columns beside the keyboard.
_KEY_CELL_DU = 64.0


class SearchOverlay(Gtk.Box, motion.FadesIn, SearchResultsController, HardwareTextInput):
    def __init__(
        self,
        scale: Scale,
        artwork: ArtworkResolver,
        pairing: PairingServer,
        *,
        on_launch: Callable[[Tile], None],
        on_options: Callable[[Tile], None],
        on_close: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._init_fade()
        self.add_css_class("salon-search")
        self.set_visible(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._scale = scale
        self._artwork = artwork
        self._on_launch = on_launch
        self._on_options = on_options
        self._on_close = on_close

        self._catalog_tiles: list[Tile] = []
        self._installed_tiles: list[Tile] = []
        self._results: list[Tile] = []
        self._results_height = 0
        self._result_widgets: list[TileWidget] = []
        self._pane = Pane.KEYBOARD
        self._pointer_active = False
        self._installed_loading = False

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
        self._results_viewport.update_property([Gtk.AccessibleProperty.LABEL], ["Search results"])
        # Wrapped, and reporting a zero minimum: a Gtk.Fixed measures to fit
        # its children, so a long result list would ask to be taller than
        # the window, be allocated it, and then scroll nowhere because every
        # row would test as already on screen. Same defect the apps grid
        # had; same fix.
        self._results_host = SizeReporter(
            self._results_viewport,
            self._on_results_resized,
            propagate_minimum=False,
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
        self._installed_loading = True
        self._begin_fade()
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
        if action is Action.OPTIONS:
            tile = self.focused_tile
            if self._pane is Pane.RESULTS and tile is not None:
                self._on_options(tile)
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

    @property
    def focused_tile(self) -> Tile | None:
        index = self._focused_index()
        return self._results[index] if 0 <= index < len(self._results) else None

    def _hardware_submit(self) -> None:
        if self._results:
            self._pane = Pane.RESULTS
            self._results_focus.jump_to(0, 0)
            self._launch_focused()

# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Focused full-screen overlay widget."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.services.artwork import glow_color  # noqa: E402
from salon.ui import motion, theme  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


@dataclass(frozen=True, slots=True)
class SystemMenuItem:
    label: str
    action: Callable[[], None]
    danger: bool = False


class SystemMenu(Gtk.Box, motion.FadesIn):
    """A D-pad-navigable *and* mouse-driven menu — every row is a real
    Gtk.Button, so clicks work for free, hover moves the selection so the
    pointer and the D-pad never disagree about what's highlighted, and a
    click on the scrim outside the card dismisses it.

    Used twice: as the reachable escape hatch for a fullscreen, keyboard-
    less kiosk (without it there is no way to suspend or shut down the
    machine, or to leave Salon at all), and as the per-tile options menu
    that OPTIONS opens. Both are the same object with different items, which
    is why the item list is settable rather than fixed at construction —
    a tile menu's contents depend on which tile is under the cursor.
    """

    def __init__(self, items: list[SystemMenuItem], scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._init_fade()
        self.add_css_class("salon-system-menu-scrim")
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_visible(False)

        self._card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._card.add_css_class("salon-system-menu-card")
        self._card.set_halign(Gtk.Align.CENTER)
        self._card.set_valign(Gtk.Align.CENTER)
        # A vertical box packs children from the top and hands each one
        # exactly its natural height, so valign alone leaves the card pinned
        # to the top edge; it only centres once the child is given the
        # spare space to centre within.
        self._card.set_vexpand(True)
        self.append(self._card)

        self._title = Gtk.Label()
        self._title.add_css_class("salon-system-menu-title")
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        self._title.set_visible(False)
        self._card.append(self._title)

        self._scale = scale
        self._items: list[SystemMenuItem] = []
        self._rows: list[Gtk.Button] = []
        self._selected = 0
        # Hover only moves the selection when the pointer is genuinely in
        # use. GTK delivers a motion event when a widget maps under a
        # stationary cursor, so without this the menu opens with whatever
        # item happens to be under the mouse selected rather than the first.
        self._hover_enabled = False
        self.set_items(items)

        dismiss = Gtk.GestureClick()
        dismiss.connect("released", self._on_scrim_clicked)
        self.add_controller(dismiss)

        self.set_scale(scale)

    def set_items(self, items: list[SystemMenuItem], *, title: str = "") -> None:
        for row in self._rows:
            self._card.remove(row)
        self._items = items
        self._rows = []
        self._selected = 0
        self._title.set_label(title)
        self._title.set_visible(bool(title))
        for index, item in enumerate(items):
            row = Gtk.Button(label=item.label)
            row.add_css_class("salon-system-menu-item")
            if item.danger:
                row.add_css_class("danger")
            row.connect("clicked", lambda _btn, i=index: self._activate(i))
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", lambda *_, i=index: self._on_hover(i))
            row.add_controller(motion)
            self._card.append(row)
            self._rows.append(row)
        self._update_selection()

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._card.set_spacing(scale.px(6.0))
        self._card.set_size_request(scale.px(560.0), -1)

    def _on_scrim_clicked(
        self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float
    ) -> None:
        # Only outside the card: the buttons handle their own clicks, but a
        # click on the card's padding shouldn't dismiss the menu.
        bounds = self._card.compute_bounds(self)
        if bounds[0] and bounds[1].contains_point(point_at(x, y)):
            return
        self.hide()

    def show(self) -> None:
        self._selected = 0
        self._update_selection()
        self.set_visible(True)
        self._begin_fade()

    def hide(self) -> None:
        self.set_visible(False)

    def move(self, delta: int) -> None:
        if not self._rows:
            return
        self._select(max(0, min(self._selected + delta, len(self._rows) - 1)))

    def activate_selected(self) -> None:
        self._activate(self._selected)

    def set_hover_enabled(self, enabled: bool) -> None:
        self._hover_enabled = enabled

    def _on_hover(self, index: int) -> None:
        if self._hover_enabled:
            self._select(index)

    def _select(self, index: int) -> None:
        if index == self._selected:
            return
        self._selected = index
        self._update_selection()

    def _activate(self, index: int) -> None:
        self.hide()
        self._items[index].action()

    def _update_selection(self) -> None:
        for i, row in enumerate(self._rows):
            if i == self._selected:
                row.add_css_class("selected")
            else:
                row.remove_css_class("selected")


def point_at(x: float, y: float) -> Graphene.Point:
    point = Graphene.Point()
    point.init(x, y)
    return point

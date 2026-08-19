# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-bleed overlays: the launching overlay (§6.4) and the system menu
(power actions + exit, §6.8/§8 — the minimal stand-in for M8's full
Settings screen, see DECISIONS.md for the scope call).

Both are sized from the du scale and both are operable with either a D-pad
or a mouse, because the hardware this runs on is a controller or a phone
acting as a trackpad and neither one gets to be second-class.
"""

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
from salon.ui.scale import Scale  # noqa: E402


def _rgba(red: float, green: float, blue: float, alpha: float = 1.0) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red = red
    color.green = green
    color.blue = blue
    color.alpha = alpha
    return color


def _parse(value: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(value)
    return color


_SURFACE_0 = _parse(tokens.color("surface-0"))
_ACCENT = _parse(tokens.color("accent"))
_TRANSPARENT = _rgba(0.0, 0.0, 0.0, 0.0)


class _AccentScrim(Gtk.Widget):
    """A near-opaque field with a soft pool of the launching tile's colour
    behind the text — §6.4 asks for a full-bleed overlay built from the
    tile's artwork, and this is the same light-fall treatment the tile and
    backdrop use, so a launch looks like the tile expanding rather than like
    a modal dialog appearing."""

    def __init__(self) -> None:
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self._accent = _ACCENT

    def set_accent(self, accent: Gdk.RGBA | None) -> None:
        # As a light source, not a surface colour — a muted app-icon accent
        # produces no visible pool at all at this alpha (see glow_color).
        self._accent = glow_color(accent) if accent is not None else _ACCENT
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0:
            return
        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)
        scrim = _rgba(_SURFACE_0.red, _SURFACE_0.green, _SURFACE_0.blue, 0.95)
        snapshot.append_color(scrim, bounds)

        center = Graphene.Point()
        center.init(width / 2.0, height * 0.45)
        inner = Gsk.ColorStop()
        inner.offset = 0.0
        inner.color = _rgba(self._accent.red, self._accent.green, self._accent.blue, 0.22)
        outer = Gsk.ColorStop()
        outer.offset = 1.0
        outer.color = _TRANSPARENT
        radius = max(width, height) * 0.45
        snapshot.append_radial_gradient(bounds, center, radius, radius, 0.0, 1.0, [inner, outer])


class LaunchingOverlay(Gtk.Overlay):
    """Absorbs all input until the child window takes focus (or a 12s
    timeout shows a recovery message instead) — that's what prevents a
    second OK press from double-launching while it's up."""

    def __init__(self, scale: Scale) -> None:
        super().__init__()
        self.set_visible(False)
        # Absorb input so a second OK/BACK press can't double-launch or
        # leak through to whatever's behind the overlay while it's up.
        self.set_can_target(True)

        self._scrim = _AccentScrim()
        self.set_child(self._scrim)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content.set_halign(Gtk.Align.CENTER)
        self._content.set_valign(Gtk.Align.CENTER)
        self.add_overlay(self._content)

        self._spinner = Gtk.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._content.append(self._spinner)

        self._title_label = Gtk.Label()
        self._title_label.add_css_class("salon-launching-title")
        self._title_label.set_halign(Gtk.Align.CENTER)
        self._content.append(self._title_label)

        self._message_label = Gtk.Label()
        self._message_label.add_css_class("salon-launching-message")
        self._message_label.set_halign(Gtk.Align.CENTER)
        self._message_label.set_visible(False)
        self._content.append(self._message_label)

        # The way back, said while it can still be read. Once the child has
        # the screen this overlay is behind it and so is every toast Salon
        # can raise — the seconds between OK and the app appearing are the
        # only window in which Salon can tell anyone anything at all.
        self._hint_label = Gtk.Label()
        self._hint_label.add_css_class("salon-launching-message")
        self._hint_label.set_halign(Gtk.Align.CENTER)
        self._content.append(self._hint_label)

        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self._content.set_spacing(scale.px(28.0))
        self._spinner.set_size_request(scale.px(64.0), scale.px(64.0))

    def show_for(self, tile: Tile, accent: Gdk.RGBA | None = None, hint: str = "") -> None:
        self._scrim.set_accent(accent)
        self._title_label.set_label(f"Starting {tile.title}…")
        self._message_label.set_visible(False)
        self._hint_label.set_label(hint)
        self._hint_label.set_visible(bool(hint))
        self._spinner.set_spinning(True)
        self.set_visible(True)

    def show_timed_out(self) -> None:
        self._message_label.set_label(
            "This is taking a while — check that the app started, or press BACK."
        )
        self._message_label.set_visible(True)

    def hide(self) -> None:
        self._spinner.set_spinning(False)
        self.set_visible(False)


@dataclass(frozen=True, slots=True)
class SystemMenuItem:
    label: str
    action: Callable[[], None]
    danger: bool = False


class SystemMenu(Gtk.Box):
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
        if bounds[0] and bounds[1].contains_point(_point(x, y)):
            return
        self.hide()

    def show(self) -> None:
        self._selected = 0
        self._update_selection()
        self.set_visible(True)

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


def _point(x: float, y: float) -> Graphene.Point:
    point = Graphene.Point()
    point.init(x, y)
    return point

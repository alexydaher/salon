# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused full-screen overlay widget."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Graphene, Gtk  # noqa: E402

from salon.ui import motion  # noqa: E402
from salon.ui.legend import Hint, Legend  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.system_menu_header import SystemMenuHeader  # noqa: E402
from salon.ui.system_menu_model import MenuFrame, SystemMenuItem  # noqa: E402
from salon.ui.system_menu_render import SystemMenuRenderer  # noqa: E402


class SystemMenu(Gtk.Box, motion.FadesIn, SystemMenuRenderer):
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

    def __init__(
        self,
        items: list[SystemMenuItem],
        scale: Scale,
        *,
        on_visibility_changed: Callable[[], None] | None = None,
        on_selection_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._init_fade()
        self.add_css_class("salon-system-menu-scrim")
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_visible(False)
        self.set_accessible_role(Gtk.AccessibleRole.MENU)

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

        self._header = SystemMenuHeader()
        self._card.append(self._header)
        self._header_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self._card.append(self._header_separator)

        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroller.set_propagate_natural_height(True)
        self._items_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._scroller.set_child(self._items_box)
        self._card.append(self._scroller)

        self._description = Gtk.Label()
        self._description.add_css_class("salon-system-menu-description")
        self._description.set_halign(Gtk.Align.START)
        self._description.set_xalign(0.0)
        self._description.set_wrap(True)
        self._description.set_visible(False)
        self._card.append(self._description)

        self._scale = scale
        self._on_visibility_changed = on_visibility_changed
        self._on_selection_changed = on_selection_changed
        self._frames: list[MenuFrame] = []
        self._rows: list[Gtk.Button] = []
        # Hover only moves the selection when the pointer is genuinely in
        # use. GTK delivers a motion event when a widget maps under a
        # stationary cursor, so without this the menu opens with whatever
        # item happens to be under the mouse selected rather than the first.
        self._hover_enabled = False
        self._header_subtitle = ""
        self._header_icon_name = ""
        self._content_insets: tuple[float, float] | None = None
        self.set_items(items)
        self._legend = Legend(scale)
        self._legend.set_visible(False)
        self.append(self._legend)

        dismiss = Gtk.GestureClick()
        dismiss.connect("released", self._on_scrim_clicked)
        self.add_controller(dismiss)

        self.set_scale(scale)

    def set_items(
        self,
        items: list[SystemMenuItem],
        *,
        title: str = "",
        frame_id: str = "root",
        selected: int = 0,
        subtitle: str = "",
        icon_name: str = "",
    ) -> None:
        """Replace the root frame when dynamic labels or capabilities change."""
        self._frames = [MenuFrame(frame_id, title, items, selected)]
        self._header_subtitle = subtitle
        self._header_icon_name = icon_name
        self._render_frame()

    def push_frame(self, frame: MenuFrame) -> None:
        """Enter a submenu without unmapping the scrim or losing its parent."""
        self._frames.append(frame)
        self._render_frame()
        self.announce(f"{frame.title} menu", Gtk.AccessibleAnnouncementPriority.MEDIUM)

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
        # Only fade a card that was not already on screen. Pushing a second
        # level, or a confirmation, replaces the items of a menu that is
        # already visible — fading the whole scrim up again there reads as
        # the screen flinching rather than as a card arriving.
        was_visible = self.get_visible()
        self.set_visible(True)
        self._update_selection()
        if not was_visible:
            self._begin_fade()
        self._notify_visibility()

    def hide(self) -> None:
        self.set_visible(False)
        if len(self._frames) > 1:
            self._frames = self._frames[:1]
            self._render_frame()
        self._notify_visibility()

    def _notify_visibility(self) -> None:
        if self._on_visibility_changed is not None:
            self._on_visibility_changed()

    @property
    def has_back(self) -> bool:
        """Whether BACK here goes up a level rather than closing."""
        return len(self._frames) > 1

    @property
    def selected_row(self) -> Gtk.Button | None:
        if not self._rows or not self._frames:
            return None
        index = self._frames[-1].selected
        return self._rows[index] if 0 <= index < len(self._rows) else None

    @property
    def selected_item(self) -> SystemMenuItem | None:
        if not self._frames:
            return None
        frame = self._frames[-1]
        return frame.items[frame.selected] if 0 <= frame.selected < len(frame.items) else None

    @property
    def current_title(self) -> str:
        return self._frames[-1].title if self._frames else ""

    @property
    def current_frame_id(self) -> str:
        return self._frames[-1].frame_id if self._frames else ""

    def set_hints(self, hints: tuple[Hint, ...]) -> None:
        self._legend.set_hints(hints)

    def back(self) -> None:
        """BACK: up one level if this card is one, closed if it is not."""
        if len(self._frames) > 1:
            self._frames.pop()
            self._render_frame()
            title = self.current_title
            if title:
                self.announce(f"{title} menu", Gtk.AccessibleAnnouncementPriority.MEDIUM)
            return
        self.hide()

    def move(self, delta: int) -> None:
        if not self._rows:
            return
        frame = self._frames[-1]
        self._select(max(0, min(frame.selected + delta, len(self._rows) - 1)))

    def activate_selected(self) -> None:
        if self._frames:
            self._activate(self._frames[-1].selected)

    def set_hover_enabled(self, enabled: bool) -> None:
        self._hover_enabled = enabled

    def _on_hover(self, index: int) -> None:
        if self._hover_enabled:
            self._select(index)

    def _select(self, index: int) -> None:
        if not self._frames or index == self._frames[-1].selected:
            return
        self._frames[-1].selected = index
        self._update_selection()

    def _activate(self, index: int) -> None:
        if not self._frames:
            return
        item = self._frames[-1].items[index]
        if item.submenu is not None:
            self.push_frame(item.submenu())
            return
        if item.action is None:
            return
        if item.closes:
            self.hide()
        item.action()


def point_at(x: float, y: float) -> Graphene.Point:
    point = Graphene.Point()
    point.init(x, y)
    return point

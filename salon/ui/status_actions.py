# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused top-bar widget."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402

_TICK_INTERVAL_MS = 1000


class StatusBar(Gtk.Box):
    """The global action buttons, in the top-right corner.

    `set_nav_focused` / `move` / `activate` are the D-pad path; the same
    buttons handle clicks and hover on their own, so the pointer never needs
    a second code path.
    """

    def __init__(
        self,
        scale: Scale,
        *,
        on_search: Callable[[], None],
        on_apps: Callable[[], None],
        on_phone: Callable[[], None],
        on_more: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.START)
        self.add_css_class("salon-status-bar")
        self.set_accessible_role(Gtk.AccessibleRole.TOOLBAR)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Shortcuts"])

        self._buttons: list[Gtk.Button] = []
        # What the detail strip says while the cursor is on each button.
        # A tooltip is a mouse affordance and the pill label is two words;
        # this is the sentence, and it is the only place a remote-holder is
        # told what "All apps" is as distinct from the tiles they can see.
        self._hints: list[tuple[str, str]] = []
        self._button_labels: list[Gtk.Label] = []
        self._button_boxes: list[Gtk.Box] = []
        self._button_images: list[Gtk.Image] = []
        self._connection_badges: list[Gtk.Widget] = []
        self._actions: list[Callable[[], None]] = []
        for icon_name, tooltip, handler, hint in (
            ("system-search-symbolic", "Search", on_search, "Find a tile or an installed app"),
            ("view-grid-symbolic", "All apps", on_apps, "Every installed application, A to Z"),
            # Connecting a phone remains visible because it also carries
            # controller/phone presence. Settings and Power moved behind
            # More: duplicating them here made the toolbar a second menu.
            # Before More, not inside it: connecting a phone is the
            # best input this television has, and burying the way to do it
            # is how it stayed unused.
            ("phone-symbolic", "Connect a phone", on_phone, "Use a phone as the remote"),
            ("view-more-symbolic", "More", on_more, "Open the Salon menu"),
        ):
            self._hints.append((tooltip, hint))
            button = self._make_button(icon_name, tooltip, handler)
            self.append(button)
            if icon_name == "phone-symbolic":
                self._phone_button = button
                self._phone_badge = self._connection_badges[-1]

        self._selected = 0
        self._nav_focused = False
        # Same guard the tiles and the system menu use: GTK delivers a
        # motion event whenever a widget maps under a stationary cursor, so
        # hover only moves the selection once the pointer has really moved.
        self._hover_enabled = False

        self.set_scale(scale)

    def _make_button(
        self, icon_name: str, tooltip: str, on_click: Callable[[], None]
    ) -> Gtk.Button:
        button = Gtk.Button()
        button.add_css_class("salon-status-button")
        button.set_valign(Gtk.Align.CENTER)
        button.set_tooltip_text(tooltip)
        # Icon-only, so there is no child text for GTK to derive a name
        # from: without this a screen reader announces four "button"s.
        button.update_property([Gtk.AccessibleProperty.LABEL], [tooltip])
        # ...and a tooltip is a mouse-only affordance. Someone holding a
        # remote three metres away sees four grey glyphs and has to guess.
        # The label appears beside the icon when the cursor reaches it and
        # the button grows to a pill, so the bar stays quiet at rest.
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_halign(Gtk.Align.CENTER)
        image = Gtk.Image.new_from_icon_name(icon_name)
        icon = Gtk.Overlay()
        icon.set_child(image)
        # Height-centred, and only as tall as the glyph: a filled overlay
        # would put the presence badge below the icon rather than on it.
        icon.set_valign(Gtk.Align.CENTER)
        badge = Gtk.Box()
        badge.add_css_class("salon-connection-badge")
        badge.set_halign(Gtk.Align.END)
        badge.set_valign(Gtk.Align.END)
        badge.set_can_target(False)
        badge.set_visible(False)
        icon.add_overlay(badge)
        box.append(icon)
        if icon_name == "phone-symbolic":
            controller_icon = Gtk.Image.new_from_icon_name("input-gaming-symbolic")
            controller_icon.add_css_class("salon-controller-indicator")
            controller_icon.set_visible(False)
            box.append(controller_icon)
            self._controller_icon = controller_icon
        label = Gtk.Label(label=tooltip)
        label.add_css_class("salon-status-button-label")
        label.set_visible(False)
        box.append(label)
        button.set_child(box)
        self._button_labels.append(label)
        self._button_boxes.append(box)
        self._button_images.append(image)
        self._connection_badges.append(badge)
        index = len(self._buttons)
        button.connect("clicked", lambda _b: on_click())
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_: self._on_hover(index))
        button.add_controller(motion)
        self._buttons.append(button)
        self._actions.append(on_click)
        return button

    def set_scale(self, scale: Scale) -> None:
        safe_margin = scale.safe_margin_px
        top_margin = max(0, safe_margin - scale.px(24.0))
        self.set_spacing(scale.px(12.0))
        self.set_margin_top(top_margin)
        self.set_margin_end(safe_margin)
        size = scale.px(54.0)
        self._button_height = size
        for button in self._buttons:
            # Square at rest, so an icon-only button is a circle. The width
            # has to be requested on the *button*: asking the child box for
            # it instead made the box wider than its icon, and a Gtk.Box
            # packs a non-expanding child at its start rather than centring
            # it — which is how every glyph ended up left of centre.
            button.set_size_request(size, size)
        for index, box in enumerate(self._button_boxes):
            box.set_spacing(scale.px(10.0))
            self._button_images[index].set_pixel_size(scale.px(28.0))
            badge_size = scale.px(10.0)
            self._connection_badges[index].set_size_request(badge_size, badge_size)
        self._controller_icon.set_pixel_size(scale.px(26.0))
        self._update_selection()

    def set_connection_state(self, *, controller: bool, phone: bool) -> None:
        """Show that at least one usable remote is already attached.

        The phone action remains available so another phone can still scan
        the code; the badge only answers the at-a-glance question of whether
        Salon currently has something connected.
        """
        self._controller_icon.set_visible(controller)
        self._phone_badge.set_visible(phone)
        if controller and phone:
            status = "Controller and phone connected"
        elif controller:
            status = "Controller connected"
        elif phone:
            status = "Phone connected"
        else:
            status = "Connect a phone"
        self._phone_button.set_tooltip_text(status)
        self._phone_button.update_property([Gtk.AccessibleProperty.LABEL], [status])

    # --- focus ------------------------------------------------------------

    @property
    def nav_focused(self) -> bool:
        return self._nav_focused

    @property
    def selected_hint(self) -> tuple[str, str]:
        """The current button's name and what it does, for the strip."""
        if 0 <= self._selected < len(self._hints):
            return self._hints[self._selected]
        return ("", "")

    @property
    def selected_button(self) -> Gtk.Button | None:
        if 0 <= self._selected < len(self._buttons):
            return self._buttons[self._selected]
        return None

    def set_hover_enabled(self, enabled: bool) -> None:
        self._hover_enabled = enabled

    def set_nav_focused(self, focused: bool, *, index: int | None = None) -> None:
        """Enter or leave the bar. `index` picks the landing button — the
        home screen passes the last one so UP from the tiles lands on Power
        only if that's where the cursor was left, and 0 otherwise."""
        self._nav_focused = focused
        if index is not None:
            self._selected = max(0, min(index, len(self._buttons) - 1))
        self._update_selection()

    def move(self, delta: int) -> bool:
        """Returns False at either end so the caller can rubber-band."""
        target = self._selected + delta
        if not (0 <= target < len(self._buttons)):
            return False
        self._selected = target
        self._update_selection()
        return True

    def activate(self) -> None:
        if 0 <= self._selected < len(self._actions):
            self._actions[self._selected]()

    def _on_hover(self, index: int) -> None:
        if self._hover_enabled:
            self._selected = index
            if self._nav_focused:
                self._update_selection()

    def _update_selection(self) -> None:
        for index, button in enumerate(self._buttons):
            selected = self._nav_focused and index == self._selected
            if selected:
                button.add_css_class("selected")
            else:
                button.remove_css_class("selected")
            self._button_labels[index].set_visible(selected)

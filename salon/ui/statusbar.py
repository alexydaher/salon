# SPDX-License-Identifier: GPL-3.0-or-later
"""The top bar (§6.9): clock, date, and the launcher's global actions.

A thin strip in the top safe-area margin holding the time in the display
face with tabular figures (so the layout doesn't twitch every minute as
digit widths change), the date beside it in the body face, and — to their
right — Search, All apps, Settings and Power.

Those four are a **focusable row**, not just mouse targets. Pressing UP from
the first row of tiles moves the cursor up here, exactly as it does on every
ten-foot launcher; DOWN drops back into the tiles. Before that they were
reachable only through MENU, which is invisible: nothing on screen said the
button existed, and a user without a controller had nothing but two dim
icons to guess at.

Left of the clock sit the two status glyphs §6.9 asks for: network and
battery. Both are **honestly absent** rather than stubbed — the network
glyph disappears if NetworkManager isn't there to ask, and the battery one
only ever appears on a machine that actually has a battery, which the box
under a television does not. Neither is focusable and neither is clickable:
they are the two things on this screen that report rather than do, and
Settings › Network is where the detail lives.

Everything in the bar carries an accessible name. The clock's is the time
spoken in words rather than "14:05", and the four buttons are icon-only, so
without an explicit label a screen reader would announce them as "button".
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.services.battery import BatteryStatus, BatteryWatcher  # noqa: E402
from salon.services.netinfo import NetworkStatus, NetworkWatcher  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

_TICK_INTERVAL_MS = 1000


class StatusBar(Gtk.Box):
    """The clock/date pair plus the global action buttons.

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
        on_settings: Callable[[], None],
        on_power: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.START)
        self.add_css_class("salon-status-bar")
        self.set_accessible_role(Gtk.AccessibleRole.TOOLBAR)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Status and shortcuts"])

        # The two glyphs sit in their own box with a tighter gap than the
        # bar's: they are one group ("what state is this machine in"), and
        # at the bar's spacing they read as two unrelated icons that happen
        # to be adjacent.
        self._glyph_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._glyph_box.set_valign(Gtk.Align.CENTER)
        self.append(self._glyph_box)
        self._network_glyph = self._make_glyph()
        self._battery_glyph = self._make_glyph()

        self._date_label = Gtk.Label()
        self._date_label.add_css_class("salon-status-date")
        self._date_label.set_valign(Gtk.Align.BASELINE_CENTER)
        self.append(self._date_label)

        self._clock_label = Gtk.Label()
        self._clock_label.add_css_class("salon-status-clock")
        self._clock_label.set_valign(Gtk.Align.BASELINE_CENTER)
        self.append(self._clock_label)

        self._buttons: list[Gtk.Button] = []
        self._button_labels: list[Gtk.Label] = []
        self._button_boxes: list[Gtk.Box] = []
        self._actions: list[Callable[[], None]] = []
        for icon_name, tooltip, handler in (
            ("system-search-symbolic", "Search", on_search),
            ("view-grid-symbolic", "All apps", on_apps),
            # Before Settings, not inside it: connecting a phone is the
            # best input this television has, and burying the way to do it
            # under a settings panel is how it stayed unused. Power keeps
            # the end of the row — it is the one nobody should land on by
            # overshooting.
            ("phone-symbolic", "Connect a phone", on_phone),
            ("emblem-system-symbolic", "Settings", on_settings),
            ("system-shutdown-symbolic", "Power", on_power),
        ):
            self.append(self._make_button(icon_name, tooltip, handler))

        self._selected = 0
        self._nav_focused = False
        # Same guard the tiles and the system menu use: GTK delivers a
        # motion event whenever a widget maps under a stationary cursor, so
        # hover only moves the selection once the pointer has really moved.
        self._hover_enabled = False

        # The bar owns its own feeds: nothing else in the app wants them,
        # and routing them through HomeView would only add a hop. Both are
        # asynchronous from the first call, so this costs no startup time
        # and a missing daemon costs a hidden glyph rather than a stall.
        self._network_watcher = NetworkWatcher(self.set_network)
        self._battery_watcher = BatteryWatcher(self.set_battery)
        self._network_watcher.start()
        self._battery_watcher.start()

        self.set_scale(scale)
        self._tick()
        GLib.timeout_add(_TICK_INTERVAL_MS, self._tick)

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
        box.append(image)
        label = Gtk.Label(label=tooltip)
        label.add_css_class("salon-status-button-label")
        label.set_visible(False)
        box.append(label)
        button.set_child(box)
        self._button_labels.append(label)
        self._button_boxes.append(box)
        index = len(self._buttons)
        button.connect("clicked", lambda _b: on_click())
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_: self._on_hover(index))
        button.add_controller(motion)
        self._buttons.append(button)
        self._actions.append(on_click)
        return button

    def _make_glyph(self) -> Gtk.Image:
        """A status glyph: dim, unfocusable, hidden until it has something
        true to say. Role IMG rather than the default, so assistive tech
        reads the label instead of skipping an unlabelled icon."""
        image = Gtk.Image()
        image.add_css_class("salon-status-glyph")
        image.set_valign(Gtk.Align.CENTER)
        image.set_visible(False)
        image.set_accessible_role(Gtk.AccessibleRole.IMG)
        self._glyph_box.append(image)
        return image

    def set_network(self, status: NetworkStatus) -> None:
        self._set_glyph(self._network_glyph, status.icon_name, status.phrase, low=False)

    def set_battery(self, status: BatteryStatus) -> None:
        self._set_glyph(self._battery_glyph, status.icon_name, status.phrase, low=status.low)

    def _set_glyph(self, image: Gtk.Image, icon_name: str, phrase: str, *, low: bool) -> None:
        if not icon_name:
            image.set_visible(False)
            return
        image.set_from_icon_name(icon_name)
        image.set_tooltip_text(phrase)
        image.update_property([Gtk.AccessibleProperty.LABEL], [phrase])
        if low:
            image.add_css_class("low")
        else:
            image.remove_css_class("low")
        image.set_visible(True)

    def set_scale(self, scale: Scale) -> None:
        margin = scale.px(
            tokens.REFERENCE_VIEWPORT_HEIGHT_PX * tokens.SAFE_AREA_DEFAULT_PERCENT / 100.0
        )
        self.set_spacing(scale.px(24.0))
        self.set_margin_top(margin)
        self.set_margin_end(margin)
        self._glyph_box.set_spacing(scale.px(10.0))
        for glyph in (self._network_glyph, self._battery_glyph):
            glyph.set_pixel_size(scale.px(30.0))
        size = scale.px(52.0)
        self._button_height = size
        for button in self._buttons:
            button.set_size_request(-1, size)
        for box in self._button_boxes:
            box.set_spacing(scale.px(10.0))
            box.set_size_request(size, -1)
            child = box.get_first_child()
            if isinstance(child, Gtk.Image):
                child.set_pixel_size(scale.px(30.0))
        self._update_selection()

    # --- focus ------------------------------------------------------------

    @property
    def nav_focused(self) -> bool:
        return self._nav_focused

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

    def _tick(self) -> bool:
        now = datetime.now()
        self._clock_label.set_label(now.strftime("%H:%M"))
        self._date_label.set_label(now.strftime("%A, %-d %B"))
        # "14:05" is read out as a number, or as two; the spoken form is
        # what the label is *for* to anyone not reading it.
        self._clock_label.update_property(
            [Gtk.AccessibleProperty.LABEL], [now.strftime("%-I:%M %p, %A %-d %B")]
        )
        return bool(GLib.SOURCE_CONTINUE)

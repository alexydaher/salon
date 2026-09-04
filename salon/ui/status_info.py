# SPDX-License-Identifier: GPL-3.0-or-later
"""Clock and machine state for Aurora Console's standing column."""

from __future__ import annotations

import os
from datetime import datetime
from typing import cast

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from salon.core.clockformat import ClockPreference  # noqa: E402
from salon.services.battery import BatteryStatus, BatteryWatcher  # noqa: E402
from salon.services.netinfo import NetworkStatus, NetworkWatcher  # noqa: E402
from salon.ui import clock_strings  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

_TICK_INTERVAL_MS = 1000


def _reveal(icon: Gtk.Widget, visible: bool = True) -> None:
    """Show or hide the stat row an icon belongs to, and the card with it.

    The card goes too when the last row does. Hiding only the rows left an
    empty rounded rectangle in the console column — which is worse than the
    placeholders it replaced, because at least those said what they were.
    """
    row = icon.get_parent()
    if row is None:
        return
    row.set_visible(visible)
    card = row.get_parent()
    if card is None:
        return
    sibling = card.get_first_child()
    while sibling is not None:
        if sibling.get_visible():
            card.set_visible(True)
            return
        sibling = sibling.get_next_sibling()
    card.set_visible(False)


class StatusInfo(Gtk.Box):
    """The two non-interactive blocks at the top of the console column."""

    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-console-status")
        self.set_accessible_role(Gtk.AccessibleRole.GROUP)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["System status"])
        self._clock_preference: ClockPreference = "automatic"

        time_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        time_card.add_css_class("salon-console-block")
        time_card.add_css_class("salon-console-time")
        # The hour and the meridiem are two labels on one baseline, not one
        # string. "8:15 PM" set at twice the clock size is wider than the
        # console column's fixed 336px — GTK said so out loud, "needs at
        # least 340" — and a 12-hour region is not an edge case. Setting the
        # designator at the date's size is also simply how a clock is drawn.
        clock_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        clock_line.set_halign(Gtk.Align.START)
        self._clock_label = Gtk.Label()
        self._clock_label.add_css_class("salon-status-clock")
        self._clock_label.set_halign(Gtk.Align.START)
        self._clock_label.set_valign(Gtk.Align.BASELINE)
        clock_line.append(self._clock_label)
        self._meridiem_label = Gtk.Label()
        self._meridiem_label.add_css_class("salon-status-meridiem")
        self._meridiem_label.set_halign(Gtk.Align.START)
        self._meridiem_label.set_valign(Gtk.Align.BASELINE)
        self._meridiem_label.set_visible(False)
        clock_line.append(self._meridiem_label)
        self._clock_line = clock_line
        time_card.append(clock_line)
        self._date_label = Gtk.Label()
        self._date_label.add_css_class("salon-status-date")
        self._date_label.set_halign(Gtk.Align.START)
        time_card.append(self._date_label)
        self.append(time_card)
        self._time_card = time_card

        system_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        system_card.add_css_class("salon-console-block")
        self._network = self._make_row(system_card, "network-wireless-symbolic", "Network")
        self._battery = self._make_row(system_card, "battery-symbolic", "Battery")
        self._applications = self._make_row(system_card, "view-grid-symbolic", "Applications")
        system_card.set_visible(False)
        self.append(system_card)
        self._system_card = system_card

        self._network_watcher = NetworkWatcher(self.set_network)
        self._battery_watcher = BatteryWatcher(self.set_battery)
        if not os.environ.get("SALON_CAPTURE_MODE"):
            self._network_watcher.start()
            self._battery_watcher.start()

        self.set_scale(scale)
        self._tick()
        GLib.timeout_add(_TICK_INTERVAL_MS, self._tick)

    @staticmethod
    def _make_row(
        parent: Gtk.Box, icon_name: str, label: str
    ) -> tuple[Gtk.Image, Gtk.Label, Gtk.Label]:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.add_css_class("salon-console-stat")
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.add_css_class("salon-console-stat-icon")
        row.append(icon)
        name = Gtk.Label(label=label)
        name.add_css_class("salon-console-stat-name")
        name.set_halign(Gtk.Align.START)
        name.set_hexpand(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(name)
        value = Gtk.Label()
        value.add_css_class("salon-console-stat-value")
        value.set_halign(Gtk.Align.END)
        row.append(value)
        # Hidden until it has something true to say. These rows used to sit
        # there permanently reading "Network —", "Battery —" — three lines
        # of furniture asserting nothing, and on a television with no
        # battery the second one was never going to say anything else.
        # "Honestly absent" has to mean absent.
        row.set_visible(False)
        parent.append(row)
        return icon, name, value

    def set_network(self, status: NetworkStatus) -> None:
        icon, name, value = self._network
        # `available` is "NetworkManager answered at all", which is the same
        # test the battery row makes and for the same reason: with no daemon
        # there is nothing true to say, and the row would draw "Network —
        # Unknown" for the life of the session. Not connected is a different
        # answer and keeps its row — "No connection" is a fact, and the one
        # somebody staring at a dead television needs.
        _reveal(icon, status.available)
        if not status.available:
            return
        if status.icon_name:
            icon.set_from_icon_name(status.icon_name)
        name.set_label(status.name or status.kind or "Network")
        if status.strength >= 75:
            value.set_label("Strong")
        elif status.strength >= 40:
            value.set_label("Good")
        elif status.strength >= 0:
            value.set_label("Weak")
        else:
            value.set_label(status.connectivity)
        row = icon.get_parent()
        if row is not None:
            row.set_tooltip_text(status.phrase)

    def set_battery(self, status: BatteryStatus) -> None:
        icon, name, value = self._battery
        # Only a real battery earns a row. "Power — Connected" on a machine
        # wired to the wall is a line that can never change.
        _reveal(icon, status.present)
        if not status.present:
            return
        if status.icon_name:
            icon.set_from_icon_name(status.icon_name)
        name.set_label("Battery")
        value.set_label(f"{round(status.percent)}%")
        if status.low:
            value.add_css_class("low")
        else:
            value.remove_css_class("low")

    def set_running_count(self, count: int) -> None:
        """How many launched applications are still up.

        The only state this row appears for. It used to carry a count of
        *installed* applications the rest of the time — a fact nobody acts
        on, holding a permanent line in the console; All Apps says it in
        its own header, where somebody is actually asking.
        """
        icon, name, value = self._applications
        running = max(0, count)
        _reveal(icon, bool(running))
        if running:
            icon.set_from_icon_name("view-grid-symbolic")
            name.set_label("Apps still running")
            value.set_label(str(running))

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(18.0))
        self._time_card.set_spacing(scale.px(3.0))
        self._clock_line.set_spacing(scale.px(6.0))
        self._system_card.set_spacing(0)
        self._time_card.set_size_request(-1, scale.px(140.0))
        self._system_card.set_size_request(-1, scale.px(181.0))
        for icon, _name, _value in (self._network, self._battery, self._applications):
            icon.set_pixel_size(scale.px(21.0))

    def set_clock_preference(self, preference: str) -> None:
        """"automatic", "12-hour" or "24-hour" — see `core/clockformat.py`."""
        if preference == self._clock_preference:
            return
        self._clock_preference = cast(ClockPreference, preference)
        self._tick()

    def _tick(self) -> bool:
        fixed = os.environ.get("SALON_CAPTURE_CLOCK")
        now = datetime.fromisoformat(fixed) if fixed else datetime.now()
        preference = self._clock_preference
        hour, meridiem = clock_strings.split_clock(now, preference)
        self._clock_label.set_label(hour)
        self._meridiem_label.set_label(meridiem)
        self._meridiem_label.set_visible(bool(meridiem))
        self._date_label.set_label(now.strftime(clock_strings.date_format()))
        # Derived from the same rules as the drawn strings rather than
        # written out again: this label used to be 12-hour beside a clock
        # that was always 24-hour, so the screen reader and the screen
        # disagreed about the format of the same instant.
        self._clock_label.update_property(
            [Gtk.AccessibleProperty.LABEL], [now.strftime(clock_strings.spoken_format(preference))]
        )
        return bool(GLib.SOURCE_CONTINUE)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Clock and machine state for Aurora Console's standing column."""

from __future__ import annotations

import os
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from salon.services.battery import BatteryStatus, BatteryWatcher  # noqa: E402
from salon.services.netinfo import NetworkStatus, NetworkWatcher  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

_TICK_INTERVAL_MS = 1000


class StatusInfo(Gtk.Box):
    """The two non-interactive blocks at the top of the console column."""

    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-console-status")
        self.set_accessible_role(Gtk.AccessibleRole.GROUP)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["System status"])

        time_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        time_card.add_css_class("salon-console-block")
        time_card.add_css_class("salon-console-time")
        self._clock_label = Gtk.Label()
        self._clock_label.add_css_class("salon-status-clock")
        self._clock_label.set_halign(Gtk.Align.START)
        time_card.append(self._clock_label)
        self._date_label = Gtk.Label()
        self._date_label.add_css_class("salon-status-date")
        self._date_label.set_halign(Gtk.Align.START)
        time_card.append(self._date_label)
        self.append(time_card)

        system_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        system_card.add_css_class("salon-console-block")
        heading = Gtk.Label(label="SYSTEM")
        heading.add_css_class("salon-console-heading")
        heading.set_halign(Gtk.Align.START)
        system_card.append(heading)
        self._network = self._make_row(system_card, "network-wireless-symbolic", "Network")
        self._battery = self._make_row(system_card, "battery-symbolic", "Battery")
        self._applications = self._make_row(system_card, "view-grid-symbolic", "Applications")
        self.append(system_card)

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
        value = Gtk.Label(label="—")
        value.add_css_class("salon-console-stat-value")
        value.set_halign(Gtk.Align.END)
        row.append(value)
        parent.append(row)
        return icon, name, value

    def set_network(self, status: NetworkStatus) -> None:
        icon, name, value = self._network
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
        if status.icon_name:
            icon.set_from_icon_name(status.icon_name)
        name.set_label("Battery" if status.present else "Power")
        value.set_label(f"{round(status.percent)}%" if status.present else "Connected")
        if status.low:
            value.add_css_class("low")
        else:
            value.remove_css_class("low")

    def set_application_count(self, count: int) -> None:
        self._applications[2].set_label(str(max(0, count)))

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(18.0))
        for card in (self.get_first_child(), self.get_last_child()):
            if isinstance(card, Gtk.Box):
                card.set_spacing(scale.px(8.0))
        for icon, _name, _value in (self._network, self._battery, self._applications):
            icon.set_pixel_size(scale.px(21.0))

    def _tick(self) -> bool:
        fixed = os.environ.get("SALON_CAPTURE_CLOCK")
        now = datetime.fromisoformat(fixed) if fixed else datetime.now()
        self._clock_label.set_label(now.strftime("%H:%M"))
        self._date_label.set_label(now.strftime("%A, %-d %B"))
        self._clock_label.update_property(
            [Gtk.AccessibleProperty.LABEL], [now.strftime("%-I:%M %p, %A %-d %B")]
        )
        return bool(GLib.SOURCE_CONTINUE)

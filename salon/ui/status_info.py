# SPDX-License-Identifier: GPL-3.0-or-later
"""Clock and the four most pertinent machine facts for the console rail."""

from __future__ import annotations

import os
from datetime import datetime
from typing import cast

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from salon.core.clockformat import ClockPreference  # noqa: E402
from salon.core.health import StorageReading, TemperatureReading  # noqa: E402
from salon.core.status_card import StatusItem, choose  # noqa: E402
from salon.services.audio_status import AudioStatus, AudioStatusWatcher  # noqa: E402
from salon.services.battery import BatteryStatus, BatteryWatcher  # noqa: E402
from salon.services.device_battery import DeviceBatteryStatus, DeviceBatteryWatcher  # noqa: E402
from salon.services.netinfo import NetworkStatus, NetworkWatcher  # noqa: E402
from salon.services.system_health import SystemHealthWatcher  # noqa: E402
from salon.ui import clock_strings, status_presenters  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

_TICK_INTERVAL_MS = 1000
_ITEM_ORDER = (
    "temperature", "storage", "network", "audio", "device-battery",
    "battery", "applications", "controls",
)


class StatusInfo(Gtk.Box):
    """Two standing blocks: local time and an adaptive four-row status card."""

    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-console-status")
        self.set_accessible_role(Gtk.AccessibleRole.GROUP)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["System status"])
        self._clock_preference: ClockPreference = "automatic"
        self._items: dict[str, StatusItem] = {}
        self._controller_count = 0
        self._phone_connected = False
        self._has_device_battery = False
        self._audio_status = AudioStatus()

        time_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        time_card.add_css_class("salon-console-block")
        time_card.add_css_class("salon-console-time")
        clock_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        clock_line.set_halign(Gtk.Align.START)
        self._clock_label = self._label("salon-status-clock")
        self._clock_label.set_valign(Gtk.Align.BASELINE)
        clock_line.append(self._clock_label)
        self._meridiem_label = self._label("salon-status-meridiem")
        self._meridiem_label.set_valign(Gtk.Align.BASELINE)
        self._meridiem_label.set_visible(False)
        clock_line.append(self._meridiem_label)
        self._clock_line = clock_line
        time_card.append(clock_line)
        self._date_label = self._label("salon-status-date")
        time_card.append(self._date_label)
        self.append(time_card)
        self._time_card = time_card

        self._system_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._system_card.add_css_class("salon-console-block")
        self._slots = tuple(self._make_row(self._system_card) for _index in range(4))
        self._system_card.set_visible(False)
        self.append(self._system_card)

        self._network_watcher = NetworkWatcher(self.set_network)
        self._battery_watcher = BatteryWatcher(self.set_battery)
        self._audio_watcher = AudioStatusWatcher(self.set_audio)
        self._device_battery_watcher = DeviceBatteryWatcher(self.set_device_batteries)
        self._health_watcher = SystemHealthWatcher(self.set_health)
        if not os.environ.get("SALON_CAPTURE_MODE"):
            for watcher in self._watchers:
                watcher.start()

        self.set_scale(scale)
        self._tick()
        self._clock_timer = GLib.timeout_add(_TICK_INTERVAL_MS, self._tick)

    @property
    def _watchers(self) -> tuple[object, ...]:
        return (self._network_watcher, self._battery_watcher, self._audio_watcher,
                self._device_battery_watcher, self._health_watcher)

    @staticmethod
    def _label(css_class: str) -> Gtk.Label:
        label = Gtk.Label()
        label.add_css_class(css_class)
        label.set_halign(Gtk.Align.START)
        return label

    @staticmethod
    def _make_row(parent: Gtk.Box) -> tuple[Gtk.Box, Gtk.Image, Gtk.Label, Gtk.Label]:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.add_css_class("salon-console-stat")
        icon = Gtk.Image()
        icon.add_css_class("salon-console-stat-icon")
        row.append(icon)
        name = StatusInfo._label("salon-console-stat-name")
        name.set_hexpand(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(name)
        value = Gtk.Label()
        value.add_css_class("salon-console-stat-value")
        value.set_halign(Gtk.Align.END)
        row.append(value)
        row.set_visible(False)
        parent.append(row)
        return row, icon, name, value

    def _put(self, item: StatusItem | None, key: str) -> None:
        if item is None:
            if key not in self._items:
                return
            self._items.pop(key, None)
        else:
            if self._items.get(key) == item:
                return
            self._items[key] = item
        self._render_items()

    def _render_items(self) -> None:
        ordered = tuple(self._items[key] for key in _ITEM_ORDER if key in self._items)
        visible = choose(ordered)
        for index, (row, icon, name, value) in enumerate(self._slots):
            if index >= len(visible):
                row.set_visible(False)
                continue
            item = visible[index]
            icon.set_from_icon_name(item.icon_name)
            name.set_label(item.name)
            value.set_label(item.value)
            row.set_tooltip_text(item.phrase)
            row.update_property([Gtk.AccessibleProperty.LABEL], [item.phrase])
            for tone in ("warning", "danger"):
                (row.add_css_class if item.tone == tone else row.remove_css_class)(tone)
            row.set_visible(True)
        self._system_card.set_visible(bool(visible))

    def set_network(self, status: NetworkStatus) -> None:
        self._put(status_presenters.network_item(status), "network")

    def set_battery(self, status: BatteryStatus) -> None:
        self._put(status_presenters.battery_item(status), "battery")

    def set_audio(self, status: AudioStatus) -> None:
        self._audio_status = status
        self._put(status_presenters.audio_item(status), "audio")

    def set_audio_muted(self, muted: bool) -> None:
        status = self._audio_status
        if status.available and not status.no_outputs:
            self.set_audio(AudioStatus(True, status.description, muted))

    def refresh_audio(self) -> None:
        self._audio_watcher.refresh()

    def set_device_batteries(self, statuses: tuple[DeviceBatteryStatus, ...]) -> None:
        self._has_device_battery = bool(statuses)
        self._put(status_presenters.device_battery_item(statuses), "device-battery")
        self._update_controls_item()

    def set_health(
        self, storage: StorageReading | None, temperature: TemperatureReading | None
    ) -> None:
        self._put(status_presenters.storage_item(storage), "storage")
        self._put(status_presenters.temperature_item(temperature), "temperature")

    def set_running_count(self, count: int) -> None:
        self._put(status_presenters.running_item(count), "applications")

    def set_connections(self, controllers: int, phone: bool) -> None:
        self._controller_count = max(0, controllers)
        self._phone_connected = phone
        self._update_controls_item()

    def _update_controls_item(self) -> None:
        item = status_presenters.controls_item(
            self._controller_count,
            self._phone_connected,
            controller_battery_visible=self._has_device_battery,
        )
        self._put(item, "controls")

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(18.0))
        self._time_card.set_spacing(scale.px(3.0))
        self._clock_line.set_spacing(scale.px(6.0))
        self._system_card.set_spacing(0)
        self._time_card.set_size_request(-1, scale.px(140.0))
        self._system_card.set_size_request(-1, scale.px(181.0))
        for _row, icon, _name, _value in self._slots:
            icon.set_pixel_size(scale.px(21.0))

    def set_clock_preference(self, preference: str) -> None:
        if preference != self._clock_preference:
            self._clock_preference = cast(ClockPreference, preference)
            self._tick()

    def _tick(self) -> bool:
        fixed = os.environ.get("SALON_CAPTURE_CLOCK")
        now = datetime.fromisoformat(fixed) if fixed else datetime.now()
        hour, meridiem = clock_strings.split_clock(now, self._clock_preference)
        self._clock_label.set_label(hour)
        self._meridiem_label.set_label(meridiem)
        self._meridiem_label.set_visible(bool(meridiem))
        self._date_label.set_label(now.strftime(clock_strings.date_format()))
        self._clock_label.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [now.strftime(clock_strings.spoken_format(self._clock_preference))],
        )
        return bool(GLib.SOURCE_CONTINUE)

    def do_dispose(self) -> None:
        if self._clock_timer:
            GLib.source_remove(self._clock_timer)
            self._clock_timer = 0
        for watcher in self._watchers:
            watcher.stop()  # type: ignore[attr-defined]
        Gtk.Box.do_dispose(self)

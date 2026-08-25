# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Focused top-bar widget."""
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

class StatusInfo(Gtk.Box):
    """The top-left corner: time, date, network, battery.

    Everything here reports and nothing here acts, so it takes no focus and
    no clicks — Settings › Network is where the detail lives. It owns its
    own feeds, because nothing else in the app wants them and routing them
    through HomeView would only add a hop. Both watchers are asynchronous
    from the first call, so this costs no startup time and a missing daemon
    costs a hidden glyph rather than a stall.
    """

    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.add_css_class("salon-status-bar")
        self.set_accessible_role(Gtk.AccessibleRole.GROUP)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Status"])

        # Clock first, nearest the corner, then the date, then the glyphs:
        # reading order out from the edge, which is the order the eye
        # arrives in on the left-hand side. It was the reverse when the
        # whole bar was right-aligned, for the same reason.
        self._clock_label = Gtk.Label()
        self._clock_label.add_css_class("salon-status-clock")
        self._clock_label.set_valign(Gtk.Align.BASELINE_CENTER)
        self.append(self._clock_label)

        self._date_label = Gtk.Label()
        self._date_label.add_css_class("salon-status-date")
        self._date_label.set_valign(Gtk.Align.BASELINE_CENTER)
        self.append(self._date_label)

        # The two glyphs sit in their own box with a tighter gap than the
        # row's: they are one group ("what state is this machine in"), and
        # at the row's spacing they read as two unrelated icons that happen
        # to be adjacent.
        self._glyph_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._glyph_box.set_valign(Gtk.Align.CENTER)
        self.append(self._glyph_box)
        self._network_glyph = self._make_glyph()
        self._battery_glyph = self._make_glyph()

        self._network_watcher = NetworkWatcher(self.set_network)
        self._battery_watcher = BatteryWatcher(self.set_battery)
        self._network_watcher.start()
        self._battery_watcher.start()

        self.set_scale(scale)
        self._tick()
        GLib.timeout_add(_TICK_INTERVAL_MS, self._tick)

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
        self.set_margin_start(margin)
        self._glyph_box.set_spacing(scale.px(10.0))
        for glyph in (self._network_glyph, self._battery_glyph):
            glyph.set_pixel_size(scale.px(30.0))

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

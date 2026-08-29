# SPDX-License-Identifier: GPL-3.0-or-later
"""The two ends of a settings list: the "More" pills, and the edge fade.

Both answer the same question — *is there anything past this edge?* — and
both are decided by the same two booleans, so they are one object rather
than a pair of concerns threaded through `SettingsList`. The list keeps the
selection, the scroll and the rows; this keeps everything drawn at the
boundary.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.ui.fades import snapshot_faded  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

# The band at each end that a pill sits in, kept clear of the rows — and the
# distance over which the rows passing under it fade out.
GUTTER_DU = 34.0
_PILL_WIDTH_DU = 112.0


class ListChrome:
    """Owned by one `SettingsList`, whose `Gtk.Fixed` it puts its pills in."""

    def __init__(self, host: Gtk.Fixed) -> None:
        self._host = host
        self.top = Gtk.Label(label="▲ More")
        self.bottom = Gtk.Label(label="▼ More")
        for pill in (self.top, self.bottom):
            pill.add_css_class("salon-scroll-indicator")
            pill.set_halign(Gtk.Align.FILL)
            pill.set_can_target(False)
            pill.set_visible(False)
            host.put(pill, 0, 0)

    def gutter(self, scale: Scale) -> int:
        return scale.px(GUTTER_DU)

    def layout(self, scale: Scale, width: int, height: int) -> int:
        """Place both pills, and return the gutter the rows must stay out of.

        The pills are opaque and were drawn straight over the content —
        Appearance rendered "Salon an▼More" across a row's value — so the
        row box carries a matching margin at each end.
        """
        gutter = self.gutter(scale)
        pill_width = min(width, scale.px(_PILL_WIDTH_DU))
        x = max(0, width - pill_width)
        for pill in (self.top, self.bottom):
            pill.set_size_request(pill_width, gutter)
        Gtk.Fixed.move(self._host, self.top, x, 0)
        Gtk.Fixed.move(self._host, self.bottom, x, max(0, height - gutter))
        return gutter

    def set_overhang(self, *, above: bool, below: bool) -> None:
        self.top.set_visible(above)
        self.bottom.set_visible(below)

    def snapshot(self, snapshot: Gtk.Snapshot, scale: Scale, content: Gtk.Widget) -> None:
        """Draw the rows faded into each gutter, then the pills over them.

        `Gtk.Overflow.HIDDEN` alone cut the boundary row through the middle
        of its glyphs — the sections column sliced "About" in half,
        Appearance sliced "Choose a picture…" — which reads as a rendering
        fault rather than as "there is more". This is the treatment the
        home band already gets, off the same helper, gated on the same fact
        the pills are: an end with nothing past it is not faded at all.

        The pills are drawn outside the mask deliberately. They sit in
        exactly the band the ramp is steepest over, so fading them with the
        rows would hide the affordance that explains the fade.
        """
        host = self._host
        ramp = float(self.gutter(scale))
        snapshot_faded(
            host,
            snapshot,
            float(host.get_width()),
            float(host.get_height()),
            ramp if self.top.get_visible() else 0.0,
            ramp if self.bottom.get_visible() else 0.0,
            vertical=True,
            draw=lambda: host.snapshot_child(content, snapshot),
        )
        for pill in (self.top, self.bottom):
            if pill.get_visible():
                host.snapshot_child(pill, snapshot)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared standing system column for Home and All applications."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui.nowplaying_status import NowPlayingStatus  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.status_info import StatusInfo  # noqa: E402


class ConsoleSidebar(Gtk.Widget):
    """A hard-width column; screens change to its right, never underneath."""

    def __init__(
        self, scale: Scale, status: StatusInfo, now_playing: NowPlayingStatus
    ) -> None:
        super().__init__()
        self._width = 1
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content.add_css_class("salon-console-sidebar")
        self._content.set_parent(self)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.FILL)
        self.set_vexpand(True)
        self.set_can_target(False)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self._content.set_overflow(Gtk.Overflow.HIDDEN)
        self._content.append(status)
        self._content.append(now_playing)
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self._width = scale.px(tokens.CONSOLE_WIDTH_DU)
        self._content.set_spacing(scale.px(tokens.CONSOLE_GAP_DU))
        self.queue_resize()

    def do_measure(
        self, orientation: Gtk.Orientation, for_size: int
    ) -> tuple[int, int, int, int]:
        if orientation is Gtk.Orientation.HORIZONTAL:
            return (self._width, self._width, -1, -1)
        return self._content.measure(orientation, self._width)

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        self._content.allocate(self._width, height, baseline, None)

    def do_dispose(self) -> None:
        if self._content is not None:
            self._content.unparent()
            self._content = None  # type: ignore[assignment]
        Gtk.Widget.do_dispose(self)

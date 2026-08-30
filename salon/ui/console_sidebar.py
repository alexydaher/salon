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


class ConsoleSidebar(Gtk.Box):
    """One reusable column; screens change to its right, never underneath."""

    def __init__(
        self, scale: Scale, status: StatusInfo, now_playing: NowPlayingStatus
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-console-sidebar")
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.FILL)
        self.set_vexpand(True)
        self.set_can_target(False)
        self.append(status)
        self.append(now_playing)
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_size_request(scale.px(tokens.CONSOLE_WIDTH_DU), -1)
        self.set_spacing(scale.px(tokens.CONSOLE_GAP_DU))

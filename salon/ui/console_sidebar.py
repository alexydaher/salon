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
        self._status = status
        self._card = now_playing
        self._reserved = 0
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content.add_css_class("salon-console-sidebar")
        self._content.set_parent(self)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.FILL)
        self.set_vexpand(True)
        # The rail takes presses, because the now-playing card in it is a
        # transport. It used to refuse them as a whole, which made that
        # card's click-to-toggle and every transport key dead: `pick()` at
        # the card's centre returned the overlay underneath. Nothing scrolls
        # behind the rail — the viewport host starts at its right edge — so
        # the cost of being targetable is nil. The blocks that only report
        # facts still keep their hands off the pointer.
        self.set_can_target(True)
        status.set_can_target(False)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self._content.set_overflow(Gtk.Overflow.HIDDEN)
        self._content.append(status)
        self._content.append(now_playing)
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._width = scale.px(tokens.CONSOLE_WIDTH_DU)
        self._content.set_spacing(scale.px(tokens.CONSOLE_GAP_DU))
        self.queue_resize()

    def set_bottom_reserved(self, reserved_px: int) -> None:
        """How much of the column's bottom something else has taken.

        The pairing card is pinned to the bottom of this rail and is a
        separate overlay child, so neither it nor the now-playing card can
        see the other. This is where they are told about each other.
        """
        reserved = max(0, reserved_px)
        if reserved == self._reserved:
            return
        self._reserved = reserved
        self.queue_allocate()

    def do_measure(
        self, orientation: Gtk.Orientation, for_size: int
    ) -> tuple[int, int, int, int]:
        if orientation is Gtk.Orientation.HORIZONTAL:
            return (self._width, self._width, -1, -1)
        return self._content.measure(orientation, self._width)

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        # The content is allocated the height *above* the pairing card, not
        # the rail's full height. The now-playing card's design no longer
        # grows with the number of media sources, so this is a backstop
        # rather than a policy — but it is the one that keeps a future
        # addition to the card from being drawn behind the QR code instead
        # of being noticed. It used to be a height budget handed to the card
        # on an idle, which the card answered by rebuilding itself into a
        # second, shorter arrangement; that is the thing being removed.
        self._content.allocate(self._width, self._usable_height(height), baseline, None)

    def _usable_height(self, height: int) -> int:
        if not self._reserved:
            return height
        return max(1, height - self._reserved - self._scale.px(tokens.CONSOLE_GAP_DU))

    def do_dispose(self) -> None:
        if self._content is not None:
            self._content.unparent()
            self._content = None  # type: ignore[assignment]
        Gtk.Widget.do_dispose(self)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Hard layout boundary for the standing phone-pairing card."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui.remotehint import _HOME_CARD_HEIGHT_DU, RemoteHint  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class RemoteHintHost(Gtk.Widget):
    """Keep a naturally wide URL or title inside the console rail."""

    def __init__(self, card: RemoteHint, scale: Scale) -> None:
        super().__init__()
        self._card = card
        self._card.set_parent(self)
        self._settings_layout = False
        self._width = 1
        self._height = 1
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.END)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.set_visible(False)
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._card.set_scale(scale)
        self._sync_geometry()

    def set_settings_layout(self, settings: bool) -> None:
        self._settings_layout = settings
        self._card.set_settings_layout(settings)
        self._sync_geometry()

    def _sync_geometry(self) -> None:
        if self._settings_layout:
            self._width = self._scale.px(540.0)
            self._height = self._scale.px(123.0)
            self.set_margin_start(self._scale.px(64.0))
            self.set_margin_bottom(self._scale.px(103.0))
        else:
            self._width = self._scale.px(tokens.CONSOLE_WIDTH_DU - 60.0)
            self._height = self._scale.px(_HOME_CARD_HEIGHT_DU)
            self.set_margin_start(self._scale.px(30.0))
            # Spend twelve of the rail's lower inset on the larger QR card;
            # height and margin still total 386du, so its top edge stays
            # aligned with the previous layout.
            self.set_margin_bottom(self._scale.px(22.0))
        self.queue_resize()

    def refresh(self) -> bool:
        return self._card.refresh()

    def do_measure(
        self, orientation: Gtk.Orientation, for_size: int
    ) -> tuple[int, int, int, int]:
        size = self._width if orientation is Gtk.Orientation.HORIZONTAL else self._height
        return (size, size, -1, -1)

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        self._card.allocate(self._width, self._height, baseline, None)

    def do_dispose(self) -> None:
        if self._card is not None:
            self._card.unparent()
            self._card = None  # type: ignore[assignment]
        Gtk.Widget.do_dispose(self)

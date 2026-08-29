# SPDX-License-Identifier: GPL-3.0-or-later
"""A panel that hands a URL to a phone.

A television cannot be typed into and the URL it is showing cannot be
copied. The only way to move an address off this screen is to point a
camera at it, and `core/qr.py` has been able to draw one since the pairing
screen was built.

`QrRow` is a settings row with the code inside it, rather than a new kind
of panel content: `Panel.build` returns `list[SettingsRow]`, and a special
case in the screen for "sometimes it is a widget instead" would be a
second layout path for one feature. A row that draws something is what the
tile preview does too.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.ui.qrcode import QrCode  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.context import Panel  # noqa: E402
from salon.ui.settings.settings_row import SettingsRow  # noqa: E402
from salon.ui.settings.static_rows import InfoRow  # noqa: E402

_QR_DU = 280.0


class QrRow(SettingsRow):
    """The code itself, filling a row of its own."""

    def __init__(self, text: str) -> None:
        super().__init__("")
        self.add_css_class("qr")
        self.set_can_target(False)
        self.set_focusable(False)
        self._qr = QrCode()
        self._qr.set_text(text)
        self._qr.set_halign(Gtk.Align.CENTER)
        self.set_child(self._qr)

    @property
    def selectable(self) -> bool:
        return False

    @property
    def actionable(self) -> bool:
        return False

    def set_scale(self, scale: Scale) -> None:
        size = scale.px(_QR_DU)
        self._qr.set_size(size)
        self.set_size_request(-1, size)


def qr_panel(title: str, url: str, note: str) -> Panel:
    """One address, as a picture and as text.

    Both, always: the text is what a screen reader announces and what
    somebody types when the camera will not focus, and the picture is what
    everyone else uses.
    """

    def build() -> list[SettingsRow]:
        return [
            QrRow(url),
            InfoRow("Address", url, detail=note),
        ]

    return Panel(title=title, build=build)

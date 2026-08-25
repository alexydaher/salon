# SPDX-License-Identifier: GPL-3.0-or-later
"""Visual card used by the phone-pairing screen."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.ui.qrcode import QrCode  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class PhonePairingCard(Gtk.Box):
    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-system-menu-card")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_vexpand(True)

        title = Gtk.Label(label="Use your phone as the remote")
        title.add_css_class("salon-system-menu-title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        self.append(title)

        self.qr_code = QrCode()
        self.qr_code.set_halign(Gtk.Align.CENTER)
        self.append(self.qr_code)

        self.address = Gtk.Label()
        self.address.add_css_class("salon-settings-label")
        self.address.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.append(self.address)

        self.status = Gtk.Label()
        self.status.add_css_class("salon-settings-detail")
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.append(self.status)

        self.buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.buttons.set_halign(Gtk.Align.CENTER)
        self.append(self.buttons)
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(16.0))
        self.set_size_request(scale.px(640.0), -1)
        self.buttons.set_spacing(scale.px(12.0))
        self.qr_code.set_size(scale.px(320.0))

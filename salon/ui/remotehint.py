# SPDX-License-Identifier: GPL-3.0-or-later
"""The standing offer of a remote, at the foot of the console rail.

`ui/phonepairing.py` is the full screen: a QR big enough to scan from a
sofa, opened deliberately from MENU or the top bar. This is the other half
of the same idea — the case where the user has *no way to press anything*.

With no controller plugged in and no phone talking to us, the only inputs
Salon has are a keyboard and a mouse, which is not what is in a living room.
A pairing screen you have to navigate to is no help at all then: reaching it
requires the very thing it hands out. So the code stands in the corner
permanently, small enough to ignore, and disappears the moment either a pad
or a phone turns up. Nothing else in Salon is drawn on a condition like that,
and that is the point — it is an answer to "there is nothing to press with",
not a piece of chrome.

Two consequences worth knowing before changing this:

* **It runs the pairing server.** There is no code to show otherwise. The
  card takes its own holder on `services/pairing.py`, so Settings' "Phone
  remote" toggle and this are independent reasons for the server to be up
  and neither can take the port from under the other.
* **It hides without releasing while a phone is connected.** `release()`
  stops the server outright when the last holder lets go, so dropping the
  hold the instant a phone appears would kill the session that just started.
  `HomeView._update_remote_hint` keeps the hold until there is no phone.

Clicking it opens the full pairing screen, because a mouse is the one input
someone in this state definitely has.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.services.pairing import PairingServer  # noqa: E402
from salon.ui.qrcode import QrCode  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

# A version-6 symbol plus its quiet zone is 49 modules wide, while the usual
# pairing URL produces 41 modules including that zone. 246du gives the
# usual code six pixels per module and still gives the longest supported
# code five. Keep this near module boundaries: QrCode deliberately draws
# whole-pixel modules, so most in-between sizes only add blank slack.
_HOME_QR_DU = 246.0
_SETTINGS_QR_DU = 102.0
_HOME_CARD_HEIGHT_DU = 364.0


class RemoteHint(Gtk.Box):
    """A small card: a QR code, a line saying what it is for, and the
    address underneath for anyone who would rather type it."""

    def __init__(self, scale: Scale, pairing: PairingServer, on_open: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-remote-hint")
        # The corner and nothing else. An overlay child fills the overlay
        # unless it is told otherwise, and a transparent box across the
        # whole screen swallows every click meant for a tile.
        self._pairing = pairing
        # What the QR currently encodes. `refresh` runs on a poll, and
        # re-encoding an unchanged URL a few dozen times a minute is a
        # version-6 matrix built for nothing.
        self._shown_url = ""
        self._settings_layout = False

        self._title = Gtk.Label(label="Phone remote")
        self._title.add_css_class("salon-remote-hint-title")
        self._title.set_halign(Gtk.Align.FILL)
        self._title.set_xalign(0.0)
        self._title.set_hexpand(True)
        self._title.set_max_width_chars(20)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        self.append(self._title)

        self._row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(self._row)

        self._qr = QrCode()
        self._qr.set_halign(Gtk.Align.START)
        self._row.append(self._qr)

        self._details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._details.set_valign(Gtk.Align.CENTER)
        self._row.append(self._details)
        self._instruction = self._detail_label()
        self._instruction.add_css_class("salon-remote-hint-instruction")
        self._instruction.set_label("Scan to connect")
        self._details.append(self._instruction)
        self._address = self._detail_label()
        self._address.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self._details.append(self._address)
        self._code = Gtk.Label()
        self._code.add_css_class("salon-remote-hint-code")
        self._code.set_halign(Gtk.Align.START)
        self._details.append(self._code)

        click = Gtk.GestureClick()
        click.connect("released", lambda *_: on_open())
        self.add_controller(click)
        self.set_tooltip_text("Open the pairing screen")
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Connect your phone. Scan the QR code to use it as the remote."],
        )

        self.set_scale(scale)

    @staticmethod
    def _detail_label() -> Gtk.Label:
        label = Gtk.Label()
        label.add_css_class("salon-remote-hint-detail")
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0.0)
        label.set_single_line_mode(True)
        label.set_max_width_chars(26)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        return label

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._row.set_spacing(scale.px(16.0))
        self._details.set_spacing(scale.px(2.0))
        self.set_settings_layout(self._settings_layout)

    def set_settings_layout(self, settings: bool) -> None:
        """Use the dedicated 540x123 card beneath Settings' sections pane."""
        self._settings_layout = settings
        self._repack(settings)
        self.set_spacing(self._scale.px(12.0 if settings else 4.0))
        self._qr.set_size(
            self._scale.px(_SETTINGS_QR_DU if settings else _HOME_QR_DU)
        )
        if settings:
            self.add_css_class("settings-pairing")
        else:
            self.remove_css_class("settings-pairing")

    def _repack(self, settings: bool) -> None:
        for widget in (
            self._title,
            self._row,
            self._qr,
            self._details,
            self._instruction,
            self._address,
            self._code,
        ):
            parent = widget.get_parent()
            if isinstance(parent, Gtk.Box):
                parent.remove(widget)
        if settings:
            self.set_orientation(Gtk.Orientation.HORIZONTAL)
            self._qr.set_halign(Gtk.Align.START)
            self._details.set_halign(Gtk.Align.FILL)
            self.append(self._qr)
            self.append(self._row)
            self._row.set_orientation(Gtk.Orientation.VERTICAL)
            self._row.set_hexpand(True)
            self._row.append(self._title)
            self._row.append(self._details)
            self._details.append(self._instruction)
            self._details.append(self._address)
            self._details.append(self._code)
        else:
            self.set_orientation(Gtk.Orientation.VERTICAL)
            self._qr.set_halign(Gtk.Align.CENTER)
            self._details.set_halign(Gtk.Align.CENTER)
            self.append(self._title)
            self.append(self._instruction)
            self.append(self._qr)
            self.append(self._details)
            self._details.append(self._address)
            self._details.append(self._code)
        alignment = 0.0 if settings else 0.5
        halign = Gtk.Align.START if settings else Gtk.Align.CENTER
        for label in (self._title, self._instruction, self._address, self._code):
            label.set_halign(halign)
            label.set_xalign(alignment)

    def refresh(self) -> bool:
        """Re-read the server. Returns False when there is nothing true to
        show, so the caller can hide rather than draw an empty card."""
        if self._pairing.locked:
            # Refusing to draw a code nobody can use. The full screen says
            # how to clear it; this corner has no room to explain.
            return False
        pair_url = self._pairing.pair_url
        url = self._pairing.url
        if not pair_url or url is None:
            return False
        if pair_url != self._shown_url:
            self._shown_url = pair_url
            self._qr.set_text(pair_url)
            address = str(url).removeprefix("http://").removeprefix("https://")
            self._address.set_label(address)
            self._code.set_label(f"CODE  {self._pairing.code}")
        return True

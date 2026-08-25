# SPDX-License-Identifier: GPL-3.0-or-later
"""The standing offer of a remote, in the bottom-right corner.

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

from salon.core import tokens  # noqa: E402
from salon.services.pairing import PairingServer  # noqa: E402
from salon.ui.qrcode import QrCode  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class RemoteHint(Gtk.Box):
    """A small card: a QR code, a line saying what it is for, and the
    address underneath for anyone who would rather type it."""

    def __init__(self, scale: Scale, pairing: PairingServer, on_open: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-remote-hint")
        # The corner and nothing else. An overlay child fills the overlay
        # unless it is told otherwise, and a transparent box across the
        # whole screen swallows every click meant for a tile.
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.END)
        self.set_visible(False)

        self._pairing = pairing
        # What the QR currently encodes. `refresh` runs on a poll, and
        # re-encoding an unchanged URL a few dozen times a minute is a
        # version-6 matrix built for nothing.
        self._shown_url = ""

        self._title = Gtk.Label(label="No remote connected")
        self._title.add_css_class("salon-remote-hint-title")
        self._title.set_halign(Gtk.Align.CENTER)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        self.append(self._title)

        self._qr = QrCode()
        self._qr.set_halign(Gtk.Align.CENTER)
        self.append(self._qr)

        self._detail = Gtk.Label()
        self._detail.add_css_class("salon-remote-hint-detail")
        self._detail.set_halign(Gtk.Align.CENTER)
        self._detail.set_justify(Gtk.Justification.CENTER)
        self._detail.set_wrap(True)
        self._detail.set_max_width_chars(24)
        self.append(self._detail)

        click = Gtk.GestureClick()
        click.connect("released", lambda *_: on_open())
        self.add_controller(click)
        self.set_tooltip_text("Open the pairing screen")
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["No remote connected. Scan this code to use a phone as the remote."],
        )

        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(10.0))
        margin = scale.px(
            tokens.REFERENCE_VIEWPORT_HEIGHT_PX * tokens.SAFE_AREA_DEFAULT_PERCENT / 100.0
        )
        self.set_margin_end(margin)
        # Above the detail strip, not on top of it. The strip spans the full
        # width and this card would otherwise land in its empty right-hand
        # end — which looks fine right up until a tile with a long title
        # pushes text under the QR code.
        self.set_margin_bottom(margin + scale.du(tokens.DETAIL_BAR_HEIGHT_DU))
        # A third of the pairing screen's 320du. Big enough for a phone held
        # at arm's length in front of the television — which is where anyone
        # scanning this is standing — and small enough that it is a corner
        # of the screen rather than a dialog.
        self._qr.set_size(scale.px(150.0))

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
            self._detail.set_label(f"Scan to use your phone\n{url} · {self._pairing.code}")
        return True

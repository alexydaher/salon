# SPDX-License-Identifier: GPL-3.0-or-later
"""The screen that hands the remote over to a phone.

The phone remote existed before this and was reachable from two places:
Settings → Input, and the "Use phone to type" button on the search
keyboard. Both of those are places you go for a *reason*, which made the
best input Salon has into something you had to already know about — the
Settings toggle in particular showed a URL and four digits as a subtitle,
in a row you had to be looking at.

It belongs in the system menu, which is the one thing MENU always opens
from anywhere, so this is a screen rather than a row: a QR code big enough
to scan from a sofa, the address and code underneath for anyone who would
rather type, and a live line saying whether a phone has actually turned up.

Closing it does not stop the remote. That is the whole point of putting it
here — you connect a phone once and then use it — so dismissing the screen
leaves the server running and there is an explicit "Turn it off" for the
other case. It stops on its own after five idle minutes regardless (see
`services/pairing.py`).
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")

from gi.repository import GLib, Gtk  # noqa: E402

from salon.input.actions import Action  # noqa: E402
from salon.services.pairing import PairingServer  # noqa: E402
from salon.ui import motion  # noqa: E402
from salon.ui.overlays import point_at  # noqa: E402
from salon.ui.phone_pairing_actions import PhonePairingActions  # noqa: E402
from salon.ui.phone_pairing_card import PhonePairingCard  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

_STATUS_POLL_MS = 1000

# How long "A phone is connected." stays on screen before the card gets out
# of the way. Long enough to read as confirmation that the scan worked,
# short enough that the phone's first press is not swallowed by a card
# nobody needs any more.
_CONNECTED_DWELL_MS = 1600


class PhonePairing(Gtk.Box, motion.FadesIn, PhonePairingActions):
    """Scrim, card, QR code. Navigated with LEFT/RIGHT and OK like the
    system menu it is opened from, and clickable throughout because the
    mouse is a first-class input here."""

    def __init__(
        self,
        scale: Scale,
        pairing: PairingServer,
        *,
        on_start: Callable[[], bool],
        on_close: Callable[[], None],
        on_stop: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._init_fade()
        self.add_css_class("salon-system-menu-scrim")
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_visible(False)

        self._pairing = pairing
        # Starting and stopping go back through the home screen rather than
        # straight to the server, because the server is reference counted:
        # this screen and the Settings toggle are the *same* holder, so
        # turning the remote on here shows it on in Settings, and search
        # closing its own hold can never take the port out from under it.
        self._on_start = on_start
        self._on_close = on_close
        self._on_stop = on_stop
        self._poll_id: int | None = None
        self._dismiss_id: int | None = None
        self._selected = 0
        self._hover_enabled = False
        self._confirming_stop = False

        self._card = PhonePairingCard(scale)
        self.append(self._card)
        self._qr = self._card.qr_code
        self._address = self._card.address
        self._status = self._card.status
        self._buttons = self._card.buttons

        self._rows: list[Gtk.Button] = []
        for index, (label, danger) in enumerate(
            (
                ("Done", False),
                ("Stop phone remote", True),
            )
        ):
            button = Gtk.Button(label=label)
            button.add_css_class("salon-system-menu-item")
            if danger:
                button.add_css_class("danger")
            button.connect("clicked", lambda _b, i=index: self._activate(i))
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", lambda *_, i=index: self._on_hover(i))
            button.add_controller(motion)
            self._buttons.append(button)
            self._rows.append(button)

        dismiss = Gtk.GestureClick()
        dismiss.connect("released", self._on_scrim_clicked)
        self.add_controller(dismiss)

        self.set_scale(scale)
        self._update_selection()

    # --- chrome ----------------------------------------------------------

    def set_scale(self, scale: Scale) -> None:
        self._card.set_scale(scale)

    # --- opening and closing ---------------------------------------------

    def open(self) -> bool:
        """Start the remote and show the code. False if the port was taken,
        so the caller can say so rather than showing an empty card."""
        if not self._on_start():
            return False
        self._selected = 0
        self._confirming_stop = False
        self._restore_buttons()
        self._update_selection()
        self._refresh()
        self.set_visible(True)
        self._begin_fade()
        if self._poll_id is None:
            self._poll_id = GLib.timeout_add(_STATUS_POLL_MS, self._on_poll)
        return True

    def close(self) -> None:
        """Dismiss the screen. The remote keeps running — see the module
        docstring; that is why "Turn it off" is a separate button."""
        self._stop_polling()
        self.set_visible(False)
        self._on_close()

    def _stop(self) -> None:
        self._stop_polling()
        self.set_visible(False)
        self._on_stop()

    def _stop_polling(self) -> None:
        if self._poll_id is not None:
            GLib.source_remove(self._poll_id)
            self._poll_id = None
        if self._dismiss_id is not None:
            GLib.source_remove(self._dismiss_id)
            self._dismiss_id = None

    def _on_poll(self) -> bool:
        self._refresh()
        return GLib.SOURCE_CONTINUE

    def do_unroot(self) -> None:
        self._stop_polling()
        Gtk.Box.do_unroot(self)

    # --- contents --------------------------------------------------------

    def _refresh(self) -> None:
        if self._pairing.locked:
            self._qr.set_text("")
            self._address.set_label("Too many wrong codes.")
            self._status.set_label("Restart the phone remote for a fresh code.")
            return

        url = self._pairing.url
        pair_url = self._pairing.pair_url
        self._qr.set_text(pair_url or "")
        if url is None:
            # No route to a LAN at all: an honest "this cannot work right
            # now" beats a QR code encoding an address nobody can reach.
            self._address.set_label("This machine isn't on a network.")
            self._status.set_label("Connect it to Wi-Fi or Ethernet and try again.")
            return

        self._address.set_label(f"Point a camera at the code, or open {url}")
        if self._pairing.connected:
            self._status.set_label("A phone is connected.")
            # It worked; get out of the way. Leaving the card up means the
            # phone's first press lands on this screen instead of on the
            # television, which reads as the remote not working at the exact
            # moment it started working.
            if self._dismiss_id is None:
                self._dismiss_id = GLib.timeout_add(_CONNECTED_DWELL_MS, self._on_dismiss)
        else:
            self._status.set_label(f"Typing it in? The code is {self._pairing.code}.")

    def _on_dismiss(self) -> bool:
        self._dismiss_id = None
        self.close()
        return GLib.SOURCE_REMOVE

    # --- navigation ------------------------------------------------------

    def handle_action(self, action: Action) -> None:
        if action in (Action.LEFT, Action.RIGHT):
            step = -1 if action is Action.LEFT else 1
            self._select(max(0, min(self._selected + step, len(self._rows) - 1)))
        elif action is Action.OK:
            self._rows[self._selected].emit("clicked")
        elif action is Action.BACK:
            self._cancel_stop() if self._confirming_stop else self.close()

    def set_hover_enabled(self, enabled: bool) -> None:
        """Hover only moves the selection once the pointer is genuinely in
        use — GTK sends a motion event whenever a widget maps under a
        stationary cursor, and this screen maps under one every time."""
        self._hover_enabled = enabled

    def _on_hover(self, index: int) -> None:
        if self._hover_enabled:
            self._select(index)

    def _select(self, index: int) -> None:
        if index == self._selected:
            return
        self._selected = index
        self._update_selection()

    def _update_selection(self) -> None:
        for index, row in enumerate(self._rows):
            if index == self._selected:
                row.add_css_class("selected")
            else:
                row.remove_css_class("selected")

    def _on_scrim_clicked(
        self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float
    ) -> None:
        # Only outside the card: the buttons handle their own clicks, and a
        # click on the card's padding shouldn't dismiss the screen.
        bounds = self._card.compute_bounds(self)
        if bounds[0] and bounds[1].contains_point(point_at(x, y)):
            return
        self.close()

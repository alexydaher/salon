# SPDX-License-Identifier: GPL-3.0-or-later
"""The on-screen keyboard, and the phone typing into it.

Two screens need to accept typed text — search (§6.6) and the tile editor's
text fields (§6.8) — and both need the same two things: the D-pad keyboard,
and somewhere for text arriving from a phone to land.

**This pane no longer starts the phone remote.** It used to carry a "Use
phone to type" button and its own QR code, from the days when the phone was
a keyboard you summoned for one URL. The phone is now a remote you connect
once, from the top bar, and leave connected — so a second place to turn it
on was two switches for one thing, and the one buried in a keyboard was the
one nobody would find. See DECISIONS.md 2026-08-22.

What is left is the part that was always the point: while this pane is on
screen it *claims the text sink*, so whatever the phone types goes to the
field the user is actually looking at. The claim happens on map rather than
on a button, which means connecting the phone from the top bar and then
opening search does the right thing with nothing else to press.

The sink is a single global slot on a shared server, and GTK maps the
incoming screen before it unmaps the outgoing one — so the release goes
through `release_text_sink`, which only clears the slot if this pane is
still the one holding it.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from salon.core.osk import KeyboardModel, KeyPress  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services.pairing import PairingServer  # noqa: E402
from salon.ui.osk import OnScreenKeyboard  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class KeyboardPane(Gtk.Box):
    def __init__(
        self,
        scale: Scale,
        pairing: PairingServer,
        *,
        on_key_pressed: Callable[[], None],
        on_text_changed: Callable[[], None],
        on_submit: Callable[[], None],
        cell_du: float = 64.0,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_valign(Gtk.Align.START)
        self._on_text_changed = on_text_changed
        self._on_submit = on_submit

        self.model = KeyboardModel()
        self._keyboard = OnScreenKeyboard(
            self.model, scale, on_key_pressed=on_key_pressed, cell_du=cell_du
        )
        self.append(self._keyboard)

        self._pairing = pairing
        self.set_scale(scale)

    # --- text ------------------------------------------------------------

    @property
    def text(self) -> str:
        return self.model.text

    def reset(self, text: str = "") -> None:
        self.model = KeyboardModel(text)
        self._keyboard.set_model(self.model)

    def press(self) -> KeyPress:
        result = self.model.press()
        self._keyboard.refresh()
        return result

    def move(self, action: Action) -> bool:
        moved = self.model.move(action)
        if moved:
            self._keyboard.refresh()
        return moved

    def refresh(self) -> None:
        self._keyboard.refresh()

    def insert_text(self, text: str) -> bool:
        changed = self.model.insert_text(text)
        if changed:
            self._keyboard.refresh()
            self._on_text_changed()
        return changed

    def backspace(self) -> bool:
        changed = self.model.backspace()
        if changed:
            self._keyboard.refresh()
            self._on_text_changed()
        return changed

    # --- chrome ----------------------------------------------------------

    def set_scale(self, scale: Scale) -> None:
        self._keyboard.set_scale(scale)
        self.set_spacing(scale.px(24.0))

    def set_hover_enabled(self, enabled: bool) -> None:
        self._keyboard.set_hover_enabled(enabled)

    # --- the phone -------------------------------------------------------

    def pairing_hint(self) -> str:
        """One line about the phone, or nothing.

        Only ever says something true about a remote that is already
        running: this pane cannot start one any more, and an invitation to
        press a button that isn't here would be worse than silence.
        """
        if not self._pairing.running:
            return ""
        if self._pairing.locked:
            return (
                "Phone locked — too many wrong codes. "
                "Turn the remote off and on again from the top bar."
            )
        if self._pairing.connected:
            return "Your phone can type here — use its Type tab."
        return "Phone remote is on. Open it and use the Type tab to type here."

    def _on_phone_text(self, text: str) -> None:
        """Text from the phone, including its two control characters.

        The rule lives in `KeyboardModel.apply_remote_text`, which is pure
        and tested; this is the widget half — redraw, and tell the screen
        above when the phone pressed Enter.
        """
        submit = self.model.apply_remote_text(text)
        self._keyboard.refresh()
        self._on_text_changed()
        if submit:
            self._on_submit()

    def do_map(self) -> None:
        Gtk.Box.do_map(self)
        # Unconditional, even with the server down: turning the remote on
        # while this pane is up must not need a second gesture here.
        self._pairing.set_text_sink(self._on_phone_text)

    def do_unmap(self) -> None:
        self._pairing.release_text_sink(self._on_phone_text)
        Gtk.Box.do_unmap(self)

    def do_unroot(self) -> None:
        # Belt and braces: a caller that tears the screen down without
        # unmapping it must not leave the phone typing into a dead widget.
        self._pairing.release_text_sink(self._on_phone_text)
        Gtk.Box.do_unroot(self)

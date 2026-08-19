# SPDX-License-Identifier: GPL-3.0-or-later
"""Keyboard plus phone hand-off, as one reusable block.

Two screens need to accept typed text — search (§6.6) and the tile editor's
text fields (§6.8) — and both need the same three things: the D-pad
keyboard, a way to bring a phone in when typing a URL with a controller
stops being reasonable (§6.12), and the pairing code displayed while that's
running. Bundling them here keeps the pairing lifecycle in one place: the
server starts on request and is stopped whenever the pane goes away, so
neither caller can leave an HTTP server listening on the LAN by forgetting
to tear it down.
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
        *,
        on_key_pressed: Callable[[], None],
        on_text_changed: Callable[[], None],
        cell_du: float = 64.0,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_valign(Gtk.Align.START)
        self._on_text_changed = on_text_changed

        self.model = KeyboardModel()
        self._keyboard = OnScreenKeyboard(
            self.model, scale, on_key_pressed=on_key_pressed, cell_du=cell_du
        )
        self.append(self._keyboard)

        self._phone_button = Gtk.Button(label="Use phone to type")
        self._phone_button.add_css_class("salon-search-phone")
        self._phone_button.connect("clicked", lambda *_: self.toggle_pairing())
        self.append(self._phone_button)

        # on_locked repaints the hint the moment the session is burned: the
        # phone just starts getting refused, and the only place that can be
        # explained is the screen the person is looking at.
        self._pairing = PairingServer(
            self._on_phone_text, on_locked=self._on_pairing_locked
        )
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

    # --- chrome ----------------------------------------------------------

    def set_scale(self, scale: Scale) -> None:
        self._keyboard.set_scale(scale)
        self.set_spacing(scale.px(24.0))

    def set_hover_enabled(self, enabled: bool) -> None:
        self._keyboard.set_hover_enabled(enabled)

    # --- phone pairing ---------------------------------------------------

    @property
    def pairing_running(self) -> bool:
        return self._pairing.running

    def pairing_hint(self) -> str:
        if not self._pairing.running:
            return ""
        if self._pairing.locked:
            return (
                "Phone keyboard locked — too many wrong codes. "
                "Press BACK and open search again for a new code."
            )
        url = self._pairing.url or "this machine"
        return f"On your phone, open {url} and enter code {self._pairing.code}"

    def toggle_pairing(self) -> bool:
        """Returns False if the server refused to start (port in use), so
        the caller can say so rather than leaving a dead button."""
        started = True
        if self._pairing.running:
            self._pairing.stop()
        else:
            started = self._pairing.start()
        self._phone_button.set_label(
            "Stop phone keyboard" if self._pairing.running else "Use phone to type"
        )
        self._on_text_changed()
        return started

    def stop_pairing(self) -> None:
        if self._pairing.running:
            self._pairing.stop()
            self._phone_button.set_label("Use phone to type")

    def _on_pairing_locked(self) -> None:
        self._on_text_changed()

    def _on_phone_text(self, text: str) -> None:
        self.model.set_text(self.model.text + text)
        self._on_text_changed()

    def do_unroot(self) -> None:
        # The server must never outlive the widget, even if a caller tears
        # the screen down without going through its own close path.
        self._pairing.stop()
        Gtk.Box.do_unroot(self)

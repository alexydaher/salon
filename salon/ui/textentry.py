# SPDX-License-Identifier: GPL-3.0-or-later
"""A modal text field driven by the on-screen keyboard.

The tile editor needs titles, URLs and commands typed in, and §6.8's
requirement is that none of that ever requires a text editor — so it has to
be reachable with six buttons. This is the one place text is entered
outside search, and it deliberately looks the same: same keyboard, same
phone hand-off, so there is one thing to learn rather than two.

Confirm with the keyboard's own Done key, cancel with BACK. The result is
delivered through a callback rather than returned, because the caller has
to keep running while this is open.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.input.actions import Action  # noqa: E402
from salon.services.pairing import PairingServer  # noqa: E402
from salon.ui.hardware_text import HardwareTextInput  # noqa: E402
from salon.ui.keyboardpane import KeyboardPane  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class TextEntryOverlay(Gtk.Box, HardwareTextInput):
    def __init__(self, scale: Scale, pairing: PairingServer) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-search")  # same full-bleed field as search
        self.set_visible(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._on_done: Callable[[str | None], None] | None = None

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content.set_halign(Gtk.Align.CENTER)
        self._content.set_valign(Gtk.Align.CENTER)
        # A vertical box packs children from the top and hands each one its
        # natural height, so valign alone leaves this pinned to the top edge
        # with the title clipped off the screen; it only centres once given
        # the spare space to centre within. (Same trap as the system menu.)
        self._content.set_vexpand(True)
        self.append(self._content)

        self._title_label = Gtk.Label()
        self._title_label.add_css_class("salon-search-hint")
        self._title_label.set_halign(Gtk.Align.START)
        self._content.append(self._title_label)

        # The field is a box around the label, not the label itself: a
        # bare caret floating in the middle of a black screen with no
        # chrome around it reads as a rendering fault until you type into
        # it. It also fixes where the text starts — a Gtk.Label with
        # ellipsize set fills its allocation and centres the text inside it
        # (xalign defaults to 0.5), so this label's caret sat in the middle
        # of the screen while its own prompt was at the left margin.
        self._field = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._field.add_css_class("salon-text-field")
        self._field.set_halign(Gtk.Align.START)
        self._content.append(self._field)

        self._value_label = Gtk.Label()
        self._value_label.add_css_class("salon-search-query")
        self._value_label.set_halign(Gtk.Align.START)
        self._value_label.set_xalign(0.0)
        self._value_label.set_hexpand(True)
        self._value_label.set_ellipsize(Pango.EllipsizeMode.START)
        self._field.append(self._value_label)

        self._hint_label = Gtk.Label()
        self._hint_label.add_css_class("salon-search-hint")
        self._hint_label.set_halign(Gtk.Align.START)
        self._hint_label.set_wrap(True)
        self._content.append(self._hint_label)

        self._keyboard = KeyboardPane(
            scale,
            pairing,
            on_key_pressed=self._press_key,
            on_text_changed=self._refresh,
            on_submit=self._hardware_submit,
        )
        self._content.append(self._keyboard)

        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        margin = scale.safe_margin_px
        self._content.set_spacing(scale.px(12.0))
        self._content.set_margin_start(margin)
        self._content.set_margin_end(margin)
        self._field.set_size_request(scale.px(760.0), -1)
        self._keyboard.set_scale(scale)

    def set_pointer_active(self, active: bool) -> None:
        self._keyboard.set_hover_enabled(active)

    def open(self, *, title: str, initial: str, on_done: Callable[[str | None], None]) -> None:
        self._on_done = on_done
        self._title_label.set_label(title)
        self._keyboard.reset(initial)
        self.set_visible(True)
        self._refresh()

    def current_text(self) -> str:
        """What the field holds, for the phone to mirror. See
        `core.remote.RemoteState.text`."""
        return self._keyboard.text

    def _refresh(self) -> None:
        text = self._keyboard.text
        # A visible caret, because an empty field and a field the keyboard
        # isn't pointed at look identical otherwise.
        self._value_label.set_label(f"{text}▏")
        self._hint_label.set_label(
            self._keyboard.pairing_hint() or "Press Done when finished, or BACK to cancel."
        )

    def _finish(self, value: str | None) -> None:
        callback = self._on_done
        self._on_done = None
        self.set_visible(False)
        if callback is not None:
            callback(value)

    def _press_key(self) -> None:
        result = self._keyboard.press()
        if result.done:
            self._finish(result.text)
        else:
            self._refresh()

    def handle_action(self, action: Action) -> None:
        if action is Action.BACK:
            self._finish(None)
            return
        if action is Action.OK:
            self._press_key()
            return
        self._keyboard.move(action)

    def _hardware_submit(self) -> None:
        self._finish(self._keyboard.text)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Direct hardware-keyboard text and clipboard input for TV text surfaces."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402


class HardwareTextInput:
    """Mixin for a widget carrying a ``KeyboardPane`` as ``_keyboard``."""

    def handle_keyval(self, keyval: int, state: object) -> bool:
        modifiers = Gdk.ModifierType(int(state))
        if modifiers & Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_v, Gdk.KEY_V):
            assert isinstance(self, Gtk.Widget)
            self.get_clipboard().read_text_async(None, self._on_hardware_paste)
            return True
        if keyval == Gdk.KEY_BackSpace:
            self._keyboard.backspace()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._hardware_submit()
            return True
        codepoint = Gdk.keyval_to_unicode(keyval)
        blocked = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK
        if codepoint and not modifiers & blocked:
            self._keyboard.insert_text(chr(codepoint))
            return True
        return False

    def _on_hardware_paste(self, clipboard: Gdk.Clipboard, result: object) -> None:
        try:
            text = clipboard.read_text_finish(result)
        except Exception:
            return
        if text:
            self._keyboard.insert_text(text)

    def _hardware_submit(self) -> None:
        raise NotImplementedError

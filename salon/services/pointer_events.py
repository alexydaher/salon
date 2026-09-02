# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused pointer-injection backend responsibility."""

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from salon.services.component import ServiceComponent  # noqa: E402
from salon.services.pointer_shared import (  # noqa: E402
    _AXIS_FINISH,
    _KEY_GAP_MS,
    _PRESSED,
    _RELEASED,
    BTN_LEFT,
    keysym_for,
)

_XK_TAB = 0xFF09
_XK_ALT_L = 0xFFE9
_XK_CTRL_L = 0xFFE3
_XK_A = 0x0061
_XK_DELETE = 0xFFFF


class PointerEventInjection(ServiceComponent):
    def move(self, dx: float, dy: float) -> None:
        if not self._owner.ready:
            return
        if self._owner._backend == "mutter":
            self._owner._mutter_call("NotifyPointerMotionRelative", GLib.Variant("(dd)", (dx, dy)))
            return
        self._owner._portal_notify(
            "NotifyPointerMotion",
            GLib.Variant("(oa{sv}dd)", (self._owner._session_handle, {}, dx, dy)),
        )

    def scroll(self, dx: float, dy: float) -> None:
        """Two fingers on the phone's trackpad, as a scroll wheel.

        `NotifyPointerAxis` and not `NotifyPointerAxisDiscrete`: the
        discrete call moves in whole wheel clicks, which is what a mouse
        does and not what a finger does — a page scrolled that way jumps in
        three-line steps under a gesture that is continuous. The `finish`
        option is what tells the compositor a fling has ended, so kinetic
        scrolling in GTK and in a browser stops when the fingers lift
        rather than drifting on.
        """
        if not self._owner.ready or not (dx or dy):
            return
        if self._owner._backend == "mutter":
            self._owner._mutter_call("NotifyPointerAxis", GLib.Variant("(ddu)", (dx, dy, 0)))
            return
        self._owner._portal_notify(
            "NotifyPointerAxis",
            GLib.Variant("(oa{sv}dd)", (self._owner._session_handle, {}, dx, dy)),
        )

    def scroll_finish(self) -> None:
        """Tell the compositor the fingers have left the glass."""
        if not self._owner.ready:
            return
        if self._owner._backend == "mutter":
            self._owner._mutter_call(
                "NotifyPointerAxis", GLib.Variant("(ddu)", (0.0, 0.0, _AXIS_FINISH))
            )
            return
        self._owner._portal_notify(
            "NotifyPointerAxis",
            GLib.Variant(
                "(oa{sv}dd)",
                (self._owner._session_handle, {"finish": GLib.Variant("b", True)}, 0.0, 0.0),
            ),
        )

    def press(self, button: int = BTN_LEFT) -> None:
        """Hold a button down. Pairs with `release`, and exists for the
        drag gestures — a tap that presses and releases 50ms later cannot
        move a window or select a line of text."""
        if not self._owner.ready:
            return
        self._notify_button(button, _PRESSED)

    def release(self, button: int = BTN_LEFT) -> None:
        if not self._owner.ready:
            return
        self._notify_button(button, _RELEASED)

    def type_text(self, text: str) -> bool:
        """Type `text` into whatever currently has keyboard focus.

        Not into Salon — into the *session*. This is how the phone keyboard
        reaches a search box inside a launched browser, which is the one
        place text entry on a television is genuinely unavoidable and the
        one place Salon's own on-screen keyboard cannot help.

        Returns whether there was a session to type into at all. What it
        cannot promise is that every character arrives: the compositor maps
        each keysym onto the *current* keyboard layout, so a character that
        layout cannot produce is dropped by mutter rather than by us. For a
        search box that is nearly always fine and occasionally is not.

        The keys are spaced out over the main loop rather than blasted in
        one go — see `_KEY_GAP_MS`.
        """
        if not self._owner.ready:
            return False
        keysyms = [k for k in (keysym_for(c) for c in text) if k is not None]
        if not keysyms:
            # Nothing to send. An empty string is a success (there was
            # nowhere for it to fail); a string of characters that produced
            # no keysym at all is not, and the phone should be told.
            return not text
        for index, keysym in enumerate(keysyms):
            GLib.timeout_add(index * _KEY_GAP_MS * 2, self._tap_keysym, keysym)
        return True

    def clear_field(self) -> bool:
        """Best-effort "empty the focused text box": Ctrl+A, then Delete.

        The input grant is write-only — a phone typing into a launched app
        cannot read back what is already in its field to back over it. Select
        all and delete is the one clear that a GTK entry, a Qt one, a browser
        and an Electron app all understand, and selecting nothing in an empty
        field then pressing Delete is harmless. Same modifier-held-across-a-
        tap shape as `switch_window`.
        """
        if not self._owner.ready:
            return False
        self._notify_keysym(_XK_CTRL_L, _PRESSED)
        GLib.timeout_add(_KEY_GAP_MS, self._notify_keysym, _XK_A, _PRESSED)
        GLib.timeout_add(_KEY_GAP_MS * 2, self._notify_keysym, _XK_A, _RELEASED)
        GLib.timeout_add(_KEY_GAP_MS * 3, self._notify_keysym, _XK_CTRL_L, _RELEASED)
        GLib.timeout_add(_KEY_GAP_MS * 4, self._tap_keysym, _XK_DELETE)
        return True

    def switch_window(self) -> bool:
        """Inject Alt+Tab while preserving the modifier across the tap.

        A Wayland client cannot raise itself without an activation token,
        and a phone press arriving over HTTP has no such token. The existing
        RemoteDesktop grant can, however, invoke the compositor's own MRU
        switcher. A launched app is the window that most recently covered
        Salon, so one switch returns to Salon without ending that process.
        """
        if not self._owner.ready:
            return False
        self._notify_keysym(_XK_ALT_L, _PRESSED)
        GLib.timeout_add(_KEY_GAP_MS, self._notify_keysym, _XK_TAB, _PRESSED)
        GLib.timeout_add(_KEY_GAP_MS * 2, self._notify_keysym, _XK_TAB, _RELEASED)
        GLib.timeout_add(_KEY_GAP_MS * 3, self._notify_keysym, _XK_ALT_L, _RELEASED)
        return True

    def _tap_keysym(self, keysym: int) -> bool:
        self._notify_keysym(keysym, _PRESSED)
        GLib.timeout_add(_KEY_GAP_MS, self._notify_keysym, keysym, _RELEASED)
        return GLib.SOURCE_REMOVE

    def _notify_keysym(self, keysym: int, state: int) -> bool:
        if self._owner._backend == "mutter":
            self._owner._mutter_call(
                "NotifyKeyboardKeysym", GLib.Variant("(ub)", (keysym, bool(state)))
            )
            return GLib.SOURCE_REMOVE
        if self._owner._session_handle is not None:
            self._owner._portal_notify(
                "NotifyKeyboardKeysym",
                GLib.Variant("(oa{sv}iu)", (self._owner._session_handle, {}, keysym, state)),
            )
        return GLib.SOURCE_REMOVE

    def click(self, button: int = BTN_LEFT) -> None:
        if not self._owner.ready:
            return
        self._notify_button(button, _PRESSED)
        GLib.timeout_add(50, self._notify_button, button, _RELEASED)

    def _notify_button(self, button: int, state: int) -> bool:
        if self._owner._backend == "mutter":
            self._owner._mutter_call(
                "NotifyPointerButton", GLib.Variant("(ib)", (button, bool(state)))
            )
            return GLib.SOURCE_REMOVE
        if self._owner._session_handle is not None:
            self._owner._portal_notify(
                "NotifyPointerButton",
                GLib.Variant("(oa{sv}iu)", (self._owner._session_handle, {}, button, state)),
            )
        return GLib.SOURCE_REMOVE

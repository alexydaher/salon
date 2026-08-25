# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused phone-remote server component."""

from __future__ import annotations

from salon.services.phone_remote_delivery import (
    _deliver,
    _deliver_button,
    _deliver_motion,
    _deliver_transport,
    _finite,
    _notify,
)
from salon.services.phone_remote_shared import (
    ACTION_NAMES,
    POINTER_BUTTONS,
    TRANSPORT_NAMES,
    GLib,
    PhoneRemoteComponent,
    Soup,
)


class PhoneRemoteInput(PhoneRemoteComponent):
    def _handle_type(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        fields = self._owner._authorize(message)
        if fields is None:
            return
        text = str(fields.get("text", ""))
        sink = self._owner._text_sink
        if sink is not None:
            GLib.idle_add(lambda: _deliver(sink, text))
            self._owner._ok(message)
            return
        # Nothing in Salon wants this, which usually means a launched
        # application is in front. Type into *that* instead, through the
        # same RemoteDesktop grant the trackpad uses — a phone keyboard
        # that only works on Salon's own screens is a phone keyboard that
        # stops working exactly when a search box appears in Netflix.
        if self._owner._on_remote_text is not None and self._owner._on_remote_text(text):
            self._owner._ok(message)
            return
        # Said plainly rather than swallowed: silence here looks exactly
        # like a broken connection.
        self._owner._refuse(
            message,
            Soup.Status.CONFLICT,
            "Nothing on the TV is asking for text, and Salon isn't allowed "
            "to type into other apps. Turn on Settings \u2192 Input \u2192 "
            "Gamepad cursor to let it.",
        )

    def _handle_action(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        fields = self._owner._authorize(message)
        if fields is None:
            return
        name = str(fields.get("action", ""))
        if self._owner._on_action is None or name not in ACTION_NAMES:
            # An unknown name is a bad request, not a silent no-op: the page
            # and this set are edited in different places and drifting apart
            # would otherwise show up as buttons that do nothing.
            self._owner._refuse(message, Soup.Status.BAD_REQUEST, "Unknown button.")
            return
        callback = self._owner._on_action
        GLib.idle_add(lambda: _deliver(callback, name))
        self._owner._ok(message)

    def _handle_launch(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Open a tile by id. Same launch path as a press on the television —
        the phone is not a second way in, it is a second remote."""
        fields = self._owner._authorize(message)
        if fields is None:
            return
        tile_id = str(fields.get("id", ""))
        if self._owner._on_launch is None or not self._owner._may_touch(tile_id):
            self._owner._refuse(message, Soup.Status.NOT_FOUND, "That is not on the TV any more.")
            return
        callback = self._owner._on_launch
        GLib.idle_add(lambda: _deliver(callback, tile_id))
        self._owner._ok(message)

    def _handle_transport(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Play/pause, next, previous — for the player the phone can see."""
        fields = self._owner._authorize(message)
        if fields is None:
            return
        what = str(fields.get("what", ""))
        if self._owner._on_transport is None or what not in TRANSPORT_NAMES:
            self._owner._refuse(message, Soup.Status.BAD_REQUEST, "Unknown transport control.")
            return
        callback = self._owner._on_transport
        GLib.idle_add(lambda: _deliver_transport(callback, what))
        self._owner._ok(message)

    def _handle_pointer(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        fields = self._owner._authorize(message)
        if fields is None:
            return
        if self._owner._pointer_ready is not None and not self._owner._pointer_ready():
            # The trackpad needs the desktop's RemoteDesktop grant, and
            # there are ordinary reasons not to have it — the permission was
            # declined, or the portal is still handshaking. A finger sliding
            # on a surface that answers 200 and moves nothing is the worst
            # of the available outcomes.
            self._owner._refuse(
                message,
                Soup.Status.CONFLICT,
                "Salon isn't allowed to move the pointer. Turn on "
                "Settings \u2192 Input \u2192 Gamepad cursor, and allow the "
                "desktop's permission request.",
            )
            return
        # Ordered by how often each arrives, which is also the order the
        # gestures on the page fire in: motion during a drag, then the
        # scroll of a two-finger drag, then the once-per-gesture events.
        move = self._owner._on_pointer
        if move is not None:
            dx = _finite(fields.get("dx"))
            dy = _finite(fields.get("dy"))
            if dx or dy:
                GLib.idle_add(lambda: _deliver_motion(move, dx, dy))
        scroll = self._owner._on_scroll
        if scroll is not None:
            sx = _finite(fields.get("sx"))
            sy = _finite(fields.get("sy"))
            if sx or sy:
                GLib.idle_add(lambda: _deliver_motion(scroll, sx, sy))
        if fields.get("scrollEnd") and self._owner._on_scroll_end is not None:
            finish = self._owner._on_scroll_end
            GLib.idle_add(_notify, finish)
        # `button` names which one; a bare `click` stays "left" so an older
        # page — one a phone kept in its cache — goes on working.
        button = str(fields.get("button", "") or "left")
        if button not in POINTER_BUTTONS:
            self._owner._refuse(message, Soup.Status.BAD_REQUEST, "Unknown mouse button.")
            return
        if fields.get("click"):
            if button == "left" and self._owner._on_click is not None:
                click = self._owner._on_click
                GLib.idle_add(_notify, click)
            elif self._owner._on_button is not None:
                press = self._owner._on_button
                GLib.idle_add(lambda: _deliver_button(press, button, "click"))
            self._owner._ok(message)
            return
        # Press and release as separate events: this is what lets a
        # double-tap-and-drag on the phone move a window or select text,
        # which a tap that releases itself 50ms later can never do.
        held = str(fields.get("hold", ""))
        if held in ("down", "up") and self._owner._on_button is not None:
            hold = self._owner._on_button
            GLib.idle_add(lambda: _deliver_button(hold, button, held))
        self._owner._ok(message)

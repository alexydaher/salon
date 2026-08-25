# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused pointer-injection backend responsibility."""

from salon.services.component import ServiceComponent
from salon.services.pointer_shared import *


class MutterPointerBackend(ServiceComponent):
    def _start_mutter(self) -> bool:
        """CreateSession + Start against gnome-shell. True if input can be
        injected when this returns.

        Deliberately synchronous. It is two round trips to a process that
        answers in a few milliseconds, and making it async would mean
        carrying a second half-built-session state through the portal
        fallback for no gain. A compositor that is not mutter simply has no
        such bus name and `call_sync` fails immediately.
        """
        try:
            result = self._connection.call_sync(
                _MUTTER_BUS,
                _MUTTER_PATH,
                _MUTTER_IFACE,
                "CreateSession",
                None,
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE,
                _MUTTER_TIMEOUT_MS,
                None,
            )
            session = str(result.unpack()[0])
            self._connection.call_sync(
                _MUTTER_BUS,
                session,
                _MUTTER_SESSION_IFACE,
                "Start",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                _MUTTER_TIMEOUT_MS,
                None,
            )
        except GLib.Error as error:
            # Not a failure worth a user-facing word: on a non-GNOME
            # compositor this is the expected answer, and the portal is
            # about to be tried.
            print(f"[pointer] mutter's RemoteDesktop is not available ({error.message}).")
            return False
        self._mutter_session = session
        self._session_handle = session
        # A session dies with the compositor. gnome-shell restarting would
        # otherwise leave `ready` True over a session that no longer exists,
        # and every press after that would go nowhere in silence.
        self._closed_sub = self._connection.signal_subscribe(
            _MUTTER_BUS,
            _MUTTER_SESSION_IFACE,
            "Closed",
            session,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_mutter_closed,
        )
        return True

    def _on_mutter_closed(self, *_args: object) -> None:
        print("[pointer] mutter closed the remote-desktop session.")
        self._fail()

    def _mutter_call(self, method: str, args: GLib.Variant | None) -> None:
        if self._mutter_session is None:
            return
        self._connection.call(
            _MUTTER_BUS,
            self._mutter_session,
            _MUTTER_SESSION_IFACE,
            method,
            args,
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )

    def _release_mutter(self) -> None:
        if self._closed_sub is not None:
            self._connection.signal_unsubscribe(self._closed_sub)
            self._closed_sub = None
        self._mutter_session = None

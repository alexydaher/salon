# SPDX-License-Identifier: GPL-3.0-or-later
"""Compatibility facade for pointer injection backends."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.core import sandbox  # noqa: E402
from salon.services.pointer_events import PointerEventInjection  # noqa: E402
from salon.services.pointer_mutter import MutterPointerBackend  # noqa: E402
from salon.services.pointer_portal import RemoteDesktopPortalBackend  # noqa: E402
from salon.services.pointer_portal_calls import PortalCalls  # noqa: E402
from salon.services.pointer_shared import (  # noqa: E402
    BACKEND_AUTO,
    BACKEND_MUTTER,
    BACKEND_PORTAL,
    BTN_LEFT,
    BUTTONS,
    keysym_for,
    onscreen_keyboard_available,
    onscreen_keyboard_enabled,
    set_onscreen_keyboard_enabled,
)

__all__ = [
    "BACKEND_AUTO",
    "BACKEND_MUTTER",
    "BACKEND_PORTAL",
    "BUTTONS",
    "PointerInjector",
    "keysym_for",
    "onscreen_keyboard_available",
    "onscreen_keyboard_enabled",
    "set_onscreen_keyboard_enabled",
]


class PointerInjector:
    """Lazily negotiates a RemoteDesktop portal session, then injects
    relative pointer motion and clicks system-wide. start() is idempotent
    and safe to call every time pointer mode is entered.
    """

    def __init__(
        self,
        on_ready: Callable[[bool], None] | None = None,
        *,
        load_restore_token: Callable[[], str] | None = None,
        save_restore_token: Callable[[str], None] | None = None,
        backend: str = BACKEND_AUTO,
    ) -> None:
        try:
            self._connection: Gio.DBusConnection | None = Gio.bus_get_sync(
                Gio.BusType.SESSION, None
            )
        except (GLib.Error, OSError, TypeError, ValueError) as error:
            print(f"[pointer] Session bus is unavailable ({error}).")
            self._connection = None
        self._session_handle: str | None = None
        self._started = False
        self._preference = backend
        # "" until something has actually started; then "mutter" or "portal".
        self._backend = ""
        self._mutter_session: str | None = None
        self._closed_sub: int | None = None
        self._parent_window = ""
        self._starting = False
        self._timeout_id: int | None = None
        self._on_ready = on_ready
        self._load_restore_token = load_restore_token
        self._save_restore_token = save_restore_token
        self._used_restore_token = ""
        self._pending_request_subscriptions: set[int] = set()
        self._portal_closed_subscription: int | None = None
        self._failure_reported = False

        self._mutter = MutterPointerBackend(self)
        self._portal = RemoteDesktopPortalBackend(self)
        self._portal_calls = PortalCalls(self)
        self._events = PointerEventInjection(self)

    def move(self, dx: float, dy: float) -> None:
        self._events.move(dx, dy)

    def scroll(self, dx: float, dy: float) -> None:
        self._events.scroll(dx, dy)

    def scroll_finish(self) -> None:
        self._events.scroll_finish()

    def press(self, button: int = BTN_LEFT) -> None:
        self._events.press(button)

    def release(self, button: int = BTN_LEFT) -> None:
        self._events.release(button)

    def click(self, button: int = BTN_LEFT) -> None:
        self._events.click(button)

    def type_text(self, value: str) -> bool:
        return self._events.type_text(value)

    def clear_field(self) -> bool:
        return self._events.clear_field()

    def switch_window(self) -> bool:
        """Ask the compositor for its most-recent-window switch."""
        return self._events.switch_window()

    def _start_mutter(self) -> bool:
        return self._mutter._start_mutter()  # noqa: SLF001

    def _mutter_call(self, method: str, args: GLib.Variant | None) -> None:
        self._mutter._mutter_call(method, args)  # noqa: SLF001

    def _release_mutter(self) -> None:
        self._mutter._release_mutter()  # noqa: SLF001

    def _create_session(self) -> None:
        self._portal._create_session()  # noqa: SLF001

    def _portal_notify(self, method: str, parameters: GLib.Variant) -> None:
        self._portal_calls._portal_notify(method, parameters)  # noqa: SLF001

    def _portal_sync(
        self,
        interface: str,
        method: str,
        parameters: GLib.Variant | None,
        reply_type: GLib.VariantType | None,
    ) -> GLib.Variant | None:
        return self._portal_calls._portal_sync(  # noqa: SLF001
            interface, method, parameters, reply_type
        )

    def _watch_request(
        self, request_path: str, on_response: Callable[[int, dict[str, object]], None]
    ) -> None:
        self._portal_calls._watch_request(request_path, on_response)  # noqa: SLF001

    @property
    def ready(self) -> bool:
        """Whether input can actually be injected *right now*.

        Deliberately not "is there a session handle": the portal hands one
        back at CreateSession, which is three round trips and possibly a
        consent dialog before Start says yes. Taking the handle as the
        answer meant `ready` was True through that whole window — so the
        phone's keyboard tab said "typing goes to whatever is open on the
        television", `/type` answered 200, and mutter dropped every keysym
        on the floor because the session had never been started. A grant
        that is still being asked for is not a grant.
        """
        return self._session_handle is not None and self._started

    @property
    def backend(self) -> str:
        """Which route is actually carrying input: "mutter", "portal", or ""
        for "nothing is running". Settings shows this, because "remote
        control is working" and "the desktop was asked for permission" are
        different facts and only one of them is visible on screen."""
        return self._backend

    def start(self, parent_window: str = "") -> None:
        """Begin the portal handshake. parent_window should be a handle from
        Gdk export_handle (e.g. "wayland:HANDLE") so the consent dialog is
        properly anchored to Salon's window instead of appearing unparented
        — xdg-desktop-portal logs "Failed to associate portal window with
        parent window" and the dialog may not be reliably visible without
        it. Empty string is legal (no parent) but not recommended."""
        if self._session_handle is not None or self._starting:
            return
        self._failure_reported = False
        if self._connection is None:
            self._fail()
            return
        self._starting = True
        self._parent_window = parent_window
        if (
            self._preference != BACKEND_PORTAL
            and sandbox.capabilities().mutter_injection
            and self._start_mutter()
        ):
            self._starting = False
            self._backend = "mutter"
            self._started = True
            # Worth a line in the journal: which route carried input is
            # invisible from the screen, and the two differ in exactly the
            # thing anyone debugging this cares about — whether a consent
            # dialog is about to appear.
            print("[pointer] Injecting input via mutter directly; no consent dialog needed.")
            if self._on_ready is not None:
                self._on_ready(True)
            return
        if self._preference == BACKEND_MUTTER:
            # Explicitly asked for the one route that just failed. Falling
            # through to the portal here would put the dialog on screen
            # that this setting exists to avoid.
            print("[pointer] input-injection=mutter, but mutter's interface did not answer.")
            self._starting = False
            self._fail()
            return
        self._timeout_id = GLib.timeout_add_seconds(20, self._on_timeout)
        self._create_session()

    def _on_timeout(self) -> bool:
        print(
            "[pointer] RemoteDesktop request timed out after 20s — the consent "
            "dialog was probably left unanswered."
        )
        self._timeout_id = None
        self._fail()
        return GLib.SOURCE_REMOVE

    def _clear_timeout(self) -> None:
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def stop(self) -> None:
        """Give the grant back. Only meaningful for the mutter route — the
        portal session is torn down with the bus connection, and its grant
        is persisted on purpose."""
        if self._backend == "mutter" and self._mutter_session is not None:
            self._mutter_call("Stop", None)
        self._release_mutter()
        self._started = False
        self._session_handle = None
        self._backend = ""

    def _fail(self) -> None:
        """Collapse every backend failure into one clean state transition."""
        self._portal_calls.cleanup_subscriptions()
        self._clear_timeout()
        self._starting = False
        self._started = False
        self._session_handle = None
        self._backend = ""
        try:
            self._release_mutter()
        except (GLib.Error, TypeError, ValueError) as error:
            print(f"[pointer] Backend cleanup failed: {error}.")
        if self._on_ready is not None and not self._failure_reported:
            self._failure_reported = True
            self._on_ready(False)

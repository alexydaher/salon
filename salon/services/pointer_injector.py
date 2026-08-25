# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Compatibility facade for pointer injection backends."""

from __future__ import annotations

from typing import Any

from salon.services.component import component_attribute
from salon.services.pointer_events import PointerEventInjection
from salon.services.pointer_mutter import MutterPointerBackend
from salon.services.pointer_portal import RemoteDesktopPortalBackend
from salon.services.pointer_shared import *


class PointerInjector:
    """Lazily negotiates a RemoteDesktop portal session, then injects
    relative pointer motion and clicks system-wide.

    start() is idempotent and safe to call repeatedly (e.g. every time
    pointer mode is entered) — it only does the handshake once.
    """

    def __init__(
        self,
        on_ready: Callable[[bool], None] | None = None,
        *,
        load_restore_token: Callable[[], str] | None = None,
        save_restore_token: Callable[[str], None] | None = None,
        backend: str = BACKEND_AUTO,
    ) -> None:
        self._connection: Gio.DBusConnection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
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

        self._components = (
            MutterPointerBackend(self),
            RemoteDesktopPortalBackend(self),
            PointerEventInjection(self),
        )

    def __getattr__(self, name: str) -> Any:
        return component_attribute(self._components, name)

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
        self._starting = True
        self._parent_window = parent_window
        if self._preference != BACKEND_PORTAL and self._start_mutter():
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

    # --- mutter's own interface ---------------------------------------

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

    # --- portal handshake ---------------------------------------------

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

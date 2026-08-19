# SPDX-License-Identifier: GPL-3.0-or-later
"""Gamepad-driven pointer/click injection via the RemoteDesktop portal.

Wayland forbids one app from injecting input into another app's window
directly (unlike X11's XTestFakeInput), so this goes through
org.freedesktop.portal.RemoteDesktop instead — the sanctioned, sandbox-safe
mechanism GNOME Remote Desktop and similar tools use.

**The consent dialog is shown once, ever.** RemoteDesktop portal version 2
added `persist_mode` and `restore_token` (the same mechanism screen-sharing
tools use so they don't re-prompt every call). Salon asks for
`PERSIST_EXPLICITLY_REVOKED`, keeps the token the portal hands back, and
passes it to `SelectDevices` next time; the portal then restores the grant
silently. Without this the dialog appears on *every* browser launch, landing
on top of whatever the user just opened.

The token is deliberately stored by the caller (GSettings) rather than here:
this class holds no policy, and clearing that key is how the grant is given
back. A token the portal no longer honours is dropped on failure so the next
attempt starts clean rather than retrying a dead grant forever.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

_BUS_NAME = "org.freedesktop.portal.Desktop"
_OBJECT_PATH = "/org/freedesktop/portal/desktop"
_RD_IFACE = "org.freedesktop.portal.RemoteDesktop"
_REQUEST_IFACE = "org.freedesktop.portal.Request"

_DEVICE_POINTER = 1
_DEVICE_KEYBOARD = 2

# org.freedesktop.portal.RemoteDesktop v2 persist modes.
_PERSIST_NONE = 0
_PERSIST_WHILE_RUNNING = 1
_PERSIST_EXPLICITLY_REVOKED = 2

# persist_mode/restore_token only exist from version 2 of the interface.
# On an older portal both are ignored and the dialog appears every time,
# which is the pre-existing behaviour rather than a failure.
_RD_VERSION_WITH_PERSIST = 2

BTN_LEFT = 0x110

_PRESSED = 1
_RELEASED = 0


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
    ) -> None:
        self._connection: Gio.DBusConnection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._session_handle: str | None = None
        self._parent_window = ""
        self._starting = False
        self._timeout_id: int | None = None
        self._on_ready = on_ready
        self._load_restore_token = load_restore_token
        self._save_restore_token = save_restore_token
        self._used_restore_token = ""

    @property
    def ready(self) -> bool:
        return self._session_handle is not None

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

    def move(self, dx: float, dy: float) -> None:
        if self._session_handle is None:
            return
        self._connection.call(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "NotifyPointerMotion",
            GLib.Variant("(oa{sv}dd)", (self._session_handle, {}, dx, dy)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )

    def click(self, button: int = BTN_LEFT) -> None:
        if self._session_handle is None:
            return
        self._notify_button(button, _PRESSED)
        GLib.timeout_add(50, self._notify_button, button, _RELEASED)

    def _notify_button(self, button: int, state: int) -> bool:
        if self._session_handle is not None:
            self._connection.call(
                _BUS_NAME,
                _OBJECT_PATH,
                _RD_IFACE,
                "NotifyPointerButton",
                GLib.Variant("(oa{sv}iu)", (self._session_handle, {}, button, state)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )
        return GLib.SOURCE_REMOVE

    # --- portal handshake ---------------------------------------------

    def _sender_token(self) -> str:
        unique = self._connection.get_unique_name()
        return unique.lstrip(":").replace(".", "_")

    def _new_token(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _watch_request(
        self, request_path: str, on_response: Callable[[int, dict[str, object]], None]
    ) -> None:
        sub_id_holder: list[int] = []

        def handler(
            connection: Gio.DBusConnection,
            sender: str,
            path: str,
            iface: str,
            signal: str,
            params: GLib.Variant,
        ) -> None:
            code, results = params.unpack()
            self._connection.signal_unsubscribe(sub_id_holder[0])
            on_response(code, results)

        sub_id = self._connection.signal_subscribe(
            _BUS_NAME,
            _REQUEST_IFACE,
            "Response",
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            handler,
        )
        sub_id_holder.append(sub_id)

    def _create_session(self) -> None:
        session_token = self._new_token("salon_rd")
        handle_token = self._new_token("salon_req")
        request_path = (
            f"/org/freedesktop/portal/desktop/request/{self._sender_token()}/{handle_token}"
        )
        self._watch_request(request_path, self._on_session_response(session_token))
        self._connection.call_sync(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "CreateSession",
            GLib.Variant(
                "(a{sv})",
                (
                    {
                        "session_handle_token": GLib.Variant("s", session_token),
                        "handle_token": GLib.Variant("s", handle_token),
                    },
                ),
            ),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_session_response(
        self, session_token: str
    ) -> Callable[[int, dict[str, object]], None]:
        def handler(code: int, results: dict[str, object]) -> None:
            if code != 0:
                self._fail()
                return
            # params.unpack() (in _watch_request) already deep-unpacks the
            # a{sv} dict, so values here are plain Python objects already —
            # not GLib.Variant, despite the a{sv} signature suggesting it.
            handle = results.get("session_handle")
            self._session_handle = handle if isinstance(handle, str) else session_token
            self._select_devices()

        return handler

    def _portal_version(self) -> int:
        try:
            result = self._connection.call_sync(
                _BUS_NAME,
                _OBJECT_PATH,
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", (_RD_IFACE, "version")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except GLib.Error:
            return 1
        return int(result.unpack()[0])

    def _select_devices(self) -> None:
        assert self._session_handle is not None
        handle_token = self._new_token("salon_req")
        request_path = (
            f"/org/freedesktop/portal/desktop/request/{self._sender_token()}/{handle_token}"
        )
        self._watch_request(request_path, self._on_devices_selected)
        options = {
            "types": GLib.Variant("u", _DEVICE_POINTER | _DEVICE_KEYBOARD),
            "handle_token": GLib.Variant("s", handle_token),
        }
        if self._portal_version() >= _RD_VERSION_WITH_PERSIST:
            options["persist_mode"] = GLib.Variant("u", _PERSIST_EXPLICITLY_REVOKED)
            token = self._load_restore_token() if self._load_restore_token else ""
            self._used_restore_token = token
            if token:
                options["restore_token"] = GLib.Variant("s", token)
        self._connection.call_sync(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "SelectDevices",
            GLib.Variant("(oa{sv})", (self._session_handle, options)),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_devices_selected(self, code: int, results: dict[str, object]) -> None:
        if code != 0:
            print(f"[pointer] SelectDevices was denied or failed (code={code}).")
            self._fail()
            return
        self._start_session()

    def _start_session(self) -> None:
        assert self._session_handle is not None
        handle_token = self._new_token("salon_req")
        request_path = (
            f"/org/freedesktop/portal/desktop/request/{self._sender_token()}/{handle_token}"
        )
        self._watch_request(request_path, self._on_started)
        self._connection.call_sync(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "Start",
            GLib.Variant(
                "(osa{sv})",
                (
                    self._session_handle,
                    self._parent_window,
                    {"handle_token": GLib.Variant("s", handle_token)},
                ),
            ),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_started(self, code: int, results: dict[str, object]) -> None:
        self._starting = False
        self._clear_timeout()
        if code != 0:
            print(f"[pointer] Start was denied or failed (code={code}) — consent not granted?")
            # A token the portal has stopped honouring (revoked in system
            # settings, or invalidated by a compositor restart) would
            # otherwise be retried forever, and the retry is silent — the
            # user would just see the pointer never work again.
            self._forget_restore_token()
            self._fail()
            return
        self._store_restore_token(results.get("restore_token"))
        if self._on_ready is not None:
            self._on_ready(True)

    def _store_restore_token(self, token: object) -> None:
        if self._save_restore_token is None:
            return
        # The portal issues a *fresh* token each time and the old one stops
        # working, so this has to be written on every successful start, not
        # only the first.
        if isinstance(token, str) and token and token != self._used_restore_token:
            self._save_restore_token(token)

    def _forget_restore_token(self) -> None:
        if self._save_restore_token is not None and self._used_restore_token:
            self._save_restore_token("")
        self._used_restore_token = ""

    def _fail(self) -> None:
        self._clear_timeout()
        self._starting = False
        self._session_handle = None
        if self._on_ready is not None:
            self._on_ready(False)


def set_onscreen_keyboard_enabled(enabled: bool) -> None:
    """Toggle GNOME's built-in accessibility on-screen keyboard.

    We deliberately don't render our own OSK overlay: Salon can't force
    itself above another app's Wayland window, so a custom overlay
    wouldn't reliably show up over Chrome/Netflix/etc. GNOME's a11y
    keyboard is a shell-level surface and isn't bound by that limit — the
    gamepad-driven cursor from PointerInjector can then click its keys
    like a real mouse.
    """
    settings = Gio.Settings.new("org.gnome.desktop.a11y.applications")
    settings.set_boolean("screen-keyboard-enabled", enabled)


def onscreen_keyboard_enabled() -> bool:
    settings = Gio.Settings.new("org.gnome.desktop.a11y.applications")
    return bool(settings.get_boolean("screen-keyboard-enabled"))

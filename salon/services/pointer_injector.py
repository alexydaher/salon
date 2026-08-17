"""Gamepad-driven pointer/click injection via the RemoteDesktop portal.

Wayland forbids one app from injecting input into another app's window
directly (unlike X11's XTestFakeInput), so this goes through
org.freedesktop.portal.RemoteDesktop instead — the sanctioned, sandbox-safe
mechanism GNOME Remote Desktop and similar tools use. The user sees a
one-time system consent dialog the first time a session starts per process
lifetime; after that this reuses the same session.
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

BTN_LEFT = 0x110

_PRESSED = 1
_RELEASED = 0


class PointerInjector:
    """Lazily negotiates a RemoteDesktop portal session, then injects
    relative pointer motion and clicks system-wide.

    start() is idempotent and safe to call repeatedly (e.g. every time
    pointer mode is entered) — it only does the handshake once.
    """

    def __init__(self, on_ready: Callable[[bool], None] | None = None) -> None:
        self._connection: Gio.DBusConnection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._session_handle: str | None = None
        self._starting = False
        self._on_ready = on_ready

    @property
    def ready(self) -> bool:
        return self._session_handle is not None

    def start(self) -> None:
        if self._session_handle is not None or self._starting:
            return
        self._starting = True
        self._create_session()

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

    def _select_devices(self) -> None:
        assert self._session_handle is not None
        handle_token = self._new_token("salon_req")
        request_path = (
            f"/org/freedesktop/portal/desktop/request/{self._sender_token()}/{handle_token}"
        )
        self._watch_request(request_path, self._on_devices_selected)
        self._connection.call_sync(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "SelectDevices",
            GLib.Variant(
                "(oa{sv})",
                (
                    self._session_handle,
                    {
                        "types": GLib.Variant("u", _DEVICE_POINTER | _DEVICE_KEYBOARD),
                        "handle_token": GLib.Variant("s", handle_token),
                    },
                ),
            ),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_devices_selected(self, code: int, results: dict[str, object]) -> None:
        if code != 0:
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
                (self._session_handle, "", {"handle_token": GLib.Variant("s", handle_token)}),
            ),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_started(self, code: int, results: dict[str, object]) -> None:
        self._starting = False
        if code != 0:
            self._fail()
            return
        if self._on_ready is not None:
            self._on_ready(True)

    def _fail(self) -> None:
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

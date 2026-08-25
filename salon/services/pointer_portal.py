# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused pointer-injection backend responsibility."""

from salon.services.component import ServiceComponent
from salon.services.pointer_shared import *


class RemoteDesktopPortalBackend(ServiceComponent):
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

    def _on_session_response(self, session_token: str) -> Callable[[int, dict[str, object]], None]:
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
        self._started = True
        self._backend = "portal"
        print("[pointer] Injecting input via the desktop portal.")
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
        self._started = False
        self._session_handle = None
        self._backend = ""
        self._release_mutter()
        if self._on_ready is not None:
            self._on_ready(False)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused pointer-injection backend responsibility."""

import uuid
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.services.component import ServiceComponent  # noqa: E402
from salon.services.pointer_shared import (  # noqa: E402
    _BUS_NAME,
    _DEVICE_KEYBOARD,
    _DEVICE_POINTER,
    _PERSIST_EXPLICITLY_REVOKED,
    _RD_IFACE,
    _RD_VERSION_WITH_PERSIST,
    _SESSION_IFACE,
)


class RemoteDesktopPortalBackend(ServiceComponent):
    def _sender_token(self) -> str | None:
        if self._owner._connection is None:
            self._owner._fail()
            return None
        try:
            unique = self._owner._connection.get_unique_name()
            if not isinstance(unique, str) or not unique:
                raise ValueError("session bus has no unique name")
            return unique.lstrip(":").replace(".", "_")
        except (GLib.Error, TypeError, ValueError) as error:
            print(f"[pointer] Portal sender-name lookup failed: {error}.")
            self._owner._fail()
            return None

    def _new_token(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _create_session(self) -> None:
        session_token = self._new_token("salon_rd")
        handle_token = self._new_token("salon_req")
        sender = self._sender_token()
        if sender is None:
            return
        request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{handle_token}"
        self._owner._watch_request(request_path, self._on_session_response(session_token))
        self._owner._portal_sync(
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
        )

    def _on_session_response(self, session_token: str) -> Callable[[int, dict[str, object]], None]:
        def handler(code: int, results: dict[str, object]) -> None:
            if code != 0:
                self._owner._fail()
                return
            # params.unpack() (in _watch_request) already deep-unpacks the
            # a{sv} dict, so values here are plain Python objects already —
            # not GLib.Variant, despite the a{sv} signature suggesting it.
            handle = results.get("session_handle")
            if not isinstance(handle, str) or not handle.startswith("/"):
                print("[pointer] CreateSession returned no valid session handle.")
                self._owner._fail()
                return
            self._owner._session_handle = handle
            if self._owner._connection is None:
                self._owner._fail()
                return
            try:
                self._owner._portal_closed_subscription = self._owner._connection.signal_subscribe(
                    _BUS_NAME,
                    _SESSION_IFACE,
                    "Closed",
                    handle,
                    None,
                    Gio.DBusSignalFlags.NONE,
                    lambda *_args: self._owner._fail(),
                )
            except (GLib.Error, TypeError, ValueError) as error:
                print(f"[pointer] Portal session watch failed: {error}.")
                self._owner._fail()
                return
            self._select_devices()

        return handler

    def _portal_version(self) -> int:
        try:
            result = self._owner._portal_sync(
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", (_RD_IFACE, "version")),
                GLib.VariantType("(v)"),
            )
            if result is None:
                return 1
            value = result.unpack()[0]
            return int(value.unpack() if isinstance(value, GLib.Variant) else value)
        except (TypeError, ValueError, IndexError) as error:
            print(f"[pointer] Portal version property failed: {error}.")
            self._owner._fail()
            return 1

    def _select_devices(self) -> None:
        assert self._owner._session_handle is not None
        handle_token = self._new_token("salon_req")
        sender = self._sender_token()
        if sender is None:
            return
        request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{handle_token}"
        self._owner._watch_request(request_path, self._on_devices_selected)
        options = {
            "types": GLib.Variant("u", _DEVICE_POINTER | _DEVICE_KEYBOARD),
            "handle_token": GLib.Variant("s", handle_token),
        }
        version = self._portal_version()
        if self._owner._session_handle is None:
            return
        if version >= _RD_VERSION_WITH_PERSIST:
            options["persist_mode"] = GLib.Variant("u", _PERSIST_EXPLICITLY_REVOKED)
            token = self._owner._load_restore_token() if self._owner._load_restore_token else ""
            self._owner._used_restore_token = token
            if token:
                options["restore_token"] = GLib.Variant("s", token)
        self._owner._portal_sync(
            _RD_IFACE,
            "SelectDevices",
            GLib.Variant("(oa{sv})", (self._owner._session_handle, options)),
            GLib.VariantType("(o)"),
        )

    def _on_devices_selected(self, code: int, results: dict[str, object]) -> None:
        if code != 0:
            print(f"[pointer] SelectDevices was denied or failed (code={code}).")
            self._owner._fail()
            return
        self._start_session()

    def _start_session(self) -> None:
        assert self._owner._session_handle is not None
        handle_token = self._new_token("salon_req")
        sender = self._sender_token()
        if sender is None:
            return
        request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{handle_token}"
        self._owner._watch_request(request_path, self._on_started)
        self._owner._portal_sync(
            _RD_IFACE,
            "Start",
            GLib.Variant(
                "(osa{sv})",
                (
                    self._owner._session_handle,
                    self._owner._parent_window,
                    {"handle_token": GLib.Variant("s", handle_token)},
                ),
            ),
            GLib.VariantType("(o)"),
        )

    def _on_started(self, code: int, results: dict[str, object]) -> None:
        self._owner._starting = False
        self._owner._clear_timeout()
        if code != 0:
            print(f"[pointer] Start was denied or failed (code={code}) — consent not granted?")
            # A token the portal has stopped honouring (revoked in system
            # settings, or invalidated by a compositor restart) would
            # otherwise be retried forever, and the retry is silent — the
            # user would just see the pointer never work again.
            self._forget_restore_token()
            self._owner._fail()
            return
        self._owner._started = True
        self._owner._backend = "portal"
        print("[pointer] Injecting input via the desktop portal.")
        self._store_restore_token(results.get("restore_token"))
        if self._owner._on_ready is not None:
            self._owner._on_ready(True)

    def _store_restore_token(self, token: object) -> None:
        if self._owner._save_restore_token is None:
            return
        # The portal issues a *fresh* token each time and the old one stops
        # working, so this has to be written on every successful start, not
        # only the first.
        if isinstance(token, str) and token and token != self._owner._used_restore_token:
            self._owner._save_restore_token(token)

    def _forget_restore_token(self) -> None:
        if self._owner._save_restore_token is not None and self._owner._used_restore_token:
            self._owner._save_restore_token("")
        self._owner._used_restore_token = ""

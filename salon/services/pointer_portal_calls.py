# SPDX-License-Identifier: GPL-3.0-or-later
"""Guarded RemoteDesktop portal transport boundaries."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from salon.services.component import ServiceComponent  # noqa: E402
from salon.services.pointer_shared import (  # noqa: E402
    _BUS_NAME,
    _OBJECT_PATH,
    _RD_IFACE,
    _REQUEST_IFACE,
)


class PortalCalls(ServiceComponent):
    def cleanup_subscriptions(self) -> None:
        """Best-effort cleanup for every outstanding portal subscription."""
        connection = self._owner._connection
        subscriptions = set(self._owner._pending_request_subscriptions)
        if self._owner._portal_closed_subscription is not None:
            subscriptions.add(self._owner._portal_closed_subscription)
        self._owner._pending_request_subscriptions.clear()
        self._owner._portal_closed_subscription = None
        if connection is None:
            return
        for subscription in subscriptions:
            try:
                connection.signal_unsubscribe(subscription)
            except (GLib.Error, TypeError, ValueError) as error:
                print(f"[pointer] Portal subscription cleanup failed: {error}.")

    def _watch_request(
        self, request_path: str, on_response: Callable[[int, dict[str, object]], None]
    ) -> None:
        if self._owner._connection is None:
            self._owner._fail()
            return
        sub_id_holder: list[int] = []

        def handler(
            connection: Gio.DBusConnection,
            _sender: str,
            _path: str,
            _iface: str,
            _signal: str,
            params: GLib.Variant,
        ) -> None:
            try:
                code, results = params.unpack()
                if not isinstance(code, int) or not isinstance(results, dict):
                    raise ValueError("malformed portal response")
            except (TypeError, ValueError) as error:
                print(f"[pointer] Portal response failed: {error}.")
                self._owner._fail()
                return
            subscription = sub_id_holder[0]
            try:
                connection.signal_unsubscribe(subscription)
            except (GLib.Error, TypeError, ValueError) as error:
                print(f"[pointer] Portal request unsubscribe failed: {error}.")
            finally:
                self._owner._pending_request_subscriptions.discard(subscription)
            try:
                on_response(code, results)
            except (GLib.Error, TypeError, ValueError, IndexError) as error:
                print(f"[pointer] Portal response handling failed: {error}.")
                self._owner._fail()

        try:
            sub_id = self._owner._connection.signal_subscribe(
                _BUS_NAME,
                _REQUEST_IFACE,
                "Response",
                request_path,
                None,
                Gio.DBusSignalFlags.NONE,
                handler,
            )
        except (GLib.Error, TypeError, ValueError) as error:
            print(f"[pointer] Portal request subscription failed: {error}.")
            self._owner._fail()
            return
        sub_id_holder.append(sub_id)
        self._owner._pending_request_subscriptions.add(sub_id)

    def _portal_sync(
        self,
        interface: str,
        method: str,
        parameters: GLib.Variant | None,
        reply_type: GLib.VariantType | None,
    ) -> GLib.Variant | None:
        if self._owner._connection is None:
            self._owner._fail()
            return None
        try:
            return self._owner._connection.call_sync(
                _BUS_NAME,
                _OBJECT_PATH,
                interface,
                method,
                parameters,
                reply_type,
                Gio.DBusCallFlags.NONE,
                20_000,
                None,
            )
        except (GLib.Error, TypeError, ValueError) as error:
            print(f"[pointer] Portal {method} failed: {error}.")
            self._owner._fail()
            return None

    def _portal_notify(self, method: str, parameters: GLib.Variant) -> None:
        if self._owner._connection is None:
            self._owner._fail()
            return

        def finished(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                connection.call_finish(result)
            except (GLib.Error, TypeError, ValueError) as error:
                print(f"[pointer] Portal {method} completion failed: {error}.")
                self._owner._fail()

        try:
            self._owner._connection.call(
                _BUS_NAME,
                _OBJECT_PATH,
                _RD_IFACE,
                method,
                parameters,
                None,
                Gio.DBusCallFlags.NONE,
                20_000,
                None,
                finished,
            )
        except (GLib.Error, TypeError, ValueError) as error:
            print(f"[pointer] Portal {method} failed: {error}.")
            self._owner._fail()

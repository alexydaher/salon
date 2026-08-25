# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

pytest.importorskip("gi")

from gi.repository import GLib  # noqa: E402

from salon.services import pointer_injector  # noqa: E402


class FailingConnection:
    def __init__(self, boundary: str) -> None:
        self.boundary = boundary
        self.unsubscribed: list[int] = []
        self.handler = None
        self.finished = None

    def get_unique_name(self) -> str:
        if self.boundary == "unique_name":
            raise TypeError("unique-name failure")
        return ":1.42"

    def call_sync(self, *_args: object) -> None:
        if self.boundary == "call_sync":
            raise TypeError("sync failure")

    def call(self, *_args: object) -> None:
        if self.boundary == "call":
            raise TypeError("async creation failure")
        self.finished = _args[-1]

    def call_finish(self, _result: object) -> None:
        raise GLib.Error("completion failure")

    def signal_subscribe(self, *_args: object) -> int:
        if self.boundary == "subscribe":
            raise TypeError("subscription failure")
        self.handler = _args[-1]
        return 77

    def signal_unsubscribe(self, subscription: int) -> None:
        if self.boundary == "unsubscribe":
            raise TypeError("unsubscribe failure")
        self.unsubscribed.append(subscription)


def _injector(monkeypatch: pytest.MonkeyPatch, connection: FailingConnection):
    monkeypatch.setattr(pointer_injector.Gio, "bus_get_sync", lambda *_args: connection)
    callbacks: list[bool] = []
    injector = pointer_injector.PointerInjector(callbacks.append, backend="portal")
    injector._starting = True
    injector._session_handle = "/session"
    return injector, callbacks


@pytest.mark.parametrize("boundary", ["call_sync", "call", "subscribe"])
def test_portal_boundary_failure_resets_once(
    monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    connection = FailingConnection(boundary)
    injector, callbacks = _injector(monkeypatch, connection)
    if boundary == "call_sync":
        injector._portal_sync("iface", "Method", None, None)
    elif boundary == "call":
        injector._portal_notify("NotifyPointerMotion", GLib.Variant("()", ()))
    else:
        injector._watch_request("/request", lambda *_args: None)
    injector._fail()
    assert callbacks == [False]
    assert not injector.ready
    assert injector._pending_request_subscriptions == set()


def test_malformed_portal_response_unsubscribes_and_fails_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FailingConnection("response")
    injector, callbacks = _injector(monkeypatch, connection)
    injector._watch_request("/request", lambda *_args: None)
    assert connection.handler is not None
    connection.handler(connection, "", "", "", "", GLib.Variant("(s)", ("bad",)))
    assert callbacks == [False]
    assert connection.unsubscribed == [77]
    assert injector._pending_request_subscriptions == set()


def test_session_bus_acquisition_failure_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pointer_injector.Gio,
        "bus_get_sync",
        lambda *_args: (_ for _ in ()).throw(TypeError("no bus")),
    )
    callbacks: list[bool] = []
    injector = pointer_injector.PointerInjector(callbacks.append, backend="portal")
    injector.start()
    assert callbacks == [False]


def test_async_completion_failure_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FailingConnection("completion")
    injector, callbacks = _injector(monkeypatch, connection)
    injector._portal_notify("NotifyPointerMotion", GLib.Variant("()", ()))
    assert connection.finished is not None
    connection.finished(connection, object())
    assert callbacks == [False]


def test_unsubscribe_failure_does_not_escape_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FailingConnection("unsubscribe")
    injector, callbacks = _injector(monkeypatch, connection)
    injector._pending_request_subscriptions.add(77)
    injector._portal_closed_subscription = 78
    injector._fail()
    assert callbacks == [False]
    assert injector._pending_request_subscriptions == set()
    assert injector._portal_closed_subscription is None


def test_sender_name_failure_stops_request_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FailingConnection("unique_name")
    injector, callbacks = _injector(monkeypatch, connection)
    injector._create_session()
    assert callbacks == [False]
    assert injector._pending_request_subscriptions == set()

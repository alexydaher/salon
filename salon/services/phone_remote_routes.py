# SPDX-License-Identifier: GPL-3.0-or-later
"""The server facade's plumbing: every route, and the helpers routes share.

Split out of `pairing.py` because it is the part with no judgement in it.
`PhoneRemoteServer` is assembled from seven components that each own one
concern, and each of them reaches the others through the owning server —
so the server needs one forwarding method per entry point. That is a long
list of one-line methods, and a long list of one-line methods is exactly
the wrong thing to have to read past to find the object's actual shape.
"""

from __future__ import annotations

from typing import Any


class PhoneRemoteRoutes:
    """Forwarding only. Every method here delegates to a component."""

    def _touch(self) -> None:
        self._lifecycle._touch()  # noqa: SLF001

    def _lock(self) -> None:
        self._lifecycle.lock()

    def _check_idle(self) -> bool:
        return self._lifecycle._check_idle()  # noqa: SLF001

    def _close_streams(self) -> None:
        self._connection._close_streams()  # noqa: SLF001

    def _broadcast(self, payload: bytes) -> None:
        self._connection._broadcast(payload)  # noqa: SLF001

    def _from_local_network(self, message: Any) -> bool:
        return self._authorization._from_local_network(message)  # noqa: SLF001

    def _fields(self, message: Any) -> Any:
        return self._authorization._fields(message)  # noqa: SLF001

    def _has_token(self, candidate: object) -> bool:
        return self._authorization._has_token(candidate)  # noqa: SLF001

    def _authorize(self, message: Any) -> Any:
        return self._authorization._authorize(message)  # noqa: SLF001

    def _authorize_get(self, message: Any, query: Any) -> bool:
        return self._authorization._authorize_get(message, query)  # noqa: SLF001

    def _refuse(self, *args: Any) -> None:
        self._authorization._refuse(*args)  # noqa: SLF001

    def _ok(self, *args: Any) -> None:
        self._authorization._ok(*args)  # noqa: SLF001

    def _json(self, *args: Any) -> None:
        self._authorization._json(*args)  # noqa: SLF001

    def _may_touch(self, tile_id: str) -> bool:
        return self._catalog._may_touch(tile_id)  # noqa: SLF001

    def _handle_page(self, *args: Any) -> None:
        self._resources._handle_page(*args)  # noqa: SLF001

    def _handle_manifest(self, *args: Any) -> None:
        self._resources._handle_manifest(*args)  # noqa: SLF001

    def _handle_icon(self, *args: Any) -> None:
        self._resources._handle_icon(*args)  # noqa: SLF001

    def _handle_asset(self, *args: Any) -> None:
        self._resources._handle_asset(*args)  # noqa: SLF001

    def _handle_awake(self, *args: Any) -> None:
        self._resources._handle_awake(*args)  # noqa: SLF001

    def _handle_connect(self, *args: Any) -> None:
        self._connection._handle_connect(*args)  # noqa: SLF001

    def _handle_state(self, *args: Any) -> None:
        self._connection._handle_state(*args)  # noqa: SLF001

    def _handle_events(self, *args: Any) -> None:
        self._connection._handle_events(*args)  # noqa: SLF001

    def _handle_search(self, *args: Any) -> None:
        self._catalog._handle_search(*args)  # noqa: SLF001

    def _handle_tile_action(self, *args: Any) -> None:
        self._catalog._handle_tile_action(*args)  # noqa: SLF001

    def _handle_volume(self, *args: Any) -> None:
        self._catalog._handle_volume(*args)  # noqa: SLF001

    def _handle_art(self, *args: Any) -> None:
        self._catalog._handle_art(*args)  # noqa: SLF001

    def _handle_apps(self, *args: Any) -> None:
        self._browse._handle_apps(*args)  # noqa: SLF001

    def _handle_now_playing_art(self, *args: Any) -> None:
        self._browse._handle_now_playing_art(*args)  # noqa: SLF001

    def _handle_type(self, *args: Any) -> None:
        self._input._handle_type(*args)  # noqa: SLF001

    def _handle_action(self, *args: Any) -> None:
        self._input._handle_action(*args)  # noqa: SLF001

    def _handle_launch(self, *args: Any) -> None:
        self._input._handle_launch(*args)  # noqa: SLF001

    def _handle_transport(self, *args: Any) -> None:
        self._input._handle_transport(*args)  # noqa: SLF001

    def _handle_running(self, *args: Any) -> None:
        self._input._handle_running(*args)  # noqa: SLF001

    def _handle_tune(self, *args: Any) -> None:
        self._tuning._handle_tune(*args)  # noqa: SLF001

    def _handle_pointer(self, *args: Any) -> None:
        self._input._handle_pointer(*args)  # noqa: SLF001

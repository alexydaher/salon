# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any

from salon.services.phone_remote_auth import PhoneRemoteAuthorization
from salon.services.phone_remote_catalog import PhoneRemoteCatalog
from salon.services.phone_remote_connection import PhoneRemoteConnection
from salon.services.phone_remote_input import PhoneRemoteInput
from salon.services.phone_remote_lifecycle import PhoneRemoteLifecycle
from salon.services.phone_remote_resources import PhoneRemoteResources
from salon.services.phone_remote_shared import (
    DEFAULT_PORT,
    MAX_ATTEMPTS,
    SESSION_TIMEOUT_SECONDS,
    Callable,
    OfferedIds,
    Path,
    RemoteState,
    RemoteTile,
    Soup,
    StateFeed,
)
from salon.services.phone_remote_state import PhoneRemoteState

__all__ = ["MAX_ATTEMPTS", "SESSION_TIMEOUT_SECONDS", "PairingServer"]


class PhoneRemoteServer:
    """Serves the remote page, and everything it can ask for."""

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        *,
        on_action: Callable[[str], None] | None = None,
        on_pointer: Callable[[float, float], None] | None = None,
        on_click: Callable[[], None] | None = None,
        on_locked: Callable[[], None] | None = None,
        on_launch: Callable[[str], None] | None = None,
        on_transport: Callable[[str], bool] | None = None,
        art_for: Callable[[str], Path | None] | None = None,
        pointer_ready: Callable[[], bool] | None = None,
        on_remote_text: Callable[[str], bool] | None = None,
        on_search: Callable[[str], list[RemoteTile]] | None = None,
        on_tile_action: Callable[[str, str], str] | None = None,
        on_volume: Callable[[float], None] | None = None,
        on_mute: Callable[[], None] | None = None,
        on_scroll: Callable[[float, float], None] | None = None,
        on_scroll_end: Callable[[], None] | None = None,
        on_button: Callable[[str, str], None] | None = None,
    ) -> None:
        self._on_action = on_action
        self._on_pointer = on_pointer
        self._on_click = on_click
        self._on_locked = on_locked
        self._on_launch = on_launch
        self._on_transport = on_transport
        self._art_for = art_for
        self._pointer_ready = pointer_ready
        self._on_remote_text = on_remote_text
        self._on_search = on_search
        self._on_tile_action = on_tile_action
        self._on_volume = on_volume
        self._on_mute = on_mute
        self._on_scroll = on_scroll
        self._on_scroll_end = on_scroll_end
        self._on_button = on_button
        self._port = port
        self._server: Soup.Server | None = None
        self._code = ""
        self._token = ""
        self._idle_id: int | None = None
        self._last_seen = 0.0
        # When a request last arrived *bearing the token*. Separate from
        # `_last_seen`, which starts the idle clock at start(): a server
        # nobody has scanned yet must not claim a phone is connected.
        self._talked_at = 0.0
        self._wrong_attempts = 0
        self._locked = False
        # What the phone draws. Published from the home screen; serialised
        # only when a poll actually asks for a version it hasn't seen.
        self._feed = StateFeed()
        # Ids served in search results. `/launch` and `/art` accept these as
        # well as the ones in the published state — see core.remote for why
        # a result list is not published and why this is bounded.
        self._offered = OfferedIds()
        # Open EventSource connections. The 1 Hz poll is still there and
        # still correct; this is what makes a press feel immediate instead
        # of up to a second late, and the page falls back to polling on any
        # browser or proxy that will not hold the stream open.
        self._streams: list[Soup.ServerMessage] = []
        # Text goes wherever is currently asking for it, which is nowhere
        # most of the time. A sink rather than a constructor argument
        # because one server now serves several screens: search, each of the
        # tile editor's fields, and the remote, which asks for none.
        self._text_sink: Callable[[str], None] | None = None
        # Reference counted: the remote and an open text field can both want
        # the server, and whichever is dismissed first must not take the
        # port out from under the other.
        self._holders: set[str] = set()
        self._lifecycle = PhoneRemoteLifecycle(self)
        self._authorization = PhoneRemoteAuthorization(self)
        self._resources = PhoneRemoteResources(self)
        self._connection = PhoneRemoteConnection(self)
        self._input = PhoneRemoteInput(self)
        self._catalog = PhoneRemoteCatalog(self)
        self._state = PhoneRemoteState(self)

    def start(self) -> bool:
        return self._lifecycle.start()

    def stop(self) -> None:
        self._lifecycle.stop()

    def acquire(self, holder: str) -> bool:
        return self._state.acquire(holder)

    def release(self, holder: str) -> None:
        self._state.release(holder)

    def holds(self, holder: str) -> bool:
        return self._state.holds(holder)

    def set_text_sink(self, sink: Callable[[str], None] | None) -> None:
        self._state.set_text_sink(sink)

    def release_text_sink(self, sink: Callable[[str], None]) -> None:
        self._state.release_text_sink(sink)

    def publish(self, state: RemoteState) -> bool:
        return self._state.publish(state)

    @property
    def running(self) -> bool:
        return self._state.running

    @property
    def code(self) -> str:
        return self._state.code

    @property
    def token(self) -> str:
        return self._state.token

    @property
    def locked(self) -> bool:
        return self._state.locked

    @property
    def connected(self) -> bool:
        return self._state.connected

    @property
    def url(self) -> str | None:
        return self._state.url

    @property
    def pair_url(self) -> str | None:
        return self._state.pair_url

    def _touch(self) -> None:
        self._lifecycle._touch()  # noqa: SLF001

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

    def _handle_type(self, *args: Any) -> None:
        self._input._handle_type(*args)  # noqa: SLF001

    def _handle_action(self, *args: Any) -> None:
        self._input._handle_action(*args)  # noqa: SLF001

    def _handle_launch(self, *args: Any) -> None:
        self._input._handle_launch(*args)  # noqa: SLF001

    def _handle_transport(self, *args: Any) -> None:
        self._input._handle_transport(*args)  # noqa: SLF001

    def _handle_pointer(self, *args: Any) -> None:
        self._input._handle_pointer(*args)  # noqa: SLF001

PairingServer = PhoneRemoteServer

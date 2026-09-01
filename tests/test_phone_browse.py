# SPDX-License-Identifier: GPL-3.0-or-later
"""What the phone can browse, and what it is served to browse it with.

Three endpoints that did not exist while the remote was one page: `/ui`,
which serves the page's stylesheets and modules; `/apps`, the whole
installed list the phone could previously only search; and `/np-art`, the
cover of whatever is playing.

Driven over real HTTP against the real `Soup.Server`, like the rest of the
remote's tests — the thing being asserted is what a request from the
network actually gets back.
"""

from __future__ import annotations

import json

import pytest
from phone_remote_harness import _connect, _free_port, _get, _run, _send_full

from salon.core.remote import RemoteNowPlaying, RemoteRow, RemoteState, RemoteTile
from salon.services.pairing import PairingServer


@pytest.fixture()
def browsing(tmp_path):
    """A server wired the way the home screen wires it, plus the two
    callbacks that only the phone has a use for."""
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n cover bytes")
    poster = tmp_path / "poster.png"
    poster.write_bytes(b"\x89PNG\r\n\x1a\n poster bytes")
    installed = [
        RemoteTile(id="app:gimp.desktop", title="GIMP", has_art=True),
        RemoteTile(id="app:vlc.desktop", title="VLC"),
    ]
    state = {"cover": cover}

    instance = PairingServer(
        port=_free_port(),
        on_launch=lambda tile_id: None,
        art_for=lambda tile_id: poster if tile_id.startswith("app:") else None,
        on_apps=lambda: list(installed),
        np_art_for=lambda _source: state["cover"],
    )
    instance.publish(
        RemoteState(
            rows=(
                RemoteRow(
                    id="home",
                    title="Home",
                    tiles=(RemoteTile(id="netflix", title="Netflix"),),
                ),
            ),
            now_playing=RemoteNowPlaying(
                title="Blue Train", detail="John Coltrane", playing=True, has_art=True
            ),
        )
    )
    if not instance.start():
        pytest.skip("could not bind a local port for the pairing server")
    yield instance, state, cover
    instance.stop()


# --- the page's own files -------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content_type"),
    [("base.css", "text/css"), ("main.js", "text/javascript")],
)
def test_a_stylesheet_and_a_module_are_served_with_the_right_type(
    browsing, name: str, content_type: str
) -> None:
    """A browser refuses a module script served as anything but a
    JavaScript MIME type, and refuses it quietly enough that the page
    simply does nothing."""
    server, _state, _cover = browsing
    port = server._port  # noqa: SLF001
    status, body = _run(server, lambda: _get(port, f"/ui/{name}"))
    assert status == 200
    assert b"SPDX-License-Identifier" in body[:200]
    served = _run(server, lambda: _headers(port, f"/ui/{name}"))
    assert served.startswith(content_type)


def _headers(port: int, path: str) -> str:
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
        return str(response.headers.get("Content-Type", ""))


def _cache_control(port: int, path: str) -> str:
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
        return str(response.headers.get("Cache-Control", ""))


@pytest.mark.parametrize("path", ["/", "/ui/base.css", "/ui/main.js"])
def test_the_phone_shell_is_not_reused_across_upgrades(browsing, path: str) -> None:
    """A cold QR load must not resurrect viewport code from an older Salon."""
    server, _state, _cover = browsing
    port = server._port  # noqa: SLF001
    assert _run(server, lambda: _cache_control(port, path)) == "no-store"


@pytest.mark.parametrize(
    ("path", "refusal"),
    [
        ("/ui/nothing.js", 404),
        ("/ui/index.html", 404),
        ("/ui/", 404),
        ("/ui/sub/dom.js", 404),
        # libsoup refuses an encoded separator outright rather than handing
        # it on, and collapses a literal `..` before it routes at all — so
        # a traversal never reaches the handler in the first place. The
        # pattern is the second line of defence, asserted directly in
        # tests/test_phone_page.py.
        ("/ui/..%2fbase.css", 400),
    ],
)
def test_an_asset_that_is_not_a_bare_bundled_name_is_refused(
    browsing, path: str, refusal: int
) -> None:
    server, _state, _cover = browsing
    port = server._port  # noqa: SLF001
    status, _body = _run(server, lambda: _get(port, path))
    assert status == refusal


def test_the_page_assets_need_no_credential(browsing) -> None:
    """They cannot: the phone has to load the page before it can
    authenticate, and nothing served here is a secret."""
    server, _state, _cover = browsing
    port = server._port  # noqa: SLF001
    status, _body = _run(server, lambda: _get(port, "/ui/dom.js"))
    assert status == 200


# --- the installed-app list -----------------------------------------------


def test_the_whole_app_list_is_served_and_its_art_is_then_fetchable(browsing) -> None:
    """Search has covered the whole system for a while; this is the browse
    half, and its ids have to be as good as a search result's — a card whose
    artwork 404s falls back to a coloured letter."""
    server, _state, _cover = browsing
    port = server._port  # noqa: SLF001

    def exchange():
        _status, key = _connect(port, server.code)
        listed = json.loads(_send_full(port, "/apps", {"key": key})[1])["apps"]
        art = _get(port, "/art/app%3Agimp.desktop", k=key)[0]
        return listed, art

    listed, art = _run(server, exchange)
    assert [tile["title"] for tile in listed] == ["GIMP", "VLC"]
    assert art == 200


def test_the_app_list_needs_the_token(browsing) -> None:
    server, _state, _cover = browsing
    port = server._port  # noqa: SLF001
    status, _body = _run(server, lambda: _send_full(port, "/apps", {"key": "wrong"}))
    assert status == 401


def test_a_server_with_no_app_list_says_so_rather_than_answering_empty(tmp_path) -> None:
    """An empty list and an unavailable one look identical on the phone,
    and only one of them is worth telling somebody about."""
    instance = PairingServer(port=_free_port())
    if not instance.start():
        pytest.skip("could not bind a local port for the pairing server")
    port = instance._port  # noqa: SLF001
    try:

        def exchange():
            _status, key = _connect(port, instance.code)
            return _send_full(port, "/apps", {"key": key})[0]

        assert _run(instance, exchange) == 501
    finally:
        instance.stop()


# --- the cover of what is playing ------------------------------------------


def test_the_cover_is_served_for_a_local_player(browsing) -> None:
    server, _state, cover = browsing
    port = server._port  # noqa: SLF001

    def exchange():
        _status, key = _connect(port, server.code)
        return _get(port, "/np-art", k=key)

    status, body = _run(server, exchange)
    assert status == 200
    assert body == cover.read_bytes()


def test_the_cover_is_not_cached_because_its_url_never_changes(browsing) -> None:
    """Unlike a tile's artwork this URL is not keyed by what it holds, so a
    cached copy would be the previous track's cover."""
    server, _state, _cover = browsing
    port = server._port  # noqa: SLF001

    def exchange():
        _status, key = _connect(port, server.code)
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/np-art?k={key}", timeout=5) as r:
            return str(r.headers.get("Cache-Control", ""))

    assert "no-store" in _run(server, exchange)


def test_nothing_playing_is_a_404_rather_than_an_empty_body(browsing) -> None:
    server, state, _cover = browsing
    state["cover"] = None
    port = server._port  # noqa: SLF001

    def exchange():
        _status, key = _connect(port, server.code)
        return _get(port, "/np-art", k=key)[0]

    assert _run(server, exchange) == 404


def test_the_cover_needs_the_token(browsing) -> None:
    server, _state, _cover = browsing
    port = server._port  # noqa: SLF001
    status, _body = _run(server, lambda: _get(port, "/np-art", k="wrong"))
    assert status == 401

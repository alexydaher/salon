# SPDX-License-Identifier: GPL-3.0-or-later
"""Which image on a page is the site's icon (salon/core/siteicon.py).

The ordering rules here are the whole feature: get them wrong and a
streaming tile picks the 16x16 favicon over the 180x180 app icon, which is
indistinguishable from the bug this replaced.
"""

from __future__ import annotations

from salon.core.siteicon import (
    MIN_USEFUL_SIZE,
    default_favicon,
    icon_candidates,
    origin,
)


def test_origin_only_accepts_http_urls() -> None:
    assert origin("https://www.netflix.com/browse") == "https://www.netflix.com"
    assert origin("http://tv.local:8080/x") == "http://tv.local:8080"
    assert origin("file:///home/alexy/x.html") is None
    assert origin("not a url") is None


def test_default_favicon_is_the_root_of_the_site() -> None:
    assert default_favicon("https://example.com/deep/page?q=1") == "https://example.com/favicon.ico"
    assert default_favicon("mailto:someone@example.com") is None


def test_apple_touch_icon_beats_a_larger_favicon() -> None:
    """A favicon is a browser-tab mark; apple-touch-icon is an app icon, and
    that is the shape a tile wants even when the favicon claims to be bigger."""
    html = """
      <link rel="icon" href="/fav.png" sizes="256x256">
      <link rel="apple-touch-icon" href="/touch.png" sizes="180x180">
    """
    best = icon_candidates(html, "https://example.com/")
    assert best[0].url == "https://example.com/touch.png"
    assert best[0].apple is True


def test_largest_declared_size_wins_among_equals() -> None:
    html = """
      <link rel="apple-touch-icon" href="/a.png" sizes="57x57">
      <link rel="apple-touch-icon" href="/b.png" sizes="152x152">
      <link rel="apple-touch-icon" href="/c.png" sizes="120x120">
    """
    order = [c.url for c in icon_candidates(html, "https://example.com/")]
    assert order == [
        "https://example.com/b.png",
        "https://example.com/c.png",
        "https://example.com/a.png",
    ]


def test_an_undeclared_size_sorts_last_not_first() -> None:
    html = """
      <link rel="icon" href="/unknown.png">
      <link rel="icon" href="/known.png" sizes="64x64">
    """
    order = [c.url for c in icon_candidates(html, "https://example.com/")]
    assert order[0] == "https://example.com/known.png"


def test_svg_outranks_equally_sized_raster() -> None:
    html = """
      <link rel="icon" href="/mark.png">
      <link rel="icon" href="/mark.svg">
    """
    assert icon_candidates(html, "https://example.com/")[0].url == "https://example.com/mark.svg"


def test_relative_and_protocol_relative_hrefs_resolve() -> None:
    html = """
      <link rel="apple-touch-icon" href="../icons/touch.png" sizes="180x180">
      <link rel="icon" href="//cdn.example.net/f.png" sizes="96x96">
    """
    urls = [c.url for c in icon_candidates(html, "https://example.com/a/b/page.html")]
    assert "https://example.com/a/icons/touch.png" in urls
    assert "https://cdn.example.net/f.png" in urls


def test_mask_icon_is_not_an_icon() -> None:
    """Safari's pinned-tab mark is a monochrome silhouette: on a dark tile it
    is a black square."""
    html = '<link rel="mask-icon" href="/mask.svg" color="#000">'
    assert icon_candidates(html, "https://example.com/") == []


def test_duplicate_declarations_appear_once() -> None:
    html = """
      <link rel="icon" href="/f.png" sizes="64x64">
      <link rel="icon" href="/f.png" sizes="64x64">
    """
    assert len(icon_candidates(html, "https://example.com/")) == 1


def test_malformed_markup_does_not_raise() -> None:
    html = "<link rel=icon href=/a.png sizes=64x64><link><link rel><p>text"
    assert [c.url for c in icon_candidates(html, "https://example.com/")] == [
        "https://example.com/a.png"
    ]


def test_min_useful_size_rejects_a_favicon_and_keeps_a_mark() -> None:
    assert MIN_USEFUL_SIZE > 16
    assert MIN_USEFUL_SIZE <= 32

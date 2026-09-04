# SPDX-License-Identifier: GPL-3.0-or-later
"""A failed site-icon lookup is remembered, but not forever.

The marker had no expiry, so a television that booted before its router did
kept a row of blank tiles for the life of the install, with nothing in the
interface to clear it. See DECISIONS 2026-09-04.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from salon.services import artwork_paths

URL = "https://www.example.com/watch"


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path: Path) -> None:
    os.environ["XDG_CACHE_HOME"] = str(tmp_path)


def _record_miss() -> Path:
    marker = artwork_paths.site_icon_miss_path(URL)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return marker


def test_no_marker_is_not_a_current_miss() -> None:
    assert not artwork_paths.site_icon_miss_is_current(URL)


def test_a_fresh_miss_is_believed() -> None:
    """Otherwise a site with no icon costs two requests on every catalogue
    rebuild, and the catalogue rebuilds on every launch."""
    _record_miss()
    assert artwork_paths.site_icon_miss_is_current(URL)


def test_a_stale_miss_is_not() -> None:
    marker = _record_miss()
    old = time.time() - artwork_paths.MISS_TTL_SECONDS - 60
    os.utime(marker, (old, old))
    assert not artwork_paths.site_icon_miss_is_current(URL)


def test_the_ttl_is_a_week_rather_than_forever() -> None:
    assert 0 < artwork_paths.MISS_TTL_SECONDS <= 30 * 24 * 60 * 60


def test_forgetting_clears_both_the_icons_and_the_misses() -> None:
    """Backs the one Settings action. Both, because clearing only the
    cached icons leaves the failures in place and nothing re-resolves."""
    _record_miss()
    icon = artwork_paths.site_icon_path(URL)
    icon.parent.mkdir(parents=True, exist_ok=True)
    icon.write_bytes(b"not really a png")

    artwork_paths.forget_site_icons()

    assert not icon.exists()
    assert not artwork_paths.site_icon_miss_is_current(URL)


def test_forgetting_an_absent_cache_is_not_an_error() -> None:
    artwork_paths.forget_site_icons()


def test_misses_live_apart_from_artwork_the_user_chose() -> None:
    """The separation is what lets "forget the guesses" be one directory
    removal that cannot take away a picture somebody picked."""
    guessed = artwork_paths.site_icon_path(URL)
    chosen = artwork_paths.cached_remote_path(URL)
    assert artwork_paths.site_icon_cache_dir() not in chosen.parents
    assert guessed.parent == artwork_paths.site_icon_cache_dir()

# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic local and cached artwork paths."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from salon.core import siteicon
from salon.core.model import Tile

_ARTWORK_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
_MAX_CACHE_BYTES = 256 * 1024 * 1024
_MAX_CACHE_ENTRIES = 512

# How long a failed site-icon lookup is remembered. See
# site_icon_miss_is_current.
MISS_TTL_SECONDS = 7 * 24 * 60 * 60.0


def artwork_drop_dir() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "salon" / "artwork"


def artwork_cache_dir() -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_home / "salon" / "art"


def site_icon_cache_dir() -> Path:
    """Kept apart from the explicit-URL cache so "forget the icons you
    guessed" can be one directory removal that leaves artwork the user
    actually chose alone."""
    return artwork_cache_dir() / "site"


def site_icon_path(url: str) -> Path:
    root = siteicon.origin(url) or url
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()
    return site_icon_cache_dir() / f"{digest}.png"


def site_icon_miss_path(url: str) -> Path:
    """A zero-byte marker meaning "this origin was asked and had nothing".

    Without it, a site with no usable icon costs two HTTP requests on every
    catalogue rebuild — and the catalogue rebuilds on every launch, every
    config save and every artwork drop.
    """
    return site_icon_path(url).with_suffix(".miss")


def site_icon_miss_is_current(url: str, *, ttl_seconds: float = MISS_TTL_SECONDS) -> bool:
    """Whether a recorded miss is still worth believing.

    It expires, because the reasons a lookup fails are overwhelmingly
    temporary — no network yet on a television that boots before its
    router, a site behind a captive portal, a redesign that has since
    added an `apple-touch-icon`. A permanent marker turned one bad first
    boot into a home screen that could never show a brand icon again, with
    nothing in the interface to clear it. A week is long enough that the
    "two requests per catalogue rebuild" cost this exists to prevent never
    comes back, and short enough that no one has to know this file exists.
    """
    marker = site_icon_miss_path(url)
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return False
    return age < ttl_seconds


def forget_site_icons() -> None:
    """Drop every guessed site icon and every recorded miss.

    Backs "Refresh artwork" in Settings → Tiles: the guesses live in their
    own directory precisely so this cannot touch artwork the user chose.
    """
    root = site_icon_cache_dir()
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_file():
                entry.unlink()
        except OSError:
            continue


def drop_folder_path(tile_id: str) -> Path | None:
    drop_dir = artwork_drop_dir()
    for extension in _ARTWORK_EXTENSIONS:
        candidate = drop_dir / f"{tile_id}.{extension}"
        if candidate.is_file():
            return candidate
    return None


def cached_remote_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return artwork_cache_dir() / f"{digest}.png"


def prune_artwork_cache(
    *, max_bytes: int = _MAX_CACHE_BYTES, max_entries: int = _MAX_CACHE_ENTRIES
) -> None:
    """Bound only Salon-generated cache files, oldest first."""
    root = artwork_cache_dir()
    try:
        files = [path for path in root.rglob("*") if path.is_file()]
    except OSError:
        return
    entries: list[tuple[float, int, Path]] = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((stat.st_mtime, stat.st_size, path))
    total = sum(size for _mtime, size, _path in entries)
    count = len(entries)
    for _mtime, size, path in sorted(entries):
        if total <= max_bytes and count <= max_entries:
            break
        try:
            path.unlink()
        except OSError:
            continue
        total -= size
        count -= 1


def local_artwork_path(tile: Tile) -> Path | None:
    """The level-1/2 image for this tile, if one is on disk right now.

    A remote `artwork` URL only resolves here once it has been fetched into
    the cache; until then the tile falls through to its icon and repaints
    when `fetch_remote_artwork` reports the download finished.
    """
    if tile.artwork:
        if tile.artwork.startswith(("http://", "https://")):
            cached = cached_remote_path(tile.artwork)
            if cached.is_file():
                return cached
        else:
            candidate = Path(tile.artwork).expanduser()
            if candidate.is_file():
                return candidate
    return drop_folder_path(tile.id)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic local and cached artwork paths."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from salon.core import siteicon
from salon.core.model import Tile

_ARTWORK_EXTENSIONS = ("jpg", "jpeg", "png", "webp")

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

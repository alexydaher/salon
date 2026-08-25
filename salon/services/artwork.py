# SPDX-License-Identifier: GPL-3.0-or-later
"""Compatibility facade for artwork resolution and color APIs."""

from salon.services.artwork_colors import (
    dominant_color,
    glow_color,
    hashed_accent,
    parse_hex,
    to_hex,
)
from salon.services.artwork_models import Artwork
from salon.services.artwork_paths import (
    artwork_cache_dir,
    artwork_drop_dir,
    site_icon_cache_dir,
)
from salon.services.artwork_resolver import ArtworkResolver

__all__ = [
    "Artwork",
    "ArtworkResolver",
    "artwork_cache_dir",
    "artwork_drop_dir",
    "dominant_color",
    "glow_color",
    "hashed_accent",
    "parse_hex",
    "site_icon_cache_dir",
    "to_hex",
]

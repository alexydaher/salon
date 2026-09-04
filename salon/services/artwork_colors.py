# SPDX-License-Identifier: GPL-3.0-or-later
"""Artwork accent parsing, generation, and image color analysis."""

from __future__ import annotations

import colorsys
import hashlib
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib  # noqa: E402

_SAMPLE_SIZE = 16
_MIN_ALPHA = 128
_MIN_LIGHTNESS = 0.18
_MAX_LIGHTNESS = 0.95
_MIN_SATURATION = 0.15


def _rgba(red: float, green: float, blue: float, alpha: float = 1.0) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red = red
    color.green = green
    color.blue = blue
    color.alpha = alpha
    return color


def parse_hex(value: str) -> Gdk.RGBA | None:
    color = Gdk.RGBA()
    return color if color.parse(value) else None


def to_hex(color: Gdk.RGBA) -> str:
    """`#rrggbb`, for the one consumer that isn't GTK: the phone remote
    draws its own cards in CSS and needs the accent as a string."""
    red, green, blue = (
        round(max(0.0, min(1.0, channel)) * 255) for channel in (color.red, color.green, color.blue)
    )
    return f"#{red:02x}{green:02x}{blue:02x}"


def hashed_accent(seed: str) -> Gdk.RGBA:
    """A stable, pleasant hue derived from a tile id — the level-4 card's
    colour. Saturation and lightness are pinned so every generated card sits
    in the same family as the rest of the palette instead of shouting."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    red, green, blue = colorsys.hls_to_rgb(hue, 0.52, 0.42)
    return _rgba(red, green, blue)


def glow_color(accent: Gdk.RGBA) -> Gdk.RGBA:
    """The accent as a *light source* rather than as a surface colour.

    A tile's accent is whatever its artwork happens to be built from, and
    plenty of those are dark or desaturated — the hue hashed from a tile id,
    a muted app icon. Blurred at low alpha against a near-black backdrop,
    such a colour produces no visible light at all. Lifting lightness and
    saturation to a floor lets launching surfaces retain the tile's hue
    while still reading as light falling on the screen.
    """
    hue, lightness, saturation = colorsys.rgb_to_hls(accent.red, accent.green, accent.blue)
    red, green, blue = colorsys.hls_to_rgb(hue, max(lightness, 0.62), max(saturation, 0.65))
    return _rgba(red, green, blue)


def dominant_color(path: Path) -> Gdk.RGBA | None:
    """The most saturated colour in an image, above a lightness floor.

    Downscales to a small grid first (§7.4) so this is cheap enough to run
    synchronously while building tiles; transparent and near-black/near-white
    pixels are skipped so a logo on a transparent field reports the logo's
    colour rather than a muddy average.
    """
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(path), _SAMPLE_SIZE, _SAMPLE_SIZE, True
        )
    except GLib.Error:
        return None

    pixels = pixbuf.get_pixels()
    channels = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    width = pixbuf.get_width()
    height = pixbuf.get_height()
    has_alpha = pixbuf.get_has_alpha()

    best: tuple[float, float, float, float] | None = None  # (saturation, r, g, b)
    total = [0.0, 0.0, 0.0]
    counted = 0

    for y in range(height):
        for x in range(width):
            offset = y * rowstride + x * channels
            if has_alpha and pixels[offset + 3] < _MIN_ALPHA:
                continue
            red = pixels[offset] / 255.0
            green = pixels[offset + 1] / 255.0
            blue = pixels[offset + 2] / 255.0
            _, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
            if not (_MIN_LIGHTNESS <= lightness <= _MAX_LIGHTNESS):
                continue
            total[0] += red
            total[1] += green
            total[2] += blue
            counted += 1
            if saturation >= _MIN_SATURATION and (best is None or saturation > best[0]):
                best = (saturation, red, green, blue)

    if best is not None:
        return _rgba(best[1], best[2], best[3])
    if counted:
        return _rgba(total[0] / counted, total[1] / counted, total[2] / counted)
    return None

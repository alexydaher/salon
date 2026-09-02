# SPDX-License-Identifier: GPL-3.0-or-later
"""Which picture the backdrop shows, and how to get a texture for it.

Split out of `backdrop.py`: everything here is about turning a settings
string into a `Gdk.Texture`, and none of it touches the widget, the
cross-fade or the composed texture cache.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib  # noqa: E402

WALLPAPER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".avif")
DEFAULT_WALLPAPER = "resource:///io/github/alexydaher/Salon/backgrounds/salon-ambient.png"
DEFAULT_WALLPAPER_DIM = 0.38

TREATMENT_AUTOMATIC = "automatic"
TREATMENT_ORIGINAL = "original"
TREATMENT_FOCUS = "focus"
TREATMENT_ACCENT = "accent"
TREATMENTS = (
    TREATMENT_AUTOMATIC,
    TREATMENT_ORIGINAL,
    TREATMENT_FOCUS,
    TREATMENT_ACCENT,
)


def resolve_source(source: str) -> str:
    """Empty is the designed Salon ambience. A single dash is the
    deliberate opt-out for people who want the palette's flat surface."""
    if source == "-":
        return ""
    return DEFAULT_WALLPAPER if not source else source


def resolve_dim(source: str, dim: float) -> float:
    """The default wallpaper carries its own dim; a chosen one takes the
    setting."""
    if not source:
        return DEFAULT_WALLPAPER_DIM
    return max(0.0, min(1.0, dim))


def resolve_treatment(source: str, treatment: str) -> str:
    """Turn the user's policy into the treatment for this picture.

    The bundled image is interface artwork and was made to accept the
    focused tile's colour. A picture somebody chose is already a finished
    composition, so Automatic leaves its colours alone.
    """
    if treatment not in TREATMENTS:
        treatment = TREATMENT_AUTOMATIC
    if treatment == TREATMENT_AUTOMATIC:
        return TREATMENT_FOCUS if not source else TREATMENT_ORIGINAL
    return treatment


def load(source: str) -> Gdk.Texture | None:
    """A resource, a file, or a folder to pick one picture out of.

    A folder is a slideshow: one image is chosen at random per call, which
    is why this is called again to advance it. Random rather than
    alphabetical because a slideshow that always opens on the same picture
    is not one.
    """
    if not source:
        return None
    if source.startswith("resource://"):
        try:
            return Gdk.Texture.new_from_resource(source.removeprefix("resource://"))
        except GLib.Error:
            return None
    path = Path(os.path.expanduser(source))
    if path.is_dir():
        chosen = _pick_from_folder(path)
        if chosen is None:
            return None
        path = chosen
    if not path.is_file():
        return None
    try:
        return Gdk.Texture.new_from_filename(str(path))
    except GLib.Error:
        # A file that is not an image, or one being written to right now.
        # The palette's own surface colour is a correct backdrop.
        return None


def _pick_from_folder(path: Path) -> Path | None:
    try:
        candidates = sorted(
            entry
            for entry in path.iterdir()
            if entry.suffix.lower() in WALLPAPER_SUFFIXES and entry.is_file()
        )
    except OSError:
        return None
    if not candidates:
        return None
    return random.choice(candidates)

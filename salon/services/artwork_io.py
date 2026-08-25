# SPDX-License-Identifier: GPL-3.0-or-later
"""Image decoding, encoding, and icon-kind helpers."""
from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402

_HTML_SNIFF_BYTES = 512 * 1024

def document_head(data: bytes) -> str:
    """The document's <head>, decoded leniently. Bounded twice: at </head>
    if there is one, and at _HTML_SNIFF_BYTES if there isn't."""
    window = data[:_HTML_SNIFF_BYTES]
    end = window.lower().find(b"</head>")
    if end != -1:
        window = window[:end]
    return window.decode("utf-8", errors="replace")


def decode_image(data: object) -> GdkPixbuf.Pixbuf | None:
    """Bytes off the network to a pixbuf, or None. Never raises: the input
    is whatever a web server chose to send, including an HTML error page
    with an image/png content type."""
    if not data:
        return None
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(bytes(data))
        loader.close()
        return loader.get_pixbuf()
    except GLib.Error:
        return None


def save_png(pixbuf: GdkPixbuf.Pixbuf, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        pixbuf.savev(str(destination), "png", [], [])
    except GLib.Error:
        return False
    return True


def is_symbolic(icon: Gtk.IconPaintable) -> bool:
    """Symbolic icons are single-colour stencils and have to be recoloured
    when drawn, or they render as flat mid-grey on the tile."""
    icon_file = icon.get_file()
    path = icon_file.get_path() if icon_file is not None else None
    return bool(path and path.endswith("-symbolic.svg"))

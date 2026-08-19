# SPDX-License-Identifier: GPL-3.0-or-later
"""Every shipped icon must actually load (§6.11).

This exists because of a failure with no symptom other than absence: a long
XML comment between the `<?xml?>` declaration and `<svg>` pushes the element
past gdk-pixbuf's format-sniffing window, the loader refuses the file
outright, and the icon silently doesn't appear anywhere in the shell.
Nothing warns, nothing logs, and `gtk4-update-icon-cache` is perfectly happy
with it.

Loading through GdkPixbuf specifically, because that is the path GNOME Shell
takes — `Gtk.IconPaintable` rendered the broken file quite happily, which is
how it survived a visual check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

gi = pytest.importorskip("gi")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

ICON_DIR = Path(__file__).resolve().parent.parent / "data" / "icons"
ICONS = sorted(ICON_DIR.rglob("*.svg"))


def test_there_are_icons_to_check() -> None:
    assert ICONS, f"no icons found under {ICON_DIR}"


@pytest.mark.parametrize("path", ICONS, ids=lambda p: p.name)
def test_icon_loads_through_gdk_pixbuf(path: Path) -> None:
    if "svg" not in {fmt.get_name() for fmt in GdkPixbuf.Pixbuf.get_formats()}:
        pytest.skip("no gdk-pixbuf SVG loader on this system")
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), 128, 128)
    assert pixbuf.get_width() > 0
    assert pixbuf.get_height() > 0


@pytest.mark.parametrize("path", ICONS, ids=lambda p: p.name)
def test_svg_element_is_within_the_sniffing_window(path: Path) -> None:
    """The direct form of the same rule, so a failure says *why* rather than
    just 'could not recognise the file format'."""
    head = path.read_bytes()[:256]
    assert b"<svg" in head, (
        f"{path.name}: <svg> must appear in the first 256 bytes. Put "
        "explanatory comments inside the element, not before it."
    )

# SPDX-License-Identifier: GPL-3.0-or-later
"""A QR matrix as a widget.

`core/qr.py` has been finished and tested since the pairing screen was
built, and deliberately left unwired — the hint showed the URL and the code
as text, and typing `http://192.168.1.151:8437` into a phone is a small
enough imposition to defer. It stopped being small when the phone became
the *remote*: the URL is now something people will open regularly rather
than once while adding a bookmark, and reading four dotted numbers off a
television across a room is exactly the kind of task this replaces.

Drawn as rectangles in `do_snapshot` rather than rendered to an image,
because a QR code is squares: at any scale, one `append_color` per dark
module is both sharper than a bitmap and less code than generating one.

The quiet zone is not optional. The specification requires four modules of
light around the symbol, and scanners genuinely fail without it — against a
dark interface, a code drawn flush to its own edge is one no phone will
read.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")

from gi.repository import Gdk, Graphene, Gtk  # noqa: E402

from salon.core import qr  # noqa: E402

_QUIET_MODULES = 4


def _rgba(value: float) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red = color.green = color.blue = value
    color.alpha = 1.0
    return color


_LIGHT = _rgba(1.0)
_DARK = _rgba(0.0)


class QrCode(Gtk.Widget):
    """Square, sized by `set_size`, showing whatever `set_text` was given."""

    def __init__(self, size_px: int = 240) -> None:
        super().__init__()
        self._matrix: qr.Matrix | None = None
        self._size = size_px
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.set_visible(False)
        # The URL beside it is the accessible form; a screen reader has no
        # use for a picture of one.
        self.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)

    def set_size(self, size_px: int) -> None:
        self._size = max(1, size_px)
        self.set_size_request(self._size, self._size)
        self.queue_resize()

    def set_text(self, text: str) -> None:
        """Show a code for `text`, or nothing if it cannot be encoded.

        Failing quietly is right here: the URL is printed beside this, so a
        payload too long for version 6 costs the convenience and not the
        instructions.
        """
        if not text:
            self._matrix = None
            self.set_visible(False)
            return
        try:
            self._matrix = qr.encode(text)
        except qr.QREncodeError:
            self._matrix = None
            self.set_visible(False)
            return
        self.set_visible(True)
        self.queue_draw()

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        return (self._size, self._size, -1, -1)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        matrix = self._matrix
        if matrix is None:
            return
        width = float(self.get_width())
        height = float(self.get_height())
        side = min(width, height)
        if side <= 0:
            return

        modules = len(matrix) + 2 * _QUIET_MODULES
        # Floored to a whole number of pixels per module: a fractional
        # module size makes neighbouring squares round differently and
        # leaves seams a scanner reads as noise.
        scale = max(1.0, float(int(side / modules)))
        drawn = scale * modules
        # Floored, not merely centred. A whole number of pixels per module
        # is not enough on its own: an odd amount of slack puts the origin
        # on a half-pixel, every module edge picks up a grey antialiased
        # column, and a strict decoder then refuses the whole symbol —
        # measured, with libzbar, against a capture of this widget. The
        # code looked perfect and read as nothing. Half a pixel of centring
        # is invisible; being unreadable is not.
        offset_x = float(int((width - drawn) / 2.0))
        offset_y = float(int((height - drawn) / 2.0))

        background = Graphene.Rect()
        background.init(offset_x, offset_y, drawn, drawn)
        snapshot.append_color(_LIGHT, background)

        for row, line in enumerate(matrix):
            run_start: int | None = None
            for column in range(len(line) + 1):
                dark = column < len(line) and line[column]
                if dark and run_start is None:
                    run_start = column
                elif not dark and run_start is not None:
                    # One rectangle per horizontal run rather than one per
                    # module: a version-6 code is 41x41, and runs cut the
                    # node count by roughly half for free.
                    rect = Graphene.Rect()
                    rect.init(
                        offset_x + (run_start + _QUIET_MODULES) * scale,
                        offset_y + (row + _QUIET_MODULES) * scale,
                        (column - run_start) * scale,
                        scale,
                    )
                    snapshot.append_color(_DARK, rect)
                    run_start = None

# SPDX-License-Identifier: GPL-3.0-or-later
"""Which surfaces are raised above the console chrome, and in what order.

`Gtk.Overlay` draws its children in the order they were added, so depth is
decided by construction order — which is decided by which setup stage
happens to build a widget, and those stages are ordered by their
dependencies rather than by what should be drawn on top of what. The
console chrome (the sidebar, the "Home" title, the top-bar buttons) is
already re-added after the content surfaces so it can outrank them; that
same move left three surfaces built *before* it stranded underneath.

What that cost, measured:

* The idle screen did not cover the screen. The clock card, the title and
  the five buttons stayed lit behind it indefinitely — the sidebar clock
  read the same peak luminance with the screensaver up as without it. Those
  are static, bright and in fixed positions, which is the exact thing that
  module exists to keep off an OLED panel.
* The launching overlay's 0.95 scrim covered the content and not the
  sidebar, so its hint — centred on the window, while its title is centred
  on the content area — crossed the sidebar's edge and rendered one
  sentence in two brightnesses. Measured: peak glyph luminance 114 to the
  left of the boundary against 163 to the right.
* The volume readout was under the chrome too, though it is the one
  control that acts on every surface.

A list here rather than three `remove_overlay`/`add_overlay` pairs written
out at the call site: this is a *rule* about depth, it is worth stating
once, and a test can hold it to its own invariants.

See DECISIONS 2026-09-04.
"""

from __future__ import annotations

# Root-owned chrome rather than children of Home or Apps: above both
# content surfaces, but below the dialogs and menus built after it.
CONSOLE_CHROME: tuple[str, ...] = (
    "_console_sidebar",
    "_home_title",
    "_status_bar",
)

# Bottom to top, and above everything above. Each name is an attribute on
# `HomeView`.
RAISED_ABOVE_CHROME: tuple[str, ...] = (
    # Above every menu and dialog: while an application is starting there is
    # nothing else worth reading.
    "_launching_overlay",
    # Above that: volume acts on the system's audio rather than on a window,
    # which is why the action router keeps it above the "something else is
    # in front" guards, and its readout has to be able to say so.
    "_osd",
    # Last of all. The idle screen is the only surface that has to cover
    # *everything* Salon draws, including whatever was left on screen.
    "_screensaver",
)

# The surface that must be on top of all of them, named so a test can say so
# without restating the tuple.
TOPMOST = "_screensaver"

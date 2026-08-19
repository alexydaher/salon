# SPDX-License-Identifier: GPL-3.0-or-later
"""The user's accent colour, applied at runtime (§6.8, Appearance).

Every other colour is a build-time token: `data/style/tokens.css` is
generated from `salon/core/tokens.py` and never changes while Salon runs.
The accent is the one exception, because the Appearance panel lets the user
pick it, and it has to reach two different worlds:

* everything styled in CSS (the focus states, the OSD bar, the menu
  selection) reads `@accent`, so a provider installed *above* tokens.css
  redefines that colour token;
* the tile's focus ring and the backdrop's light pool are drawn in
  `do_snapshot`, where CSS cannot reach at all, so they call `accent()`.

Keeping the second path a module-level function rather than a constructor
argument means a colour change reaches every already-built widget without
anyone having to thread it through — the widgets simply read the current
value the next time they draw.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402

# The bloom's alpha is fixed by the design system (tokens.py ships
# accent-bloom at 0.22); only the hue follows the user's choice.
_BLOOM_ALPHA = 0.22


def _parse(value: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(value)
    return color


_DEFAULT_ACCENT = _parse(tokens.color("accent"))
_accent = _DEFAULT_ACCENT


def accent() -> Gdk.RGBA:
    """The current accent, for code that draws outside CSS."""
    return _accent


def build_css(color: Gdk.RGBA) -> str:
    red, green, blue = (round(c * 255) for c in (color.red, color.green, color.blue))
    return (
        "/* Generated at runtime by salon/ui/theme.py — do not edit. */\n"
        f"@define-color accent rgb({red},{green},{blue});\n"
        f"@define-color accent-bloom rgba({red},{green},{blue},{_BLOOM_ALPHA});\n"
    )


class ThemeManager:
    """Owns the accent and the CSS provider carrying it. One per app."""

    def __init__(self, settings: Gio.Settings) -> None:
        self._settings = settings
        self._provider = Gtk.CssProvider()
        self._listeners: list[Callable[[], None]] = []
        self._installed = False

    def install(self, display: Gdk.Display) -> None:
        if self._installed:
            return
        # Above ScaleManager's provider, which is itself above salon.css:
        # this is the last word on what @accent means.
        Gtk.StyleContext.add_provider_for_display(
            display, self._provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2
        )
        self._installed = True
        self._settings.connect("changed::accent-color", lambda *_: self.reload())
        self.reload()

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def reload(self) -> None:
        global _accent
        color = Gdk.RGBA()
        # A hand-edited GSetting can hold anything; an unparseable value
        # falls back to the design default rather than leaving the ring
        # transparent, which would look like the focus indicator broke.
        if not color.parse(self._settings.get_string("accent-color").strip()):
            color = _DEFAULT_ACCENT
        _accent = color
        self._provider.load_from_string(build_css(color))
        for listener in list(self._listeners):
            listener()

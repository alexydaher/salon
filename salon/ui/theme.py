# SPDX-License-Identifier: GPL-3.0-or-later
"""The colours that can change while Salon is running (§6.8, Appearance).

`data/style/tokens.css` is generated from `salon/core/tokens.py` at build
time and is the design default. What the user picks — an accent, and one of
`tokens.PALETTES` — is layered over it here, and has to reach two different
worlds:

* everything styled in CSS reads `@accent`, `@surface-0` and the rest, so
  a provider installed *above* tokens.css redefines those colour tokens;
* the tile, the backdrop, the overlays and the idle screen draw themselves
  in `do_snapshot`, where CSS cannot reach at all, so they call `accent()`
  and `color()`.

Keeping the second path module-level functions rather than constructor
arguments means a colour change reaches every already-built widget without
anyone having to thread it through — the widgets simply read the current
value the next time they draw. They used to parse these once at import,
which is why changing a palette needed a restart and why this is a function
call per use rather than a constant.
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
_palette: dict[str, Gdk.RGBA] = {
    name: _parse(value) for name, value in tokens.palette(tokens.DEFAULT_PALETTE).items()
}


def accent() -> Gdk.RGBA:
    """The current accent, for code that draws outside CSS."""
    return _accent


def color(name: str) -> Gdk.RGBA:
    """A themed surface or text colour, for code that draws outside CSS.

    Falls back to the design default for anything the palette does not
    name, so a token added to tokens.py and not to the palettes renders in
    its designed colour rather than not at all.
    """
    found = _palette.get(name)
    return found if found is not None else _parse(tokens.color(name))


def build_css(color_value: Gdk.RGBA, palette: dict[str, str]) -> str:
    red, green, blue = (
        round(channel * 255)
        for channel in (color_value.red, color_value.green, color_value.blue)
    )
    lines = [
        "/* Generated at runtime by salon/ui/theme.py — do not edit. */",
        f"@define-color accent rgb({red},{green},{blue});",
        f"@define-color accent-bloom rgba({red},{green},{blue},{_BLOOM_ALPHA});",
    ]
    lines.extend(f"@define-color {name} {value};" for name, value in palette.items())
    return "\n".join(lines) + "\n"


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
        self._settings.connect("changed::theme", lambda *_: self.reload())
        self.reload()

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def reload(self) -> None:
        global _accent, _palette
        chosen = Gdk.RGBA()
        # A hand-edited GSetting can hold anything; an unparseable value
        # falls back to the design default rather than leaving the ring
        # transparent, which would look like the focus indicator broke.
        if not chosen.parse(self._settings.get_string("accent-color").strip()):
            chosen = _DEFAULT_ACCENT
        _accent = chosen
        palette = tokens.palette(self._settings.get_string("theme"))
        _palette = {name: _parse(value) for name, value in palette.items()}
        self._provider.load_from_string(build_css(chosen, palette))
        for listener in list(self._listeners):
            listener()

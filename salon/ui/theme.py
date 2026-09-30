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

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402

# `tile-background`: what colours a card that has no artwork of its own.
TILE_BACKGROUND_ICON = "icon"
TILE_BACKGROUND_UNIFORM = "uniform"

# `accent-color`: the one value that is not a colour. It means "whatever
# GNOME Settings → Appearance says", read live through Adw.StyleManager.
SYSTEM_ACCENT = "system"


def _parse(value: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(value)
    return color


_DEFAULT_ACCENT = _parse(tokens.color("accent"))
_accent = _DEFAULT_ACCENT
_palette: dict[str, Gdk.RGBA] = {
    name: _parse(value) for name, value in tokens.palette(tokens.DEFAULT_PALETTE).items()
}
_tile_background = TILE_BACKGROUND_ICON


def accent() -> Gdk.RGBA:
    """The current accent, for code that draws outside CSS."""
    return _accent


def _hex(color_value: Gdk.RGBA) -> str:
    channels = (color_value.red, color_value.green, color_value.blue)
    return "#{:02X}{:02X}{:02X}".format(*(round(channel * 255) for channel in channels))


def accent_hex() -> str:
    """The current accent as `#RRGGBB`, for the phone, which cannot be
    handed the word "system" and has to draw the colour itself."""
    return _hex(_accent)


def system_accent_supported() -> bool:
    """Whether this libadwaita can report GNOME's accent (1.6+) and the
    platform actually has one to report."""
    manager = Adw.StyleManager.get_default()
    probe = getattr(manager, "get_system_supports_accent_colors", None)
    return bool(probe and probe())


def _system_accent() -> Gdk.RGBA | None:
    if not system_accent_supported():
        return None
    return Adw.StyleManager.get_default().get_accent_color_rgba()


def system_accent_hex() -> str:
    """GNOME's accent as `#RRGGBB`, or "" where there is none to report."""
    found = _system_accent()
    return _hex(found) if found is not None else ""


def tiles_take_their_icon_colour() -> bool:
    """Whether a card with no artwork is tinted by the icon drawn on it.

    A taste question with a real cost either way, so it is the user's.
    Tinted, a row of tiles reads as several different things across a room
    — which is what the shipped catalogue needs, since five of its streaming
    tiles are the same shape of card and differ only by their mark. Uniform,
    the rows have an even rhythm and the icons carry the identity on their
    own, which is the quieter composition and the one the Aurora console was
    drawn as. Tiles with real artwork are unaffected by either.

    Read at draw time like `accent()` and `color()`, so changing it reaches
    every already-built widget without anyone threading it through.
    """
    return _tile_background == TILE_BACKGROUND_ICON


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
        round(channel * 255) for channel in (color_value.red, color_value.green, color_value.blue)
    )
    lines = [
        "/* Generated at runtime by salon/ui/theme.py — do not edit. */",
        f"@define-color accent rgb({red},{green},{blue});",
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
        style = Adw.StyleManager.get_default()
        # Salon is always dark, whatever the desktop is. Its own surfaces
        # come from the palette, but the few stock libadwaita widgets it
        # uses — toasts, a file picker — follow the system scheme and would
        # arrive light over a dark screen.
        style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        if system_accent_supported():
            style.connect("notify::accent-color", lambda *_: self._on_system_accent())
        self._settings.connect("changed::accent-color", lambda *_: self.reload())
        self._settings.connect("changed::theme", lambda *_: self.reload())
        self._settings.connect("changed::tile-background", lambda *_: self.reload())
        self.reload()

    def _on_system_accent(self) -> None:
        if self._settings.get_string("accent-color") == SYSTEM_ACCENT:
            self.reload()

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def reload(self) -> None:
        global _accent, _palette, _tile_background
        chosen = Gdk.RGBA()
        requested = self._settings.get_string("accent-color").strip()
        if requested == SYSTEM_ACCENT:
            # On a libadwaita too old to say, or a platform with no accent,
            # the design default rather than nothing.
            chosen = _system_accent() or _DEFAULT_ACCENT
        # A hand-edited GSetting can hold anything; an unparseable value
        # falls back to the design default rather than leaving the ring
        # transparent, which would look like the focus indicator broke.
        elif not chosen.parse(requested):
            chosen = _DEFAULT_ACCENT
        _accent = chosen
        palette = tokens.palette(self._settings.get_string("theme"))
        _palette = {name: _parse(value) for name, value in palette.items()}
        # Anything but the one recognised alternative means the default, on
        # the same grounds as the accent above: a hand-edited GSetting can
        # hold any string and a card has to be drawn either way.
        _tile_background = (
            TILE_BACKGROUND_UNIFORM
            if self._settings.get_string("tile-background") == TILE_BACKGROUND_UNIFORM
            else TILE_BACKGROUND_ICON
        )
        self._provider.load_from_string(build_css(chosen, palette))
        for listener in list(self._listeners):
            listener()

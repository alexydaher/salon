# SPDX-License-Identifier: GPL-3.0-or-later
"""The du -> px runtime pipeline (§7.2).

`core/tokens.py` holds every size in design units, where 1du =
viewport_height / 1080. This module resolves them to pixels once the target
monitor's geometry is known, and pushes the results into GTK two ways:

* as CSS custom properties on `:root`, loaded at PRIORITY_APPLICATION after
  the build-time `tokens.css`, so `salon.css` can be written entirely in
  `var(--…)` and never contain a raw px value (a gate in §10, enforced by
  tests/test_css_has_no_raw_px.py);
* as plain floats via `Scale.du()`, for the widget geometry CSS can't
  express — tile sizes, gaps, row spacing, anything set from Python.

Monitor geometry is reported in *logical* pixels, which is what we want: on
a 4K TV that the compositor already scales 2x, geometry height is 1080 and
du is 1.0 because GTK is doing the scaling for us; on a 4K TV running
unscaled, geometry height is 2160 and du is 2.0 because nobody else will.

The scale is recomputed when the window moves between monitors or a monitor
changes mode; listeners registered with `subscribe()` rebuild the geometry
they derived from it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402


@dataclass(frozen=True, slots=True)
class Scale:
    """An immutable du -> px conversion for one viewport height."""

    viewport_height_px: int

    @property
    def factor(self) -> float:
        return self.viewport_height_px / tokens.REFERENCE_VIEWPORT_HEIGHT_PX

    def du(self, value: float) -> float:
        return tokens.design_units_to_px(value, self.viewport_height_px)

    def px(self, value: float) -> int:
        return round(self.du(value))


_DEFAULT_SCALE = Scale(int(tokens.REFERENCE_VIEWPORT_HEIGHT_PX))


def build_css(scale: Scale) -> str:
    """Every du-derived token, resolved to px as CSS custom properties.

    Colours and font families deliberately aren't here — those don't depend
    on viewport size and come from the build-time tokens.css instead.
    """
    lines = ["/* Generated at runtime by salon/ui/scale.py — do not edit. */", ":root {"]
    lines.append(f"  --radius: {scale.du(tokens.CORNER_RADIUS_DU):.1f}px;")
    lines.append(f"  --radius-lg: {scale.du(tokens.CORNER_RADIUS_DU * 1.75):.1f}px;")
    # Not a size: the "round the ends completely" sentinel for pill shapes,
    # which is resolution-independent by definition. It lives here rather
    # than in salon.css so the stylesheet can stay free of literal px and
    # the §10 gate that enforces that stays meaningful.
    lines.append("  --radius-pill: 9999px;")
    lines.append(f"  --tile-gap: {scale.du(tokens.TILE_GAP_DU):.1f}px;")
    lines.append(f"  --row-gap: {scale.du(tokens.ROW_GAP_DU):.1f}px;")
    lines.append(f"  --heading-gap: {scale.du(tokens.ROW_HEADING_GAP_DU):.1f}px;")
    lines.append(f"  --focus-ring: {scale.du(tokens.FOCUS_RING_DU):.1f}px;")
    lines.append(f"  --pad-s: {scale.du(12.0):.1f}px;")
    lines.append(f"  --pad-m: {scale.du(24.0):.1f}px;")
    lines.append(f"  --pad-l: {scale.du(40.0):.1f}px;")
    for token in tokens.TYPE_SCALE:
        lines.append(f"  --font-{token.name}: {scale.du(token.size_du):.1f}px;")
        lines.append(f"  --weight-{token.name}: {token.weight};")
    lines.append("}")
    return "\n".join(lines) + "\n"


class ScaleManager:
    """Owns the current Scale and the CSS provider carrying it.

    One instance lives on the application; the window hands it a surface
    once it's realized so the right monitor can be found.
    """

    def __init__(self) -> None:
        self._scale = _DEFAULT_SCALE
        self._provider = Gtk.CssProvider()
        self._listeners: list[Callable[[Scale], None]] = []
        self._monitor: Gdk.Monitor | None = None
        self._installed = False

    @property
    def scale(self) -> Scale:
        return self._scale

    def install(self, display: Gdk.Display) -> None:
        if self._installed:
            return
        Gtk.StyleContext.add_provider_for_display(
            display, self._provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        self._installed = True
        self._reload_css()

    def subscribe(self, listener: Callable[[Scale], None]) -> None:
        self._listeners.append(listener)

    def track_surface(self, surface: Gdk.Surface) -> None:
        """Follow whichever monitor `surface` is on, recomputing on change."""
        display = surface.get_display()
        monitors = display.get_monitors()
        monitors.connect("items-changed", lambda *_: self._update_for_surface(surface))
        self._update_for_surface(surface)

    def _update_for_surface(self, surface: Gdk.Surface) -> None:
        display = surface.get_display()
        monitor = display.get_monitor_at_surface(surface)
        if monitor is None:
            monitors = display.get_monitors()
            monitor = monitors.get_item(0) if monitors.get_n_items() else None
        if monitor is None:
            return
        if self._monitor is not monitor:
            self._monitor = monitor
            monitor.connect("notify::geometry", lambda *_: self._apply_monitor(monitor))
        self._apply_monitor(monitor)

    def _apply_monitor(self, monitor: Gdk.Monitor) -> None:
        height = monitor.get_geometry().height
        if height <= 0:
            return
        scale = Scale(height)
        if scale == self._scale:
            return
        self._scale = scale
        self._reload_css()
        for listener in list(self._listeners):
            listener(scale)

    def _reload_css(self) -> None:
        self._provider.load_from_string(build_css(self._scale))

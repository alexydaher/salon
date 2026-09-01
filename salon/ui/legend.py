# SPDX-License-Identifier: GPL-3.0-or-later
"""The button legend: what the buttons do *here*, in this device's words.

Split out of `ui/detailbar.py`, where it was the third line of a widget
whose job is describing the selected tile. That put two unrelated things on
one clock: the legend was re-rendered on every cursor move to say something
that had not changed, and it could only ever be a property of the
selection, when what it is really a property of is the *mode* — the top bar
holds the cursor, or a menu is open, or the tiles do.

Two things it does that the old line could not:

* **It shows the button rather than the intent.** `core/buttons.py` turns
  (action, source) into the control on the device that most recently sent a
  press, so the same hint uses a square mark on a DualSense, a ringed X on
  an Xbox pad and the letter O on a keyboard. The source is tracked because
  a living room has more than one.
* **It changes with the mode and nothing else**, so it holds still while a
  held direction races through a row.

Bottom-right, which is where the eye goes for "what can I press" and where
`ui/remotehint.py` already stood — that card now sits one legend-height
higher so the two never share a pixel.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core import buttons, tokens  # noqa: E402
from salon.core.actions import Action  # noqa: E402
from salon.core.bindings import CEC  # noqa: E402
from salon.ui.controller_glyph import ControllerGlyph, ControllerGlyphWidget  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

# One hint: the button presentation, and what it does right now.
LegendKey = str | Action | ControllerGlyph
Hint = tuple[LegendKey, str]


class Legend(Gtk.Box):
    """A row of (button, meaning) pairs pinned to the bottom-right."""

    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("salon-legend")
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.END)
        # Natural width, at the end of the bottom row. The detail strip
        # beside it is the one that expands, so the pair divide the band
        # between them rather than competing for the same pixels.
        self.set_hexpand(False)
        # Reports, never acts: a transparent overlay child that took clicks
        # would swallow every press meant for the tile underneath it.
        self.set_can_target(False)
        # The container that owns the cursor announces what OK will do; a
        # second reading of the same thing is noise in a screen reader.
        self.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)

        self._hints: tuple[Hint, ...] = ()
        self._input_source = CEC
        self._gamepad_family = buttons.GENERIC
        self._scale = scale
        self.set_scale(scale)

    def set_input_device(self, source: str, family: str = buttons.GENERIC) -> None:
        """Repaint semantic action keys for the device currently in use."""
        state = (source, family)
        if state == (self._input_source, self._gamepad_family):
            return
        self._input_source, self._gamepad_family = state
        self._rebuild()

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self.set_spacing(scale.px(20.0))
        self.set_margin_end(scale.safe_margin_px)
        self.set_margin_bottom(scale.px(tokens.BOTTOM_CHROME_MARGIN_DU))
        self._rebuild()

    def set_hints(self, hints: tuple[Hint, ...]) -> None:
        """Replace the row. A no-op when nothing changed, which is the
        common case: this is called after every press, and the mode it
        describes changes on very few of them."""
        hints = tuple((key, meaning) for key, meaning in hints if key and meaning)
        if hints == self._hints:
            return
        self._hints = hints
        self._rebuild()

    def _rebuild(self) -> None:
        child = self.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.remove(child)
            child = next_child
        for key, meaning in self._hints:
            self.append(self._make_hint(key, meaning))
        self.set_visible(bool(self._hints))

    def _present_key(self, key: LegendKey) -> str | ControllerGlyph:
        if not isinstance(key, Action):
            return key
        label = buttons.label(key, self._input_source, family=self._gamepad_family)
        glyph = buttons.glyph(key, self._input_source, family=self._gamepad_family)
        if glyph:
            return ControllerGlyph(glyph, label)
        return label.upper() if self._input_source == CEC else label

    def _make_hint(self, key: LegendKey, meaning: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(self._scale.px(8.0))
        cap = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        cap.add_css_class("salon-legend-key")
        presented = self._present_key(key)
        if isinstance(presented, ControllerGlyph) and ControllerGlyphWidget.supports(
            presented.name
        ):
            cap.append(ControllerGlyphWidget(presented.name, self._scale))
        else:
            fallback = presented.fallback if isinstance(presented, ControllerGlyph) else presented
            cap.append(Gtk.Label(label=fallback))
        box.append(cap)
        label = Gtk.Label(label=meaning)
        label.add_css_class("salon-legend-meaning")
        box.append(label)
        return box

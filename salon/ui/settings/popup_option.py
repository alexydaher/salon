# SPDX-License-Identifier: GPL-3.0-or-later
"""The choice card and range slider used by a `ValuePopup`."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.indicators import Swatch  # noqa: E402

_CHECK_GLYPH = "✓"


class ValueOption(Gtk.Button):
    """A label, a colour when the value is one, and a tick when it is set.

    A Gtk.Button so a click and a hover come for free; the remote never
    touches these directly — `ValuePopup` drives the selection and this
    only reports what the pointer did.

    The swatch is why the accent list stopped being four words about
    colours: "Ember", "Cold blue" and "Violet" describe a palette nobody
    can see, and this is the screen where the choice is actually made.
    """

    def __init__(
        self,
        scale: Scale,
        label: str,
        *,
        current: bool,
        index: int,
        height: int,
        on_click: Callable[[int], None],
        on_hover: Callable[[int], None],
        swatch: str = "",
        preview: bool = False,
    ) -> None:
        super().__init__()
        self.add_css_class("salon-value-option")
        self.set_size_request(-1, height)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL if preview else Gtk.Orientation.HORIZONTAL
        )
        box.set_spacing(scale.px(6.0 if preview else 12.0))
        if swatch:
            chip = Swatch()
            if preview:
                chip.set_hexpand(True)
                chip.set_size_request(-1, scale.px(44.0))
            else:
                chip.set_metrics(scale.px(30.0))
            chip.set_color(swatch)
            box.append(chip)
        text = Gtk.Label(label=label)
        text.set_halign(Gtk.Align.CENTER if preview else Gtk.Align.START)
        text.set_hexpand(True)
        text.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(text)
        # A tick on the value that is already set, always present so the
        # labels do not shift sideways as the cursor moves, and invisible
        # rather than absent on the rest.
        tick = Gtk.Label(label="CURRENT" if preview else _CHECK_GLYPH)
        tick.add_css_class("salon-value-option-tick")
        tick.set_opacity(1.0 if current else 0.0)
        box.append(tick)
        self.set_child(box)

        self.connect("clicked", lambda _b: on_click(index))
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_: on_hover(index))
        self.add_controller(motion)


class RangePreview(Gtk.Box):
    """One horizontal range instead of a card for every numeric step.

    Controller input is still owned by :class:`ValuePopup`; the native
    scale is here so pointer users may click or drag to the same candidate.
    Moving the thumb previews a value but does not commit it -- OK and BACK
    keep the same promises as the choice cards.
    """

    def __init__(
        self,
        scale: Scale,
        labels: list[str],
        selected: int,
        on_change: Callable[[int], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-preview-range")
        self.set_hexpand(True)
        self._labels = labels
        self._on_change = on_change
        self._syncing = False

        self._value = Gtk.Label()
        self._value.add_css_class("salon-preview-range-value")
        self._value.set_halign(Gtk.Align.CENTER)
        self.append(self._value)

        maximum = max(0, len(labels) - 1)
        self._slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, float(maximum), 1.0
        )
        self._slider.add_css_class("salon-preview-slider")
        self._slider.set_draw_value(False)
        self._slider.set_digits(0)
        self._slider.set_has_origin(True)
        self._slider.set_hexpand(True)
        self._slider.set_can_focus(False)
        self._slider.connect("value-changed", self._changed)
        self.append(self._slider)

        ends = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        low = Gtk.Label(label=labels[0] if labels else "")
        low.set_halign(Gtk.Align.START)
        low.set_hexpand(True)
        high = Gtk.Label(label=labels[-1] if labels else "")
        high.set_halign(Gtk.Align.END)
        ends.append(low)
        ends.append(high)
        ends.add_css_class("salon-preview-range-ends")
        self.append(ends)

        self.set_scale(scale)
        self.set_selected(selected)

    def set_scale(self, scale: Scale) -> None:
        self.set_size_request(-1, scale.px(122.0))
        self.set_spacing(scale.px(2.0))
        self.set_margin_start(scale.px(18.0))
        self.set_margin_end(scale.px(18.0))

    def set_selected(self, index: int) -> None:
        if not self._labels:
            return
        index = min(len(self._labels) - 1, max(0, index))
        self._value.set_label(self._labels[index])
        if round(self._slider.get_value()) == index:
            return
        self._syncing = True
        self._slider.set_value(float(index))
        self._syncing = False

    def _changed(self, slider: Gtk.Scale) -> None:
        if self._syncing or not self._labels:
            return
        index = min(len(self._labels) - 1, max(0, round(slider.get_value())))
        self._value.set_label(self._labels[index])
        self._on_change(index)

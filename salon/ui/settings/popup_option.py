# SPDX-License-Identifier: GPL-3.0-or-later
"""One value inside a `ValuePopup` list."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402

_CHECK_GLYPH = "✓"


class ValueOption(Gtk.Button):
    """A label, and a tick when this is the value currently set.

    A Gtk.Button so a click and a hover come for free; the remote never
    touches these directly — `ValuePopup` drives the selection and this
    only reports what the pointer did.
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
    ) -> None:
        super().__init__()
        self.add_css_class("salon-value-option")
        self.set_size_request(-1, height)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(scale.px(12.0))
        text = Gtk.Label(label=label)
        text.set_halign(Gtk.Align.START)
        text.set_hexpand(True)
        text.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(text)
        # A tick on the value that is already set, always present so the
        # labels do not shift sideways as the cursor moves, and invisible
        # rather than absent on the rest.
        tick = Gtk.Label(label=_CHECK_GLYPH)
        tick.add_css_class("salon-value-option-tick")
        tick.set_opacity(1.0 if current else 0.0)
        box.append(tick)
        self.set_child(box)

        self.connect("clicked", lambda _b: on_click(index))
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_: on_hover(index))
        self.add_controller(motion)

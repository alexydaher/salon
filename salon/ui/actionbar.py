# SPDX-License-Identifier: GPL-3.0-or-later
"""Structured selection text and control legend for bottom action bars."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui.legend import Hint, Legend  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class SelectionActionBar(Gtk.Box):
    def __init__(self, scale: Scale, hints: tuple[Hint, ...]) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("salon-bottom-bar")
        self._selection = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._selection.set_hexpand(True)
        self._selection.set_valign(Gtk.Align.CENTER)
        self.append(self._selection)
        self._title = Gtk.Label()
        self._title.add_css_class("salon-detail-title")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_valign(Gtk.Align.BASELINE)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        self._selection.append(self._title)
        self._detail = Gtk.Label()
        self._detail.add_css_class("salon-detail-body")
        self._detail.set_halign(Gtk.Align.START)
        self._detail.set_valign(Gtk.Align.BASELINE)
        self._detail.set_ellipsize(Pango.EllipsizeMode.END)
        self._detail.set_hexpand(True)
        self._selection.append(self._detail)
        self._legend = Legend(scale)
        self._legend.set_hints(hints)
        self.append(self._legend)
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_size_request(-1, scale.px(tokens.ACTION_BAR_HEIGHT_DU))
        self._selection.set_spacing(scale.px(16.0))
        self._selection.set_margin_start(scale.safe_margin_px)
        self._selection.set_margin_end(scale.px(24.0))
        self._legend.set_scale(scale)

    def set_selection(self, title: str, detail: str = "") -> None:
        """The selected item's name, and optionally a line about it.

        The detail label expands and the title does not, which is right
        when there is a detail and wrong when there is not: an ellipsizing
        label's *minimum* width is about one character, so under pressure
        from the legend the title collapsed to its minimum while an empty
        label beside it held the rest of the band. The all-apps grid never
        passes a detail, and its selected application rendered as `Adv…`
        with 200px of empty band next to it. So the detail only takes part
        when it has something to say, and the title expands when it does
        not.
        """
        self._title.set_label(title)
        self._detail.set_label(detail)
        self._detail.set_visible(bool(detail))
        self._title.set_hexpand(not detail)

    def set_hints(self, hints: tuple[Hint, ...]) -> None:
        self._legend.set_hints(hints)

    def set_input_device(self, source: str, family: str) -> None:
        self._legend.set_input_device(source, family)

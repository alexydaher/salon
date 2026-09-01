# SPDX-License-Identifier: GPL-3.0-or-later
"""Everything a settings row draws, as one widget the row owns.

Split out of `settings_row.py` rather than mixed into it: the row is a
state machine (selected, adjusting, denied, unavailable) with a behaviour
contract on top, and the arrangement of eight child widgets is a separate
job that was making one file impossible to read. This is a collaborator,
not a mixin — it knows nothing about actions, values or GSettings, and the
row never reaches past it to a child.

Left to right: a modified dot, an optional section icon, the label with its
detail line under it, then the value — which is a string, or a switch, or a
colour chip, or a meter, or a string with one of those beside it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import GLib, Gtk, Pango  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.indicators import Meter, Swatch, Switch  # noqa: E402

# The affordance a row with a list of values draws, so "opens a list" is
# visible without pressing anything. Dim until the row is selected.
DROPDOWN_GLYPH = "⌄"
_DROPDOWN_ALPHA = {True: "70%", False: "22%"}
# A row that leaves Salon. Named in the detail line too — the glyph is the
# thing you can see from the sofa, the words are what confirm it.
EXTERNAL_GLYPH = "↗"


class RowContent(Gtk.Box):
    def __init__(self, label: str, detail: str, icon_name: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)

        # Presentation, not content: it is always allocated in a list that
        # has any resettable row (see `reserve_dot`), so a screen reader
        # would otherwise announce a bullet on every row in the panel.
        self._dot = Gtk.Label(label="•", accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self._dot.add_css_class("salon-settings-dot")
        self._dot.set_can_target(False)
        self._dot.set_visible(False)
        self._dot.set_opacity(0.0)
        self.append(self._dot)

        self._icon: Gtk.Image | None = None
        if icon_name:
            self._icon = Gtk.Image.new_from_icon_name(icon_name)
            self._icon.add_css_class("salon-settings-icon")
            self._icon.set_valign(Gtk.Align.CENTER)
            self.append(self._icon)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text.set_hexpand(True)
        # Centred, not filled: a one-line row would otherwise sit at the top
        # of its box while the value beside it centred, and the two would
        # read as belonging to different rows.
        text.set_valign(Gtk.Align.CENTER)
        self.append(text)

        self._label = Gtk.Label(label=label)
        self._label.set_halign(Gtk.Align.START)
        self._label.set_ellipsize(Pango.EllipsizeMode.END)
        self._label.add_css_class("salon-settings-label")
        text.append(self._label)

        self._detail = Gtk.Label(label=detail)
        self._detail.set_halign(Gtk.Align.START)
        self._detail.set_ellipsize(Pango.EllipsizeMode.END)
        self._detail.add_css_class("salon-settings-detail")
        self._detail.set_visible(bool(detail))
        text.append(self._detail)

        # Right-aligned, and the row itself is capped (`SettingsRow.
        # set_content_width`) rather than this column being given a width.
        # A size request here is a *minimum*, and 330du of it made every row
        # too wide for the 420du sections column to measure.
        self._column = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._column.set_halign(Gtk.Align.END)
        self._column.set_valign(Gtk.Align.CENTER)
        self.append(self._column)

        self._meter = Meter()
        self._meter.set_visible(False)
        self._column.append(self._meter)

        self._swatch = Swatch()
        self._swatch.set_visible(False)
        self._column.append(self._swatch)

        self._value = Gtk.Label(label="")
        self._value.set_halign(Gtk.Align.END)
        self._value.set_valign(Gtk.Align.CENTER)
        self._value.set_ellipsize(Pango.EllipsizeMode.END)
        self._value.add_css_class("salon-settings-value")
        self._column.append(self._value)

        self._switch = Switch()
        self._switch.set_visible(False)
        self._column.append(self._switch)

    # --- text ------------------------------------------------------------

    @property
    def label_text(self) -> str:
        return self._label.get_label() or ""

    @property
    def detail_text(self) -> str:
        return self._detail.get_label() or ""

    def set_label_text(self, text: str) -> None:
        self._label.set_label(text)

    def set_detail(self, text: str) -> None:
        self._detail.set_label(text)
        self._detail.set_visible(bool(text))

    def render_value(self, text: str, *, has_list: bool, selected: bool, muted: bool) -> None:
        """The value, with the dropdown affordance when there is a list.

        Markup rather than a second label so the glyph keeps its space at
        both opacities and the text beside it never shifts as the cursor
        moves onto the row.
        """
        self._value.set_visible(bool(text))
        if muted:
            self._value.add_css_class("muted")
        else:
            self._value.remove_css_class("muted")
        if not has_list:
            self._value.set_use_markup(False)
            self._value.set_text(text)
            return
        alpha = _DROPDOWN_ALPHA[selected]
        escaped = GLib.markup_escape_text(text)
        self._value.set_markup(f"{escaped} <span alpha='{alpha}'>{DROPDOWN_GLYPH}</span>")

    # --- the drawn affordances -------------------------------------------

    def set_switch(self, on: bool | None) -> None:
        self._switch.set_visible(on is not None)
        if on is not None:
            self._switch.set_on(on)

    def set_swatch(self, spec: str) -> bool:
        return self._swatch.set_color(spec)

    def set_meter(self, fraction: float | None) -> None:
        self._meter.set_visible(fraction is not None)
        if fraction is not None:
            self._meter.set_fraction(fraction)

    def set_modified(self, modified: bool) -> None:
        """A dot in the margin on a row that no longer holds what Salon
        shipped. The alternative is reading the whole screen and knowing
        the defaults, which nobody does.

        Opacity, not visibility: a hidden box child takes no space, so the
        dot used to push its own label 38du right of every neighbour's —
        measured at 579px against 541px in Appearance, which is a ragged
        left edge on precisely the rows meant to catch the eye.
        `reserve_dot` is what decides whether the space is there at all.
        """
        self._dot.set_opacity(1.0 if modified else 0.0)

    def reserve_dot(self, reserve: bool) -> None:
        """Whether this row keeps room for the dot whether or not it shows.

        A per-*list* decision, made in `SettingsList.set_rows`: within one
        list every row indents the same way or none does. The sections list
        has no resettable rows at all, and 38du of its 420du column is
        worth more than a gutter for a dot that can never appear there.
        """
        self._dot.set_visible(reserve)

    # --- geometry ---------------------------------------------------------

    @property
    def value_anchor(self) -> Gtk.Widget:
        """What a value list hangs off: the value, not the row. A row is
        most of the screen wide and a popup centred under one lands in the
        middle of nothing."""
        return self._value

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(20.0))
        self._column.set_spacing(scale.px(16.0))
        self._dot.set_size_request(scale.px(18.0), -1)
        self._switch.set_metrics(scale.px(72.0), scale.px(38.0))
        self._swatch.set_metrics(scale.px(38.0))
        self._meter.set_metrics(scale.px(120.0), scale.px(8.0))
        if self._icon is not None:
            self._icon.set_pixel_size(scale.px(34.0))

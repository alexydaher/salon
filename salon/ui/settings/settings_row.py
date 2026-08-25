# SPDX-License-Identifier: GPL-3.0-or-later
"""Base row widget for Salon's controller-friendly settings lists."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402

_DENY_FLASH_MS = 220
_DROPDOWN_GLYPH = "\u2304"
_DROPDOWN_ALPHA = {True: "70%", False: "22%"}

class SettingsRow(Gtk.Button):
    """Label on the left, current value on the right.

    A Gtk.Button rather than a Box so click, hover and keyboard activation
    all come for free; the D-pad path drives the same `activate()`.
    """

    def __init__(
        self,
        label: str,
        *,
        detail: str = "",
        danger: bool = False,
        icon_name: str = "",
        preview: bool = False,
    ) -> None:
        super().__init__()
        self.add_css_class("salon-settings-row")
        if danger:
            self.add_css_class("danger")
        self.set_hexpand(True)
        # Rows that change something you can only judge by looking at the
        # home screen (see SettingsScreen's preview strip). Marked on the
        # row rather than listed in the screen, so a new visual setting
        # opts in where it's declared instead of in a table somewhere else.
        self.previewable = preview
        self._raw_value = ""
        self._is_selected = False
        self._deny_source = 0

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(box)

        self._icon: Gtk.Image | None = None
        if icon_name:
            self._icon = Gtk.Image.new_from_icon_name(icon_name)
            self._icon.add_css_class("salon-settings-icon")
            self._icon.set_valign(Gtk.Align.CENTER)
            box.append(self._icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text_box.set_hexpand(True)
        # Centred, not filled: a one-line row would otherwise sit at the top
        # of its 72du box while the value beside it centred, and the two
        # would read as belonging to different rows.
        text_box.set_valign(Gtk.Align.CENTER)
        box.append(text_box)

        self._label = Gtk.Label(label=label)
        self._label.set_halign(Gtk.Align.START)
        self._label.set_ellipsize(Pango.EllipsizeMode.END)
        self._label.add_css_class("salon-settings-label")
        text_box.append(self._label)

        self._detail = Gtk.Label(label=detail)
        self._detail.set_halign(Gtk.Align.START)
        self._detail.set_ellipsize(Pango.EllipsizeMode.END)
        self._detail.add_css_class("salon-settings-detail")
        self._detail.set_visible(bool(detail))
        text_box.append(self._detail)

        self._value = Gtk.Label(label="")
        self._value.set_halign(Gtk.Align.END)
        self._value.set_valign(Gtk.Align.CENTER)
        self._value.set_ellipsize(Pango.EllipsizeMode.END)
        self._value.add_css_class("salon-settings-value")
        box.append(self._value)

        self._box = box

    # --- appearance ------------------------------------------------------

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")
        self._render_value()

    def set_list_open(self, open_: bool) -> None:
        """Whether this row's value list is on screen right now.

        EXPANDED rather than a bespoke state: to assistive technology a row
        with a list behind it is exactly a collapsed combo box, and that is
        the state a screen reader already knows how to announce.
        """
        self.update_state(
            [Gtk.AccessibleState.EXPANDED],
            [open_],
        )
        if open_:
            self.add_css_class("adjusting")
        else:
            self.remove_css_class("adjusting")

    def flash_denied(self) -> None:
        """RIGHT on a row with no inside, or a step past the end of a range.

        Silence at a boundary reads as a broken remote — the same reason the
        lists rubber-band vertically. There is no horizontal scroll here to
        bump, so the row itself blinks instead.
        """
        if self._deny_source:
            GLib.source_remove(self._deny_source)
        self.add_css_class("denied")
        self._deny_source = GLib.timeout_add(_DENY_FLASH_MS, self._end_deny_flash)

    def _end_deny_flash(self) -> bool:
        self._deny_source = 0
        self.remove_css_class("denied")
        return GLib.SOURCE_REMOVE

    @property
    def value_anchor(self) -> Gtk.Widget:
        """What a value list hangs off. The value label rather than the row,
        so the list opens where the thing it is about is written — a row is
        most of the screen wide, and a popup centred under one lands in the
        middle of nothing."""
        return self._value

    @property
    def label_text(self) -> str:
        return self._label.get_label() or ""

    @property
    def value_text(self) -> str:
        """The value itself, never the chevrons drawn around it."""
        return self._raw_value

    def set_label_text(self, text: str) -> None:
        self._label.set_label(text)
        self._render_value()

    def set_detail(self, text: str) -> None:
        self._detail.set_label(text)
        self._detail.set_visible(bool(text))

    def set_value(self, text: str) -> None:
        self._raw_value = text
        self._render_value()

    def _render_value(self) -> None:
        # The name a screen reader announces is composed from the child
        # labels, which would otherwise carry the ⌄ affordance and the alpha
        # span holding its space. Say the row instead.
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"{self.label_text}, {self._raw_value}" if self._raw_value else self.label_text],
        )
        if not self.choices:
            self._value.set_use_markup(False)
            self._value.set_text(self._raw_value)
            return
        alpha = _DROPDOWN_ALPHA[self._is_selected]
        text = GLib.markup_escape_text(self._raw_value)
        self._value.set_markup(f"{text}\u2002<span alpha='{alpha}'>{_DROPDOWN_GLYPH}</span>")

    def set_scale(self, scale: Scale) -> None:
        self._box.set_spacing(scale.px(24.0))
        self.set_size_request(-1, scale.px(72.0))
        if self._icon is not None:
            self._icon.set_pixel_size(scale.px(34.0))

    # --- behaviour -------------------------------------------------------

    @property
    def selectable(self) -> bool:
        return True

    @property
    def choices(self) -> list[tuple[str, str]]:
        """The values this row can take, as (key, label).

        Non-empty means OK raises the list rather than changing anything
        itself — see `ui/settings/popup.py`. The key is opaque to everything
        outside the row; only `current_choice` and `choose` interpret it.
        """
        return []

    @property
    def current_choice(self) -> str:
        """Which of `choices` is set, by key. Empty selects nothing."""
        return ""

    def choose(self, key: str) -> None:
        """Apply one of `choices`. Called from the popup, never directly."""

    @property
    def enterable(self) -> bool:
        """True for rows where RIGHT may safely do the thing directly: no
        list to raise, and nothing lost by a stray press."""
        return False

    @property
    def hint(self) -> str:
        """What the legend at the bottom of the screen says about this row."""
        return "A/OK selects"

    def activate_row(self) -> None:
        """OK, or a click."""

    def can_adjust(self, delta: int) -> bool:
        """Whether a step in this direction would change anything.

        With `choices` this only serves the preview strip, which is the one
        place LEFT/RIGHT still moves a value — there the point is watching
        the home screen change under it, not reading a list of numbers.
        """
        return False

    def adjust(self, delta: int) -> bool:
        """One step, for the preview strip. False if it ran off the end, so
        the caller can say so rather than doing nothing silently."""
        return False

    def refresh(self) -> None:
        """Re-read the underlying value. Called when the list is shown, so
        a row never displays state that changed elsewhere."""

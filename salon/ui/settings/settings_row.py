# SPDX-License-Identifier: GPL-3.0-or-later
"""One settings row: its state, and what the buttons do to it.

A `Gtk.Button` rather than a box, so click, hover and keyboard activation
come for free and the D-pad path drives the same `activate()`. What it
*draws* lives in `row_content.py`, and the contract every subtype
implements — with a harmless default for each of its questions — lives in
`row_contract.py`. What is left here is the state machine.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.row_content import RowContent  # noqa: E402
from salon.ui.settings.row_contract import RowContract  # noqa: E402

_DENY_FLASH_MS = 220
# How wide a row's own content may get, however wide the list is. Chosen so
# the label and the value stay one readable pair at 1080p, and — because it
# is in design units — the same pair at 4K rather than twice the distance.
_MAX_CONTENT_DU = 1250.0


class SettingsRow(Gtk.Button, RowContract):
    def __init__(
        self,
        label: str,
        *,
        detail: str = "",
        danger: bool = False,
        icon_name: str = "",
        preview: bool = False,
        external: bool = False,
        available: bool = True,
        unavailable_reason: str = "",
    ) -> None:
        super().__init__()
        self.add_css_class("salon-settings-row")
        if danger:
            self.add_css_class("danger")
        self.set_hexpand(True)
        # Rows that change something you can only judge by looking at the
        # home screen. Marked where the row is declared rather than listed
        # in the screen, so a new visual setting opts in beside itself.
        self.previewable = preview
        # Rows that leave Salon for gnome-control-center. "Display and
        # resolution" and "Shut Down" used to be the same shape of row.
        self.external = external
        self._raw_value = ""
        # What Salon shipped, for the subtypes that know it (`Keyed` reads
        # it off the schema). Declared here so `has_default` — and so the
        # modified dot's gutter — has one answer for every row subtype.
        self._default: object | None = None
        self._muted = False
        self._is_selected = False
        self._deny_source = 0
        self._scale: Scale | None = None
        self._allocated_width = 0
        self.available = available
        self.unavailable_reason = ""

        self._content = RowContent(label, detail, icon_name)
        self.set_child(self._content)
        if not available:
            self.make_unavailable(unavailable_reason)

    # --- appearance ------------------------------------------------------

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")
        self._render_value()

    def set_list_open(self, open_: bool) -> None:
        """Whether this row's value list is on screen right now. EXPANDED
        rather than a bespoke state: to assistive technology a row with a
        list behind it is exactly a collapsed combo box."""
        self.update_state([Gtk.AccessibleState.EXPANDED], [open_])
        if open_:
            self.add_css_class("adjusting")
        else:
            self.remove_css_class("adjusting")

    def flash_denied(self) -> None:
        """RIGHT on a row with no inside, or a step past a range's end.
        Silence at a boundary reads as a broken remote — the same reason the
        lists rubber-band; there is no horizontal scroll to bump here, so
        the row blinks instead."""
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
        return self._content.value_anchor

    @property
    def label_text(self) -> str:
        return self._content.label_text

    @property
    def detail_text(self) -> str:
        return self._content.detail_text

    @property
    def identity(self) -> str:
        """What this row *is*, across a rebuild that replaces every widget.

        Its label and its kind: "Favourites" is a switch in one group and a
        read-only diagnostic in another on the same panel, so the label
        alone is not enough. Used only to put the cursor back where it was
        — see `list_layout._rebuilt_selection`."""
        return f"{type(self).__name__}:{self.label_text}"

    @property
    def value_text(self) -> str:
        """The value itself, never the affordances drawn around it."""
        return self._raw_value

    def set_label_text(self, text: str) -> None:
        self._content.set_label_text(text)
        self._render_value()

    def set_detail(self, text: str) -> None:
        self._content.set_detail(text)

    def set_value(self, text: str, *, muted: bool = False) -> None:
        """`muted` is for a value that means *nothing is set*. The value
        column carries the accent, which on a row reading "Off" made the
        disabled state the brightest thing on screen."""
        self._raw_value = text
        self._muted = muted
        self._render_value()

    def _render_value(self) -> None:
        # The name a screen reader announces is composed from the child
        # labels, which would otherwise carry the ⌄ affordance and the alpha
        # span holding its space. Say the row instead.
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"{self.label_text}, {self._raw_value}" if self._raw_value else self.label_text],
        )
        self._content.render_value(
            self._raw_value,
            has_list=bool(self.choices),
            selected=self._is_selected,
            muted=self._muted,
        )
        self._content.set_modified(self.modified)

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._content.set_scale(scale)
        self.set_size_request(-1, scale.px(72.0))
        self.set_content_width(self._allocated_width)

    @property
    def has_default(self) -> bool:
        """Whether this row knows the value Salon shipped, and so whether
        it could ever carry the modified dot. Static for the life of the
        row, which is what lets a list reserve the gutter once."""
        return self._default is not None

    def set_dot_reserved(self, reserved: bool) -> None:
        self._content.reserve_dot(reserved)

    def set_content_width(self, width: int) -> None:
        """Cap how far apart the label and its value may sit.

        "Tile size" and "65%" were a thousand pixels apart at 1080p and two
        thousand on a 4K panel, which is not a pair anybody reads as one
        row. A margin rather than a width on the value column, because a
        size request is a *minimum* — one wide enough to fix this made
        every row too wide for the sections list to measure.
        """
        self._allocated_width = width
        cap = self._scale.px(_MAX_CONTENT_DU) if self._scale is not None else width
        self.set_margin_end(max(0, width - cap) if width > 0 else 0)

    # --- behaviour -------------------------------------------------------

    @property
    def selectable(self) -> bool:
        return self.available

    @property
    def actionable(self) -> bool:
        """Whether pressing anything here does something. The cursor lands
        on the first of these, not merely the first selectable row — see
        `settings_list._first_stop`."""
        return self.selectable

    def make_unavailable(self, reason: str) -> SettingsRow:
        self.available = False
        self.unavailable_reason = reason
        self.set_sensitive(False)
        self.add_css_class("unavailable")
        self.set_detail(reason)
        self.set_value("Unavailable", muted=True)
        return self

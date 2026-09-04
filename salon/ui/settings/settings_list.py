# SPDX-License-Identifier: GPL-3.0-or-later
"""Navigable and animated list of settings rows."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.ui.motion import AxisSpring  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.list_chrome import ListChrome  # noqa: E402
from salon.ui.settings.list_layout import (  # noqa: E402
    _first_stop,
    _rebuilt_selection,
    _selection_offset,
)
from salon.ui.settings.settings_row import SettingsRow  # noqa: E402


class SettingsList(Gtk.Fixed):
    """A vertically scrolling list of rows with a single selection.

    A Gtk.Fixed clipping around a taller box, translated by a spring — the
    same mechanism the home rows use rather than a Gtk.ScrolledWindow,
    because the selection drives the scroll here and not the reverse."""

    def __init__(self, scale: Scale) -> None:
        super().__init__()
        self.add_css_class("salon-settings-list")
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._scale = scale
        self._rows: list[SettingsRow] = []
        self._selected = 0
        # Whether the cursor is where the *user* put it. A panel that fills
        # in asynchronously rebuilds under an untouched cursor, and then
        # "keep the selection" means keeping a row nobody chose — see
        # `list_layout._rebuilt_selection`.
        self._pinned = False
        self._hover_enabled = False
        # Where a click goes. Unset it activates the row directly, which is
        # right for the sections list; the panel list hands this to the
        # screen so that a click and OK take the same path — a row with a
        # value list has nothing to "activate", and clicking one used to do
        # nothing at all.
        self._on_activate: Callable[[int], None] | None = None
        self._allocated_width = -1
        self._allocated_height = -1

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.put(self._content, 0, 0)
        self._scroll = AxisSpring(self, self._content, vertical=True)
        self._chrome = ListChrome(self)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        self._chrome.snapshot(snapshot, self._scale, self._content)

    def on_resize(self, width: int, height: int) -> None:
        """Fed by the `SizeReporter` this list is wrapped in.

        A Gtk.Fixed hands every child its own measured size and an
        ellipsized label measures one ellipsis wide, so the content box has
        to be told how wide the viewport actually is."""
        self._allocated_width = width
        self._allocated_height = height
        self._content.set_size_request(width, -1)
        for row in self._rows:
            row.set_content_width(width)
        gutter = self._chrome.layout(self._scale, width, height)
        # The top gutter comes and goes with its pill (`_scroll_to_selection`
        # owns it). The bottom one is always reserved: unlike the top, that
        # pill is there from the first frame of any over-long list.
        self._content.set_margin_bottom(gutter)
        # Only now is there a height to scroll within: set_rows runs before
        # the first allocation, or the list opens unscrolled.
        self._scroll_to_selection(animate=False)

    @property
    def rows(self) -> list[SettingsRow]:
        return self._rows

    @property
    def selected_index(self) -> int:
        return self._selected

    @property
    def selected_row(self) -> SettingsRow | None:
        if 0 <= self._selected < len(self._rows):
            return self._rows[self._selected]
        return None

    def set_hover_enabled(self, enabled: bool) -> None:
        self._hover_enabled = enabled

    def set_activate_handler(self, handler: Callable[[int], None] | None) -> None:
        self._on_activate = handler

    def set_active(self, active: bool) -> None:
        """Which of the two lists the cursor is actually in. The other one
        keeps its selection drawn, but dimmed: two full-strength highlights
        on screen leaves no answer to "what does OK do right now"."""
        if active:
            self.add_css_class("active")
        else:
            self.remove_css_class("active")

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._content.set_spacing(scale.px(6.0))
        for row in self._rows:
            row.set_scale(scale)

    def set_rows(self, rows: list[SettingsRow], *, keep_selection: bool = False) -> None:
        previous = self.selected_row
        previous_key = previous.identity if previous is not None else ""
        child = self._content.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._content.remove(child)
            child = next_child

        self._rows = rows
        # One decision for the whole list: either every row indents past a
        # dot gutter or none does. The sections list has no resettable rows
        # in it at all, and its column is the one already short of room for
        # the summaries — so it keeps no gutter for a dot that can never
        # appear there.
        reserve_dot = any(row.has_default for row in rows)
        for index, row in enumerate(rows):
            row.set_dot_reserved(reserve_dot)
            row.set_scale(self._scale)
            row.set_content_width(self._allocated_width)
            row.connect("clicked", lambda _b, i=index: self._click(i))
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", lambda *_, i=index: self._hover(i))
            row.add_controller(motion)
            self._content.append(row)

        kept = (
            _rebuilt_selection(
                [row.identity for row in rows],
                [row.selectable for row in rows],
                previous_key=previous_key,
                previous_index=self._selected,
                pinned=self._pinned,
            )
            if keep_selection
            else None
        )
        self._selected = _first_stop(rows) if kept is None else kept
        self._pinned = self._pinned and keep_selection
        self._content.set_spacing(self._scale.px(6.0))
        self._update_selection(animate=False)

    def refresh_values(self) -> None:
        for row in self._rows:
            row.refresh()

    def move(self, delta: int) -> bool:
        if not self._rows:
            return False
        target = self._selected + delta
        while 0 <= target < len(self._rows) and not self._rows[target].selectable:
            target += delta
        if not 0 <= target < len(self._rows):
            return False
        self._selected = target
        self._pinned = True
        self._update_selection()
        return True

    def activate(self) -> None:
        if self._rows and self._rows[self._selected].selectable:
            self._rows[self._selected].activate_row()

    def select(self, index: int) -> None:
        """Put the cursor on one row. This is a *placement*, so it pins the
        selection: a later rebuild follows the row rather than re-deciding
        where to start."""
        if 0 <= index < len(self._rows) and self._rows[index].selectable:
            self._selected = index
            self._pinned = True
            self._update_selection()

    def bump(self, distance: float) -> None:
        self._scroll.bump(distance)

    def _click(self, index: int) -> None:
        if not self._rows[index].selectable:
            return
        self.select(index)
        if self._on_activate is not None:
            self._on_activate(index)
        else:
            self._rows[index].activate_row()

    def _hover(self, index: int) -> None:
        if self._hover_enabled and self._rows[index].selectable:
            self.select(index)

    def _update_selection(self, *, animate: bool = True) -> None:
        for index, candidate in enumerate(self._rows):
            candidate.set_selected(index == self._selected and candidate.selectable)
        self._scroll_to_selection(animate=animate)

    def _scroll_to_selection(self, *, animate: bool) -> None:
        if not self._rows:
            return
        viewport_height = self._allocated_height
        if viewport_height <= 0:
            return

        # A row requests 72du, but that is only a minimum. Two-line rows can
        # grow beyond it when the font metrics and CSS padding need more
        # room. Using the nominal pitch here left the last Appearance rows
        # clipped because the scroll range was shorter than the real list.
        # Measure at the viewport width so this stays correct for every
        # theme, text scale, and row subtype.
        row_heights = [
            row.measure(Gtk.Orientation.VERTICAL, self._allocated_width)[1] for row in self._rows
        ]
        gutter = self._chrome.gutter(self._scale)
        offset = _selection_offset(
            row_heights,
            self._selected,
            viewport_height,
            self._content.get_spacing(),
            gutter=gutter,
        )
        content_height = sum(row_heights) + self._content.get_spacing() * max(
            0, len(row_heights) - 1
        )
        band = viewport_height - 2 * gutter
        above = offset < -1.0
        self._chrome.set_overhang(above=above, below=content_height + offset > band + 1.0)
        # The top gutter is reserved only while there is a pill to put in
        # it. `_selection_offset` has always placed rows at `gutter + top +
        # offset`; the margin making that true existed at the bottom and not
        # at the top, so the opaque "▲ More" pill landed square on the first
        # visible row ("Appearanc[▲ More]", "Networ[▲ More]"). Reserving it
        # unconditionally is what the old comment here rejected, rightly:
        # at rest there is no pill and it would be a permanent empty band.
        self._content.set_margin_top(gutter if above else 0)
        self._scroll.animate_to(offset) if animate else self._scroll.jump_to(offset)

# SPDX-License-Identifier: GPL-3.0-or-later
"""The small list of values a settings row can take.

Opened with OK on any row that has `choices` (see `widgets.py`), anchored on
that row's value so it appears where the setting is written rather than in
the middle of the screen. UP/DOWN walks it, OK picks, and BACK leaves it
unchanged — the shape a games console uses for exactly this, and the only
one where the alternatives are *visible* before the choice is made. Stepping
a value with a direction key shows one candidate at a time and hides the set.

On a row marked previewable the list opens over the *home screen* and each
value is applied as the cursor passes over it. That is `preview_policy` and
`screen_preview.py`; all this owns is `anchor` (the strip, not the row, has
the screen to itself down there), `on_candidate` and `on_dismissed` — the
last one being what makes BACK's promise of "unchanged" true again.

Two deliberate choices in here:

* **`set_autohide(False)`.** An autohiding popover takes a GTK input grab,
  and Salon does not route input through GTK focus — every button arrives as
  an `Action` on the window's controllers, or over HTTP from a phone, or off
  a gamepad, and a grab would silently take all of that away from the screen
  underneath. Dismissal is therefore ours to do: `SettingsScreen` closes
  this before anything else can happen to the list behind it.
* **It is unparented every time it closes.** Popovers hold a reference to
  the widget they are parented on, and settings panels rebuild their rows
  wholesale on every save — leaving one attached to a row that is about to
  be thrown away is how you get a popover pointing at nothing.

A real `Gtk.ScrolledWindow` here, unlike everywhere else in Salon: one small
list inside a popover with a bounded height, not a viewport whose scroll
position the selection has to drive across a full screen, so none of the
`Gtk.Fixed` machinery in `ui/motion.py` buys anything.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from salon.input.actions import Action  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.navigation_policy import is_settings_back  # noqa: E402
from salon.ui.settings.popup_option import ValueOption  # noqa: E402
from salon.ui.settings.widgets import SettingsRow  # noqa: E402

# How tall the list may get before it scrolls. Eight rows is enough for every
# choice list in Salon and for a useful window onto the long ranges (the
# 41-step idle-inhibit one is the worst), while staying short enough that the
# popup still reads as attached to its row rather than as a second screen.
_MAX_VISIBLE_ROWS = 8


class ValuePopup(Gtk.Popover):
    """One row's values, as a list. Driven entirely by `handle_action`."""

    def __init__(
        self,
        scale: Scale,
        on_chosen: Callable[[], None],
        *,
        on_candidate: Callable[[str], None] | None = None,
        on_dismissed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.add_css_class("salon-value-popup")
        self.set_autohide(False)
        self.set_has_arrow(False)
        self.set_position(Gtk.PositionType.BOTTOM)
        self.set_cascade_popdown(False)

        self._scale = scale
        self._on_chosen = on_chosen
        # Told which value the cursor rests on, and told when the list went
        # away without one being picked. Both are for live preview.
        self._on_candidate = on_candidate
        self._on_dismissed = on_dismissed
        self._committing = False  # a close that follows a choice is not a dismissal
        self._row: SettingsRow | None = None
        self._keys: list[str] = []
        self._buttons: list[Gtk.Button] = []
        self._selected = 0
        self._hover_enabled = False

        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroller.set_propagate_natural_height(True)
        self._scroller.set_propagate_natural_width(True)
        self.set_child(self._scroller)

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._scroller.set_child(self._list)

        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self._row_height = scale.px(56.0)
        self._list.set_spacing(scale.px(2.0))
        self._scroller.set_max_content_height(_MAX_VISIBLE_ROWS * self._row_height)
        self._scroller.set_min_content_width(scale.px(280.0))
        for button in self._buttons:
            button.set_size_request(-1, self._row_height)

    def set_hover_enabled(self, enabled: bool) -> None:
        self._hover_enabled = enabled

    # --- opening and closing ---------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._row is not None

    @property
    def row(self) -> SettingsRow | None:
        return self._row

    def open_for(
        self,
        row: SettingsRow,
        *,
        anchor: Gtk.Widget | None = None,
        position: Gtk.PositionType = Gtk.PositionType.BOTTOM,
    ) -> bool:
        """Raise the list for `row`; False if it hasn't got one. `anchor`
        overrides the row's value label — a list opened over the home screen
        has no row left on screen to hang off."""
        choices = row.choices
        if not choices:
            return False
        self.close()

        self._row = row
        self._keys = [key for key, _ in choices]
        current = row.current_choice
        self._selected = self._keys.index(current) if current in self._keys else 0

        self._buttons = []
        child = self._list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._list.remove(child)
            child = following

        swatches = row.swatches
        for index, (key, label) in enumerate(choices):
            button = ValueOption(
                self._scale,
                label,
                current=index == self._selected,
                index=index,
                height=self._row_height,
                on_click=self._activate,
                on_hover=self._hover,
                swatch=swatches.get(key, ""),
            )
            self._list.append(button)
            self._buttons.append(button)

        self.set_position(position)
        self.set_parent(anchor if anchor is not None else row.value_anchor)
        row.set_list_open(True)
        self._update_selection()
        self.popup()
        # After popup(), so the scroller has an adjustment with a real upper
        # bound to move within: before it, every value below the fold is
        # clamped back to zero and a list opens at the top however far down
        # the current value sits.
        self._scroll_to_selection()
        return True

    def close(self) -> None:
        if self._row is None:
            return
        self._row.set_list_open(False)
        self._row = None
        self.popdown()
        self.unparent()
        if not self._committing and self._on_dismissed is not None:
            self._on_dismissed()

    # --- navigation ------------------------------------------------------

    def handle_action(self, action: Action) -> None:
        if action in (Action.UP, Action.DOWN):
            step = -1 if action is Action.UP else 1
            target = self._selected + step
            if 0 <= target < len(self._buttons):
                self._selected = target
                self._update_selection()
                self._scroll_to_selection()
                self._announce_candidate()
            return
        if action is Action.OK:
            self._activate(self._selected)
            return
        if is_settings_back(action) or action is Action.MENU:
            # MENU is handled here only so the list is gone before the
            # screen it belongs to closes underneath it.
            self.close()

    def _hover(self, index: int) -> None:
        if self._hover_enabled and index != self._selected:
            self._selected = index
            self._update_selection()
            self._announce_candidate()

    def _activate(self, index: int) -> None:
        row = self._row
        if row is None or not (0 <= index < len(self._keys)):
            return
        key = self._keys[index]
        # A value was picked, so what is being previewed behind the list is
        # kept rather than undone.
        self._committing = True
        self.close()
        self._committing = False
        row.choose(key)
        self._on_chosen()

    def _announce_candidate(self) -> None:
        """The cursor moved onto a value. Live preview applies it now."""
        if self._on_candidate is not None and 0 <= self._selected < len(self._keys):
            self._on_candidate(self._keys[self._selected])

    def _update_selection(self) -> None:
        for index, button in enumerate(self._buttons):
            if index == self._selected:
                button.add_css_class("selected")
            else:
                button.remove_css_class("selected")

    def _scroll_to_selection(self) -> None:
        adjustment = self._scroller.get_vadjustment()
        if adjustment is None:
            return
        pitch = float(self._row_height + self._scale.px(2.0))
        top = self._selected * pitch
        page = adjustment.get_page_size()
        value = adjustment.get_value()
        if top < value:
            adjustment.set_value(top)
        elif top + pitch > value + page:
            adjustment.set_value(top + pitch - page)

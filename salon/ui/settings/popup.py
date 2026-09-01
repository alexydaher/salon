# SPDX-License-Identifier: GPL-3.0-or-later
"""A row's value list, either anchored or embedded in live preview."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.input.actions import Action  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.navigation_policy import is_settings_back  # noqa: E402
from salon.ui.settings.popup_option import RangePreview, ValueOption  # noqa: E402
from salon.ui.settings.widgets import RangeRow, SettingsRow  # noqa: E402

# Eight visible rows keep long ranges useful without becoming a second screen.
_MAX_VISIBLE_ROWS = 5


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
        self._inline_host: Gtk.Box | None = None
        self._horizontal = False
        self._range_preview: RangePreview | None = None

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
        list_height = _MAX_VISIBLE_ROWS * self._row_height + (_MAX_VISIBLE_ROWS - 1) * scale.px(2.0)
        self._scroller.set_max_content_height(list_height)
        self._scroller.set_min_content_width(scale.px(280.0))
        for button in self._buttons:
            button.set_size_request(-1, self._row_height)
        if self._range_preview is not None:
            self._range_preview.set_scale(scale)

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
        inline: Gtk.Box | None = None,
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
        preview = anchor is not None or inline is not None
        range_preview = preview and isinstance(row, RangeRow)
        self._horizontal = preview
        if preview:
            self.add_css_class("preview-values")
            self._list.set_orientation(Gtk.Orientation.HORIZONTAL)
            self._list.set_hexpand(True)
            self._list.set_homogeneous(not range_preview)
            self._scroller.set_min_content_width(self._scale.px(920.0))
        else:
            self.remove_css_class("preview-values")
            self._list.set_orientation(Gtk.Orientation.VERTICAL)
            self._list.set_hexpand(False)
            self._list.set_homogeneous(False)
            self._scroller.set_min_content_width(self._scale.px(280.0))

        self._buttons = []
        self._range_preview = None
        child = self._list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._list.remove(child)
            child = following

        if range_preview:
            self._range_preview = RangePreview(
                self._scale,
                [label for _key, label in choices],
                self._selected,
                self._range_changed,
            )
            self._list.append(self._range_preview)
        else:
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
                    preview=preview,
                )
                if preview:
                    button.set_hexpand(True)
                    button.set_size_request(-1, self._scale.px(122.0))
                self._list.append(button)
                self._buttons.append(button)

        self._inline_host = inline
        row.set_list_open(True)
        self._update_selection()
        if inline is not None:
            self._scroller.set_child(None)
            inline.append(self._list)
        else:
            self.set_position(position)
            self.set_parent(anchor if anchor is not None else row.value_anchor)
            if anchor is None:
                pitch = self._row_height + self._scale.px(2.0)
                # Centre the selected value on its setting row. BOTTOM is
                # GTK's reliable anchor for a label nested inside the row.
                self.set_position(Gtk.PositionType.BOTTOM)
                visible = min(len(self._buttons), _MAX_VISIBLE_ROWS)
                first = max(0, min(self._selected - visible // 2, len(self._buttons) - visible))
                selected_centre = (self._selected - first + 0.5) * pitch
                vertical = selected_centre + self._row_height * 0.54
                self.set_offset(self._scale.px(-70.0), -round(vertical))
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
        if self._inline_host is not None:
            self._inline_host.remove(self._list)
            self._scroller.set_child(self._list)
            self._inline_host = None
        else:
            self.popdown()
            self.unparent()
        if not self._committing and self._on_dismissed is not None:
            self._on_dismissed()

    # --- navigation ------------------------------------------------------

    def handle_action(self, action: Action) -> None:
        directions = (
            (Action.LEFT, Action.RIGHT) if self._horizontal else (Action.UP, Action.DOWN)
        )
        if action in directions:
            step = -1 if action is directions[0] else 1
            target = self._selected + step
            if 0 <= target < len(self._keys):
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

    def _range_changed(self, index: int) -> None:
        if index == self._selected or not (0 <= index < len(self._keys)):
            return
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
        if self._range_preview is not None:
            self._range_preview.set_selected(self._selected)
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
        if page > 0:
            adjustment.set_value(top + pitch / 2.0 - page / 2.0)

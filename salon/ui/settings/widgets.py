# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings row kit: one navigable list, six kinds of row.

§6.8 requires Settings to be styled like the home screen and operable with
six buttons — never a desktop dialog on a television. That rules out
`Adw.PreferencesPage`, whose rows expect a pointer and a scrollbar, so this
is a small purpose-built set instead:

* UP/DOWN moves the selection,
* RIGHT engages the selected row — a row with values is *stepped into* and
  only then does LEFT/RIGHT change it,
* LEFT is never a value change: it leaves the row, and then the panel,
* OK activates it.

That middle pair is the whole shape of this screen. LEFT means "back" in
the section list, in every sub-panel and on the home screen; a settings
panel where it silently meant "decrement" instead was the one place in
Salon where the same button did two unrelated things depending on which
row the cursor happened to be resting on. Now a row has to be entered
before it can be changed, so LEFT means back everywhere and nothing is
edited by accident on the way out.

`adjustable` rows (choice, range) are the ones with an inside to step into;
`enterable` rows (toggle, text, and the action rows that open a sub-panel)
have nothing to step through, so RIGHT does the thing directly. The rest —
plain actions like "Shut Down", read-only info — refuse RIGHT with a short
flash rather than acting, because a directional key must never be the way a
destructive row gets triggered.

Every row is also a real button, so a mouse or a phone trackpad works
without a second code path, and hover moves the selection so the two input
methods never disagree about what's highlighted. A click still activates a
row outright: engaging is a D-pad concept, and a pointer never needed it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import GLib, Gtk, Pango  # noqa: E402

from salon.ui.motion import AxisSpring  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

# How long the "nothing to step into here" flash lasts. Long enough to
# register from a sofa, short enough not to read as a state.
_DENY_FLASH_MS = 220

# Opacity of the ‹ › affordances beside an adjustable row's value, keyed by
# (engaged, that direction still has somewhere to go). They are always
# rendered, at 2% when the row isn't selected, so landing on a row fades
# them in instead of shifting the value sideways.
_CHEVRON_ALPHA = {
    (True, True): "100%",
    (True, False): "20%",
    (False, True): "40%",
    (False, False): "14%",
}
_CHEVRON_IDLE_ALPHA = "2%"


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
        self._adjusting = False
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

    def set_adjusting(self, adjusting: bool) -> None:
        """Engaged: LEFT/RIGHT belong to this row until it is left again."""
        if adjusting == self._adjusting:
            return
        self._adjusting = adjusting
        if adjusting:
            self.add_css_class("adjusting")
        else:
            self.remove_css_class("adjusting")
        # PRESSED is the closest thing GTK has to "this row currently owns
        # the left/right buttons", and it is what a screen reader reports as
        # a toggled-on button — which is what being engaged is.
        self.update_state(
            [Gtk.AccessibleState.PRESSED],
            [int(Gtk.AccessibleTristate.TRUE if adjusting else Gtk.AccessibleTristate.FALSE)],
        )
        self._render_value()

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
        # labels, which would otherwise include the ‹ › affordances and the
        # 2%-alpha spans holding their space. Say the row instead.
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"{self.label_text}, {self._raw_value}" if self._raw_value else self.label_text],
        )
        if not self.adjustable:
            self._value.set_use_markup(False)
            self._value.set_text(self._raw_value)
            return
        left = self._chevron("\u2039", -1)
        right = self._chevron("\u203a", 1)
        text = GLib.markup_escape_text(self._raw_value)
        self._value.set_markup(f"{left}\u2002{text}\u2002{right}")

    def _chevron(self, glyph: str, delta: int) -> str:
        if not self._is_selected:
            alpha = _CHEVRON_IDLE_ALPHA
        else:
            alpha = _CHEVRON_ALPHA[(self._adjusting, self.can_adjust(delta))]
        return f"<span alpha='{alpha}'>{glyph}</span>"

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
    def adjustable(self) -> bool:
        """True for rows with a set of values to walk. RIGHT steps *into*
        these; only then does LEFT/RIGHT move through the values."""
        return False

    @property
    def enterable(self) -> bool:
        """True for rows where RIGHT may safely do the thing directly: no
        values to walk, and nothing lost by a stray press."""
        return False

    @property
    def ok_engages(self) -> bool:
        """Whether OK should engage the row rather than activate it. True
        wherever activating would change a value without showing the user
        they are now inside it."""
        return False

    @property
    def hint(self) -> str:
        """What the legend at the bottom of the screen says about this row."""
        return "OK selects"

    def activate_row(self) -> None:
        """OK, or a click."""

    def can_adjust(self, delta: int) -> bool:
        """Whether a step in this direction would change anything. Drives
        the chevrons as well as `adjust`, so the affordance and the
        behaviour cannot drift apart."""
        return False

    def adjust(self, delta: int) -> bool:
        """LEFT/RIGHT while engaged. Return False if the step ran off the
        end, so the caller can flash instead of doing nothing silently."""
        return False

    def refresh(self) -> None:
        """Re-read the underlying value. Called when the list is shown, so
        a row never displays state that changed elsewhere."""


class ActionRow(SettingsRow):
    """A row that does something. `opens` says whether RIGHT may do it.

    It defaults to the chevron this screen already draws on every row that
    leads somewhere — a section, a tile, a sub-panel — so a drill-in row
    written the same way as the existing ones is enterable without anyone
    having to remember a second flag. Rows that act rather than navigate
    ("Shut Down", "Delete row", "Add tile") are left alone: OK is a
    deliberate press, a direction key is not, and RIGHT must never be how a
    television gets turned off.
    """

    def __init__(
        self,
        label: str,
        on_activate: Callable[[], None],
        *,
        detail: str = "",
        value: str = "",
        danger: bool = False,
        icon_name: str = "",
        opens: bool | None = None,
    ) -> None:
        super().__init__(label, detail=detail, danger=danger, icon_name=icon_name)
        self._on_activate = on_activate
        self._opens = (value == "\u203a") if opens is None else opens
        self.set_value(value)

    @property
    def enterable(self) -> bool:
        return self._opens

    @property
    def hint(self) -> str:
        return "OK or RIGHT opens it" if self._opens else "OK runs it"

    def activate_row(self) -> None:
        self._on_activate()


class InfoRow(SettingsRow):
    """Read-only. Still selectable, because on a D-pad a row you cannot
    land on is a row you cannot read the end of."""

    def __init__(
        self, label: str, value: str, *, detail: str = "", icon_name: str = ""
    ) -> None:
        super().__init__(label, detail=detail, icon_name=icon_name)
        self.set_value(value)
        self.add_css_class("info")

    @property
    def hint(self) -> str:
        return "Nothing to change on this row"


class ToggleRow(SettingsRow):
    def __init__(
        self,
        label: str,
        get: Callable[[], bool],
        set_: Callable[[bool], None],
        *,
        detail: str = "",
        preview: bool = False,
    ) -> None:
        super().__init__(label, detail=detail, preview=preview)
        self._get = get
        self._set = set_
        self.refresh()

    @property
    def enterable(self) -> bool:
        """On/Off has no inside to step into: stepping in and then pressing
        RIGHT again to reach the only other value would be two presses to
        do what one already does, and LEFT would mean "Off" at exactly the
        moment the rest of the screen has taught it to mean "back"."""
        return True

    @property
    def hint(self) -> str:
        return "OK or RIGHT switches it"

    def refresh(self) -> None:
        self.set_value("On" if self._get() else "Off")

    def activate_row(self) -> None:
        self._set(not self._get())
        self.refresh()

    def can_adjust(self, delta: int) -> bool:
        return self._get() != (delta > 0)

    def adjust(self, delta: int) -> bool:
        """Still LEFT/RIGHT-able for the preview strip, which has no BACK
        of its own to protect."""
        if not self.can_adjust(delta):
            return False
        self._set(delta > 0)
        self.refresh()
        return True


class ChoiceRow(SettingsRow):
    def __init__(
        self,
        label: str,
        options: Sequence[tuple[str, str]],
        get: Callable[[], str],
        set_: Callable[[str], None],
        *,
        detail: str = "",
        preview: bool = False,
    ) -> None:
        super().__init__(label, detail=detail, preview=preview)
        self._options = list(options)
        self._get = get
        self._set = set_
        self.refresh()

    def _index(self) -> int:
        current = self._get()
        for index, (value, _) in enumerate(self._options):
            if value == current:
                return index
        return 0

    @property
    def adjustable(self) -> bool:
        return bool(self._options)

    @property
    def ok_engages(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "OK or RIGHT changes it"

    def refresh(self) -> None:
        if self._options:
            self.set_value(self._options[self._index()][1])

    def activate_row(self) -> None:
        """A mouse click, which has no notion of being inside a row: cycle."""
        self.adjust(1)

    def can_adjust(self, delta: int) -> bool:
        return bool(self._options) and 0 <= self._index() + delta < len(self._options)

    def adjust(self, delta: int) -> bool:
        if not self.can_adjust(delta):
            return False
        self._set(self._options[self._index() + delta][0])
        self.refresh()
        return True


class RangeRow(SettingsRow):
    def __init__(
        self,
        label: str,
        get: Callable[[], float],
        set_: Callable[[float], None],
        *,
        minimum: float,
        maximum: float,
        step: float,
        fmt: Callable[[float], str] = lambda v: f"{v:g}",
        detail: str = "",
        preview: bool = False,
    ) -> None:
        super().__init__(label, detail=detail, preview=preview)
        self._get = get
        self._set = set_
        self._minimum = minimum
        self._maximum = maximum
        self._step = step
        self._fmt = fmt
        self.refresh()

    @property
    def adjustable(self) -> bool:
        return True

    @property
    def ok_engages(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "OK or RIGHT changes it"

    def refresh(self) -> None:
        self.set_value(self._fmt(self._get()))

    def _target(self, delta: int) -> float:
        return min(self._maximum, max(self._minimum, self._get() + delta * self._step))

    def can_adjust(self, delta: int) -> bool:
        return abs(self._target(delta) - self._get()) >= 1e-9

    def adjust(self, delta: int) -> bool:
        if not self.can_adjust(delta):
            return False
        self._set(self._target(delta))
        self.refresh()
        return True

    def activate_row(self) -> None:
        """A mouse click, which has no notion of being inside a row: step."""
        self.adjust(1)


class TextRow(SettingsRow):
    """Opens the on-screen keyboard; the value arrives back through the
    callback the caller wires to `ui/textentry.py`."""

    def __init__(
        self,
        label: str,
        get: Callable[[], str],
        on_edit: Callable[[], None],
        *,
        placeholder: str = "Not set",
        detail: str = "",
    ) -> None:
        super().__init__(label, detail=detail)
        self._get = get
        self._on_edit = on_edit
        self._placeholder = placeholder
        self.refresh()

    @property
    def enterable(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "OK or RIGHT edits it"

    def refresh(self) -> None:
        self.set_value(self._get() or self._placeholder)

    def activate_row(self) -> None:
        self._on_edit()


class SettingsList(Gtk.Fixed):
    """A vertically scrolling list of rows with a single selection.

    A Gtk.Fixed clipping around a taller box, translated by a spring — the
    same mechanism the home rows use, rather than a Gtk.ScrolledWindow,
    because the selection drives the scroll here and not the reverse.
    """

    def __init__(self, scale: Scale) -> None:
        super().__init__()
        self.add_css_class("salon-settings-list")
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._scale = scale
        self._rows: list[SettingsRow] = []
        self._selected = 0
        # Whether the selected row is *engaged* — LEFT/RIGHT are its, not
        # the navigation's. Owned here rather than by the screen because
        # every path that moves the selection has to drop it, including
        # the mouse ones the screen never sees.
        self._adjusting = False
        self._hover_enabled = False
        self._allocated_width = -1
        self._allocated_height = -1

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.put(self._content, 0, 0)
        self._scroll = AxisSpring(self, self._content, vertical=True)

    def on_resize(self, width: int, height: int) -> None:
        """Fed by the `SizeReporter` this list is wrapped in.

        A Gtk.Fixed hands every child its own measured size, and an
        ellipsized label measures one ellipsis wide — the same trap the home
        screen's row headings fell into. The content box has to be told how
        wide the viewport actually is.
        """
        self._allocated_width = width
        self._allocated_height = height
        self._content.set_size_request(width, -1)
        # And only now is there a height to scroll within: set_rows runs
        # before the first allocation, so without this the list opens
        # unscrolled however far down the selection sits.
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

    @property
    def adjusting(self) -> bool:
        return self._adjusting

    def set_adjusting(self, adjusting: bool) -> bool:
        """Engage or release the selected row. False if there was nothing
        to engage, so the caller can flash the row instead."""
        row = self.selected_row
        if adjusting and (row is None or not row.adjustable):
            return False
        self._adjusting = adjusting
        self._update_selection(animate=False)
        return True

    def set_hover_enabled(self, enabled: bool) -> None:
        self._hover_enabled = enabled

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
        child = self._content.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._content.remove(child)
            child = next_child

        self._rows = rows
        for index, row in enumerate(rows):
            row.set_scale(self._scale)
            row.connect("clicked", lambda _b, i=index: self._click(i))
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", lambda *_, i=index: self._hover(i))
            row.add_controller(motion)
            self._content.append(row)

        if not keep_selection or self._selected >= len(rows):
            self._selected = 0
        self._content.set_spacing(self._scale.px(6.0))
        self._update_selection(animate=False)

    def refresh_values(self) -> None:
        for row in self._rows:
            row.refresh()

    def move(self, delta: int) -> bool:
        if not self._rows:
            return False
        target = self._selected + delta
        if not (0 <= target < len(self._rows)):
            return False
        self._selected = target
        self._adjusting = False
        self._update_selection()
        return True

    def activate(self) -> None:
        if self._rows:
            self._rows[self._selected].activate_row()

    def adjust(self, delta: int) -> bool:
        if not self._rows:
            return False
        return self._rows[self._selected].adjust(delta)

    def select(self, index: int) -> None:
        if 0 <= index < len(self._rows):
            if index != self._selected:
                self._adjusting = False
            self._selected = index
            self._update_selection()

    def bump(self, distance: float) -> None:
        self._scroll.bump(distance)

    def _click(self, index: int) -> None:
        self.select(index)
        self._rows[index].activate_row()

    def _hover(self, index: int) -> None:
        if self._hover_enabled:
            self.select(index)

    def _update_selection(self, *, animate: bool = True) -> None:
        # A rebuild replaces every row object while a row is engaged (any
        # edit that saves the catalogue does exactly that), so the engaged
        # state is re-applied here rather than held on a widget that may
        # already have been thrown away.
        row = self.selected_row
        if self._adjusting and (row is None or not row.adjustable):
            self._adjusting = False
        for index, candidate in enumerate(self._rows):
            selected = index == self._selected
            candidate.set_selected(selected)
            candidate.set_adjusting(selected and self._adjusting)
        self._scroll_to_selection(animate=animate)

    def _scroll_to_selection(self, *, animate: bool) -> None:
        if not self._rows:
            return
        row_height = self._scale.du(72.0) + self._scale.du(6.0)
        viewport_height = self._allocated_height
        if viewport_height <= 0:
            return
        content_height = len(self._rows) * row_height
        top = self._selected * row_height
        offset = 0.0
        if top + row_height > viewport_height:
            offset = viewport_height - (top + row_height)
        offset = max(min(0.0, viewport_height - content_height), min(0.0, offset))
        self._scroll.animate_to(offset) if animate else self._scroll.jump_to(offset)

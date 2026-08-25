# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings row kit: one navigable list, six kinds of row.

§6.8 requires Settings to be styled like the home screen and operable with
six buttons — never a desktop dialog on a television. That rules out
`Adw.PreferencesPage`, whose rows expect a pointer and a scrollbar, so this
is a small purpose-built set instead:

* UP/DOWN moves the selection,
* OK (or RIGHT) **opens** the selected row: a row with a set of values
  raises a small list of them beside itself and the choice is made there,
* LEFT is never a value change: it leaves the panel.

That middle line is the whole shape of this screen, and it has been through
two designs. LEFT/RIGHT used to change a value in place, which made the
button that means "back" everywhere else in Salon silently edit a setting.
That was replaced by an *engage* mode — RIGHT stepped into a row, then
LEFT/RIGHT walked its values — which fixed the ambiguity but kept the part
nobody liked: a direction key was still what changed the setting, the values
went past one at a time with no way to see the set, and how many presses a
change took depended on where in the list the current value happened to sit.

Now the values are a list. OK opens `ui/settings/popup.py` anchored on the
row, UP/DOWN walks the options with all of them on screen at once, and OK
picks one — the shape a games console uses, for the same reason: it is the
only one where the user can see what the alternatives *are* before choosing.
`choices` on a row is what says it has a list; rows that have nothing to pick
from (toggles, text fields, rows that open a sub-panel) are `enterable` and
RIGHT does the thing directly. The rest — plain actions like "Shut Down",
read-only info — refuse RIGHT with a short flash rather than acting, because
a directional key must never be the way a television gets turned off.

`can_adjust`/`adjust` survive the change and are now only for the preview
strip, where LEFT/RIGHT stepping is right: the point there is watching the
home screen change under the value, not reading a list of numbers.

Every row is also a real button, so a mouse or a phone trackpad works
without a second code path, and hover moves the selection so the two input
methods never disagree about what's highlighted.
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

# The affordance beside a row's value saying "there is a list behind this".
# Always rendered on such a row so that landing on one fades it in rather
# than shifting the value sideways to make room.
_DROPDOWN_GLYPH = "\u2304"  # ⌄
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
        return "OK selects"

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
        """On/Off is not a list worth raising. A popup offering two items,
        one of which is what the row already says, is two presses and a
        panel to do what one press already does — and unlike a range or a
        palette there is nothing to *see* in the set of alternatives."""
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
    def choices(self) -> list[tuple[str, str]]:
        return list(self._options)

    @property
    def current_choice(self) -> str:
        return self._get()

    def choose(self, key: str) -> None:
        self._set(key)
        self.refresh()

    @property
    def hint(self) -> str:
        return "OK opens the list"

    def refresh(self) -> None:
        if self._options:
            self.set_value(self._options[self._index()][1])

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
    def choices(self) -> list[tuple[str, str]]:
        """Every step from minimum to maximum, as a list.

        A range is a set of values like any other here — these are all
        coarse, deliberately chosen steps (5% of a scale, 50ms of a repeat
        delay), not continuous quantities, and the longest of them is a few
        dozen entries in a list that scrolls. Enumerating them means the
        user can jump to the end instead of pressing RIGHT forty times.

        Keyed by index rather than by the value: the labels go through
        `fmt` and two neighbouring steps can format identically ("Off" and
        "0 s"), so the key has to be the one thing that is unique.
        """
        return [(str(index), self._fmt(value)) for index, value in enumerate(self._steps())]

    def _steps(self) -> list[float]:
        values: list[float] = []
        value = self._minimum
        # Accumulated by addition rather than by index * step so the last
        # entry is exactly `maximum` when the span divides evenly, and the
        # epsilon keeps a float that lands a hair over the top from being
        # dropped.
        while value <= self._maximum + 1e-9:
            values.append(min(value, self._maximum))
            value += self._step
        return values

    @property
    def current_choice(self) -> str:
        current = self._get()
        steps = self._steps()
        if not steps:
            return ""
        nearest = min(range(len(steps)), key=lambda i: abs(steps[i] - current))
        return str(nearest)

    def choose(self, key: str) -> None:
        steps = self._steps()
        index = int(key)
        if 0 <= index < len(steps):
            self._set(steps[index])
            self.refresh()

    @property
    def hint(self) -> str:
        return "OK opens the list"

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
        self._update_selection()
        return True

    def activate(self) -> None:
        if self._rows:
            self._rows[self._selected].activate_row()

    def select(self, index: int) -> None:
        if 0 <= index < len(self._rows):
            self._selected = index
            self._update_selection()

    def bump(self, distance: float) -> None:
        self._scroll.bump(distance)

    def _click(self, index: int) -> None:
        self.select(index)
        if self._on_activate is not None:
            self._on_activate(index)
        else:
            self._rows[index].activate_row()

    def _hover(self, index: int) -> None:
        if self._hover_enabled:
            self.select(index)

    def _update_selection(self, *, animate: bool = True) -> None:
        for index, candidate in enumerate(self._rows):
            candidate.set_selected(index == self._selected)
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

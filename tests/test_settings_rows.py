# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings row kit: what a row shows, and where the cursor lands."""

from __future__ import annotations

import os

# GSettings, in memory and nowhere else. A dconf *write* is a D-Bus call to
# the writer daemon, which resolves the user database from its own
# environment — so a harness that redirects the XDG directories still edits
# the live session while reading its own empty copy back. Assigned rather
# than `setdefault`, and before `gi.repository` is imported, which is when
# the backend is chosen. Enforced by tests/test_settings_isolation.py.
os.environ["GSETTINGS_BACKEND"] = "memory"

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, Gtk  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.action_rows import (  # noqa: E402
    ActionRow,
    ToggleRow,
    opens_gnome,
    opens_panel,
)
from salon.ui.settings.keyed import Keyed, restore_defaults_row  # noqa: E402
from salon.ui.settings.list_layout import (  # noqa: E402
    _first_stop,
    _rebuilt_selection,
    _selection_offset,
)
from salon.ui.settings.settings_list import SettingsList  # noqa: E402
from salon.ui.settings.static_rows import GroupRow, InfoRow  # noqa: E402
from salon.ui.settings.value_rows import ChoiceRow, RangeRow, TextRow  # noqa: E402

_ACCENTS = [("#E8A33D", "Amber"), ("#4C9BE8", "Blue")]


@pytest.fixture(autouse=True)
def _gtk() -> None:
    Gtk.init()


# --- what a value looks like --------------------------------------------


def test_off_is_muted_so_the_accent_never_means_not_doing_anything() -> None:
    """The value column is @accent, so a row reading "Off" used to render
    the disabled state as the brightest thing on the screen."""
    state = {"on": False}
    row = ToggleRow("Reduced motion", lambda: state["on"], lambda v: state.__setitem__("on", v))
    assert row.value_text == "Off" and row._muted
    row.activate_row()
    assert row.value_text == "On" and not row._muted


def test_a_colour_choice_offers_its_colours_to_the_list() -> None:
    """The keys of an accent list *are* the colours, so neither the row nor
    the popup has to be told twice."""
    row = ChoiceRow("Accent", _ACCENTS, lambda: "#4C9BE8", lambda _v: None)
    assert row.swatches == {"#E8A33D": "#E8A33D", "#4C9BE8": "#4C9BE8"}


def test_a_non_colour_choice_offers_none() -> None:
    row = ChoiceRow("Theme", [("midnight", "Midnight")], lambda: "midnight", lambda _v: None)
    assert row.swatches == {}


def test_a_range_that_lands_on_off_is_muted_too() -> None:
    """"Animation speed: Off" in the accent colour is the same mistake a
    switch reading Off in the accent colour was."""
    stored = {"value": 0.0}
    row = RangeRow(
        "Animation speed",
        lambda: stored["value"],
        lambda v: stored.__setitem__("value", v),
        minimum=0.0,
        maximum=2.0,
        step=0.25,
        fmt=lambda v: "Off" if v == 0 else f"{v:g}",
        off_at=0.0,
    )
    assert row.value_text == "Off" and row._muted
    stored["value"] = 1.0
    row.refresh()
    assert not row._muted


def test_a_placeholder_is_muted_and_a_real_value_is_not() -> None:
    stored = {"value": ""}
    row = TextRow("Path", lambda: stored["value"], lambda: None, placeholder="Not set")
    assert row.value_text == "Not set" and row._muted
    stored["value"] = "/tmp/a.png"
    row.refresh()
    assert row.value_text == "/tmp/a.png" and not row._muted


# --- where the cursor lands ----------------------------------------------


def test_the_cursor_opens_on_something_it_can_act_on() -> None:
    """About and Audio both led with a read-only fact, so opening either
    announced itself with "Nothing to change on this row"."""
    rows = [InfoRow("Version", "0.3.3"), ActionRow("Open folder", lambda: None)]
    assert _first_stop(rows) == 1


def test_a_group_heading_is_never_a_stop() -> None:
    rows = [GroupRow("Colour"), ChoiceRow("Theme", [("a", "A")], lambda: "a", lambda _v: None)]
    assert _first_stop(rows) == 1
    listing = SettingsList(Scale(1080))
    listing.set_rows(list(rows))
    assert listing.selected_index == 1
    # And UP from the first real row cannot get stuck on it.
    assert not listing.move(-1)


def test_a_rebuild_keeps_the_cursor_and_a_new_panel_does_not() -> None:
    """`_rebuild_panel` serves both "a value changed, redraw" and "we are
    looking at a different panel now". Treating the second as the first is
    why the first-actionable rule never fired — About opened on Version."""
    listing = SettingsList(Scale(1080))
    first = [InfoRow("Version", "0.3.3"), ActionRow("Open folder", lambda: None)]
    listing.set_rows(first, keep_selection=False)
    assert listing.selected_index == 1
    listing.select(0)

    # Same panel, rebuilt: the cursor stays where the user left it, even on
    # a read-only row.
    listing.set_rows([InfoRow("Version", "0.3.4"), ActionRow("Open folder", lambda: None)],
                     keep_selection=True)
    assert listing.selected_index == 0

    # A different panel: start at something pressable.
    listing.set_rows([InfoRow("Current output", "HDMI 3"), ActionRow("Test", lambda: None)],
                     keep_selection=False)
    assert listing.selected_index == 1


def test_a_panel_that_fills_in_later_does_not_pick_a_row_for_you() -> None:
    """Audio asks wpctl for the outputs on a worker thread, so it builds
    once as "No outputs found" — cursor on the test-tone row — and again
    when they arrive. Keeping the *index* put it on whichever sink happened
    to be third, and OK there switches the television's output."""
    listing = SettingsList(Scale(1080))
    listing.set_rows(
        [GroupRow("Output"), InfoRow("No outputs found", ""), ActionRow("Test", lambda: None)]
    )
    assert listing.selected_index == 2

    listing.set_rows(
        [
            GroupRow("Output"),
            ActionRow("HDMI 3", lambda: None),
            ActionRow("HDMI 2", lambda: None),
            ActionRow("Test", lambda: None),
        ],
        keep_selection=True,
    )
    assert listing.rows[listing.selected_index].label_text == "HDMI 3"


def test_a_rebuild_under_a_cursor_the_user_moved_follows_the_row() -> None:
    """Once it has been placed, the row is followed by name — an edit
    rebuilds the panel and the cursor must not walk back to the top."""
    keys = ["ToggleRow:Mute", "RangeRow:Volume", "ActionRow:Test"]
    assert (
        _rebuilt_selection(
            ["GroupRow:Output", *keys],
            [False, True, True, True],
            previous_key="RangeRow:Volume",
            previous_index=1,
            pinned=True,
        )
        == 2
    )


def test_a_renamed_row_keeps_the_cursor_where_it_was() -> None:
    """Renaming a tile from the row above it changes that row's key.
    Staying put beats starting the panel over."""
    assert (
        _rebuilt_selection(
            ["ActionRow:Film Night", "ActionRow:Arcade"],
            [True, True],
            previous_key="ActionRow:Movie Night",
            previous_index=0,
            pinned=True,
        )
        == 0
    )


def test_a_row_that_went_away_hands_the_choice_back() -> None:
    assert (
        _rebuilt_selection(
            ["GroupRow:Output"],
            [False],
            previous_key="ActionRow:HDMI 3",
            previous_index=2,
            pinned=True,
        )
        is None
    )


def test_a_panel_of_only_read_only_rows_still_has_a_cursor() -> None:
    rows = [InfoRow("A", ""), InfoRow("B", "")]
    assert _first_stop(rows) == 0


# --- the scroll gutter ----------------------------------------------------


def test_no_row_is_ever_drawn_under_a_scroll_pill() -> None:
    """The "▼ More" pill is opaque and was drawn over the content, so
    Appearance rendered "Salon an▼More" across a row's value.

    The list carries a matching margin, so a row's position on screen is
    `gutter + top + offset` — which is what this checks, for every row in
    turn rather than only the one the cursor is on.
    """
    heights = [72] * 10
    gutter, spacing, viewport = 34, 6, 300
    for selected in range(len(heights)):
        offset = _selection_offset(heights, selected, viewport, spacing, gutter=gutter)
        top = sum(heights[:selected]) + spacing * selected
        assert gutter + top + offset >= gutter - 1e-6, selected
        assert gutter + top + heights[selected] + offset <= viewport - gutter + 1e-6, selected


def test_the_gutter_costs_nothing_at_the_ends() -> None:
    """At the top and bottom the pill is hidden, so reserving space for it
    there would scroll a list that does not need scrolling."""
    heights = [72] * 3
    assert _selection_offset(heights, 0, viewport_height=300, spacing=6, gutter=34) == 0.0


def test_the_existing_end_of_list_behaviour_is_unchanged() -> None:
    assert _selection_offset([72, 72, 84, 84], 3, 240, 6) == -90


# --- rows bound to a GSettings key ---------------------------------------


def _settings() -> Gio.Settings:
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup("io.github.alexydaher.Salon", True) if source else None
    if schema is None:
        pytest.skip("Salon's compiled schema is not on GSETTINGS_SCHEMA_DIR")
    return Gio.Settings.new_full(schema, None, None)


def test_a_keyed_row_knows_what_salon_shipped() -> None:
    settings = _settings()
    keyed = Keyed(settings)
    row = keyed.ranged(
        "tile-scale", "Tile size", minimum=0.5, maximum=1.5, step=0.05, fmt=lambda v: f"{v:g}"
    )
    assert not row.modified
    settings.set_double("tile-scale", 1.25)
    row.refresh()
    assert row.modified
    assert row.reset_to_default()
    assert not row.modified


def test_an_integer_key_is_read_and_written_as_one() -> None:
    """The half of this that used to be spelled by hand at every call site,
    where getting one side wrong is a GLib.Variant error at runtime."""
    settings = _settings()
    keyed = Keyed(settings)
    row = keyed.ranged(
        "key-repeat-initial-ms",
        "Repeat delay",
        minimum=150,
        maximum=1000,
        step=50,
        fmt=lambda v: f"{v:.0f}",
    )
    row.choose(row.current_choice)
    row.adjust(1)
    assert settings.get_value("key-repeat-initial-ms").get_type_string() == "i"


def test_restore_defaults_counts_only_what_this_panel_owns() -> None:
    settings = _settings()
    keyed = Keyed(settings)
    keyed.toggle("reduced-motion", "Reduced motion")
    keyed.choice("theme", "Theme", [("midnight", "Midnight"), ("ember", "Ember")])
    settings.set_string("theme", "ember")
    # Touched, but not one of this panel's rows.
    settings.set_int("volume-step-percent", 11)

    assert keyed.modified_keys == ["theme"]
    row = restore_defaults_row(keyed, lambda _m: None, lambda: None)
    assert row.value_text == "1 changed"
    assert keyed.reset_all() == 1
    assert settings.get_string("theme") == "midnight"
    assert settings.get_int("volume-step-percent") == 11
    settings.reset("volume-step-percent")


# --- rows that leave Salon ------------------------------------------------


def test_an_external_row_says_so_before_it_is_pressed() -> None:
    """"Display and resolution" and "Shut Down" were the same shape of row."""
    external = opens_gnome("Display and resolution", lambda: None, detail="Resolution")
    internal = opens_panel("Advanced input", lambda: None)
    assert external.external and "GNOME Settings" in external.hint
    assert not internal.external
    assert not external.enterable, "a direction key must not leave the application"


def test_a_plain_action_row_refuses_right() -> None:
    assert not ActionRow("Shut down", lambda: None).enterable
    assert opens_panel("Power", lambda: None).enterable


def test_the_deny_flash_clears_itself() -> None:
    row = ActionRow("Shut down", lambda: None)
    row.flash_denied()
    assert row.has_css_class("denied")
    row._end_deny_flash()
    assert not row.has_css_class("denied")
    GLib.MainContext.default().iteration(False)


# --- the modified dot -----------------------------------------------------


def test_the_dot_gutter_is_the_same_on_every_row_of_a_panel() -> None:
    """A hidden box child takes no space, so the dot used to push its own
    label 38du right of every neighbour's — a ragged left edge on exactly
    the rows meant to catch the eye."""
    settings = _settings()
    keyed = Keyed(settings)
    listing = SettingsList(Scale(1080))
    changed = keyed.ranged(
        "tile-scale", "Tile size", minimum=0.5, maximum=1.5, step=0.05, fmt=str
    )
    settings.set_double("tile-scale", 0.9)
    changed.refresh()
    plain = ActionRow("Play a test sound", lambda: None)
    listing.set_rows([changed, plain])

    assert changed.modified and not plain.has_default
    # Both reserve it, because one of them can show it.
    assert changed._content._dot.get_visible() and plain._content._dot.get_visible()
    assert changed._content._dot.get_opacity() == 1.0
    assert plain._content._dot.get_opacity() == 0.0


def test_a_list_with_nothing_resettable_keeps_no_gutter() -> None:
    """The sections column has no keyed row in it, and is the one already
    short of room for its summaries."""
    listing = SettingsList(Scale(1080))
    listing.set_rows([ActionRow("Appearance", lambda: None, value="›")])
    assert not listing.rows[0]._content._dot.get_visible()


def test_an_external_row_uses_a_compact_trailing_arrow() -> None:
    row = opens_gnome("Region and language", lambda: None, detail="Advanced options")
    assert row._content._detail.get_label() == "Advanced options"
    assert row.value_text == "↗"

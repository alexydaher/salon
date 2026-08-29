# SPDX-License-Identifier: GPL-3.0-or-later
"""The boundary of what a phone may change on the television.

`POST /tune` writes GSettings on behalf of an HTTP client on the LAN, so
the allow-list is the whole of the security story: the handler never names
a key of its own, and everything it will act on is described here.
"""

from __future__ import annotations

import pytest

from salon.core import remote_settings as rs


def test_only_settings_the_television_can_show_you_are_offered() -> None:
    """The rule, not a convenience: a setting whose result the home screen
    cannot display is one there is no advantage to setting from a phone."""
    assert {f.key for f in rs.FIELDS} == {
        "accent-color",
        "theme",
        "tile-scale",
        "row-spacing-scale",
        "safe-area-percent",
        "wallpaper-dim",
    }


def test_every_offered_key_exists_in_the_schema() -> None:
    """A key here that the schema does not have would be a row on the phone
    that fails silently on every drag."""
    schema = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "data"
        / "io.github.alexydaher.Salon.gschema.xml"
    ).read_text(encoding="utf-8")
    for setting in rs.FIELDS:
        assert f'<key name="{setting.key}"' in schema, setting.key


def test_an_unknown_key_is_refused() -> None:
    for key in ("remote-desktop-restore-token", "autostart", "", None, 7, "../theme"):
        assert rs.coerce(key, "anything") is None


def test_a_choice_outside_its_own_options_is_refused() -> None:
    assert rs.coerce("theme", "midnight") is not None
    assert rs.coerce("theme", "hot-pink") is None
    assert rs.coerce("accent-color", "#000000") is None


def test_a_range_takes_a_number_and_nothing_else() -> None:
    assert rs.coerce("tile-scale", 1.0) is not None
    assert rs.coerce("tile-scale", "1.0") is None
    # A bool is an int in Python and would sail through a naive check,
    # arriving as tile-scale 1.0 or 0.0.
    assert rs.coerce("tile-scale", True) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-5.0, 0.5), (99.0, 1.5), (1.02, 1.0), (0.5, 0.5), (1.5, 1.5)],
)
def test_a_range_is_clamped_and_snapped_to_its_own_steps(value: float, expected: float) -> None:
    coerced = rs.coerce("tile-scale", value)
    assert coerced is not None
    assert coerced[1] == pytest.approx(expected)


def test_the_description_carries_what_the_phone_needs_to_draw_each_row() -> None:
    payload = rs.describe({"theme": "ember", "tile-scale": 0.65})
    fields = {f["key"]: f for f in payload["fields"]}  # type: ignore[union-attr]
    assert fields["theme"]["kind"] == rs.CHOICE
    assert {o["value"] for o in fields["theme"]["options"]} >= {"midnight", "ember"}
    assert fields["tile-scale"]["kind"] == rs.RANGE
    assert fields["tile-scale"]["step"] == pytest.approx(0.05)
    # Stored 0..1 and shown 0..100; without this the phone would render
    # "Tile size 0.65".
    assert fields["tile-scale"]["format"] == "percent"


def test_a_value_that_could_not_be_read_costs_its_row_and_not_the_screen() -> None:
    payload = rs.describe({"theme": "ember"})
    assert payload["values"] == {"theme": "ember"}
    assert len(payload["fields"]) == len(rs.FIELDS)  # type: ignore[arg-type]


def test_the_accent_options_are_colours_the_phone_can_draw() -> None:
    """The phone paints any option whose value looks like a colour. A list
    reading "Ember", "Cold blue", "Violet" is a list of words about
    colours, which is the thing this pane exists to stop being."""
    accent = next(f for f in rs.FIELDS if f.key == "accent-color")
    for value, _label in accent.options:
        assert value.startswith("#") and len(value) == 7, value

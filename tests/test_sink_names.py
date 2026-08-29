# SPDX-License-Identifier: GPL-3.0-or-later
"""Audio outputs named by their port, not by their controller.

The four sinks below are the real ones from the development machine, and
they are why this module exists: fifty-five characters each, three of them
differing only in one digit, listed on a screen read from three metres.
"""

from __future__ import annotations

import pytest

from salon.core.sink_names import device_name, device_names, short_name

_REAL = [
    "Tiger Lake-LP Smart Sound Technology Audio Controller HDMI / DisplayPort 3 Output",
    "Tiger Lake-LP Smart Sound Technology Audio Controller HDMI / DisplayPort 2 Output",
    "Tiger Lake-LP Smart Sound Technology Audio Controller HDMI / DisplayPort 1 Output",
    "Tiger Lake-LP Smart Sound Technology Audio Controller Speaker",
]


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (_REAL[0], "HDMI 3"),
        (_REAL[1], "HDMI 2"),
        (_REAL[2], "HDMI 1"),
        (_REAL[3], "Speakers"),
        ("Built-in Audio Analog Stereo Output", "Analogue output"),
        ("USB Headset Mono", "Headset"),
        ("Family 17h HD Audio Controller Digital Stereo Output", "Digital output"),
    ],
)
def test_the_port_is_the_name(description: str, expected: str) -> None:
    assert short_name(description) == expected


def test_every_real_output_gets_a_distinct_name() -> None:
    """The whole point. Three HDMI ports that shorten to one label would be
    worse than the long names, not better."""
    assert len({short_name(d) for d in _REAL}) == len(_REAL)


def test_the_card_survives_as_the_detail_line() -> None:
    detail = device_name(_REAL[0])
    assert "Tiger Lake-LP" in detail
    # The marketing and the port are both gone: the detail line exists to
    # tell two sound cards apart, not to repeat the label above it.
    assert "Smart Sound" not in detail
    assert "HDMI" not in detail


def test_a_description_that_is_only_a_port_has_no_detail() -> None:
    """A detail line repeating the label above it is how a list stops being
    scannable, so "" is a real answer rather than a fallback."""
    assert short_name("Speakers") == "Speakers"
    assert device_name("Speakers") == ""


def test_an_unrecognised_sink_is_still_listed_under_its_own_name() -> None:
    """A sink that does not appear is a worse bug than one with a long name."""
    assert short_name("Scarlett 2i2 4th Gen") == "Scarlett 2i2 4th Gen"


def test_an_empty_description_does_not_produce_an_empty_row() -> None:
    assert short_name("") == "Unknown output"
    assert short_name("   ") == "Unknown output"


def test_one_sound_card_prints_no_card_at_all() -> None:
    """Every real sink here is on the same controller, so the detail line
    was "Tiger Lake-LP" four times — a second line that distinguishes
    nothing is what stops a list being scannable."""
    assert device_names(_REAL) == ["", "", "", ""]


def test_two_cards_are_named_because_then_it_is_the_answer() -> None:
    mixed = [_REAL[0], "Scarlett 2i2 USB Analog Stereo Output"]
    assert device_names(mixed) == ["Tiger Lake-LP", "Scarlett 2i2 USB"]


def test_an_empty_list_stays_empty() -> None:
    assert device_names([]) == []

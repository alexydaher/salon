# SPDX-License-Identifier: GPL-3.0-or-later
"""The locale rules behind the clock. See DECISIONS 2026-09-04."""

from __future__ import annotations

from salon.core import clockformat

# Real `langinfo` values, so these are not assertions about a format string
# somebody invented for the test.
US_T_FMT = "%r"
US_D_FMT = "%m/%d/%Y"
GB_T_FMT = "%H:%M:%S"
GB_D_FMT = "%d/%m/%Y"
ISO_D_FMT = "%Y-%m-%d"


def test_a_12_hour_locale_is_recognised() -> None:
    assert clockformat.uses_12_hour(US_T_FMT)
    assert clockformat.uses_12_hour("%I:%M:%S %p")


def test_a_24_hour_locale_is_recognised() -> None:
    assert not clockformat.uses_12_hour(GB_T_FMT)


def test_an_empty_meridiem_alone_does_not_mean_12_hour() -> None:
    """A few locales append %p to a 24-hour format, where it renders as
    nothing. Reading %p as the marker would put those on a 12-hour dial."""
    assert not clockformat.uses_12_hour("%H:%M:%S %p")


def test_month_order_follows_the_locale() -> None:
    assert clockformat.month_leads(US_D_FMT)
    assert not clockformat.month_leads(GB_D_FMT)
    # Big-endian (ja_JP, en_CA, hu_HU) orders year-month-day, so the
    # month-day pair reads "August 25" there too.
    assert clockformat.month_leads(ISO_D_FMT)


def test_the_preference_overrides_the_locale_in_both_directions() -> None:
    assert clockformat.clock_format("24-hour", US_T_FMT) == "%H:%M"
    assert clockformat.clock_format("12-hour", GB_T_FMT) == "%-I:%M %p"


def test_automatic_asks_the_locale() -> None:
    assert clockformat.clock_format("automatic", US_T_FMT) == "%-I:%M %p"
    assert clockformat.clock_format("automatic", GB_T_FMT) == "%H:%M"


def test_the_hour_is_never_zero_padded_on_a_12_hour_dial() -> None:
    """"08:15 PM" is not how anyone writes it. 24-hour clocks are padded."""
    assert "%-I" in clockformat.clock_format("12-hour", GB_T_FMT)
    assert "%H" in clockformat.clock_format("24-hour", US_T_FMT)


def test_a_format_naming_neither_falls_back_rather_than_guessing() -> None:
    assert not clockformat.month_leads("%Y")


def test_the_date_always_names_the_weekday_and_the_month() -> None:
    for d_fmt in (US_D_FMT, GB_D_FMT, ISO_D_FMT):
        drawn = clockformat.date_format(d_fmt)
        assert "%A" in drawn
        assert "%B" in drawn


def test_the_spoken_form_is_derived_from_the_drawn_one() -> None:
    """They used to be written out separately, and disagreed: the clock was
    always 24-hour while its accessible label was always 12-hour."""
    for preference in ("automatic", "12-hour", "24-hour"):
        for t_fmt, d_fmt in ((US_T_FMT, US_D_FMT), (GB_T_FMT, GB_D_FMT)):
            spoken = clockformat.spoken_format(preference, t_fmt, d_fmt)  # type: ignore[arg-type]
            assert spoken.startswith(clockformat.clock_format(preference, t_fmt))  # type: ignore[arg-type]
            assert spoken.endswith(clockformat.date_format(d_fmt))

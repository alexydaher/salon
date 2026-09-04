# SPDX-License-Identifier: GPL-3.0-or-later
"""Which way round to write the time and the date. Pure — no gi, no I/O.

Salon drew `%H:%M` and `%A, %-d %B` everywhere, hardcoded. On a US
installation that is "20:15 / Tuesday, 25 August" on a television in a
living room whose every other clock says "8:15 PM". The screen-reader
label beside it already used `%-I:%M %p`, so the drawn clock and the
spoken one disagreed about the format of the same instant.

There is no gettext here yet and this is not it: the month and weekday
*names* come from the C library, which has known them all along and was
simply never asked. What this module decides is the two things a format
string cannot get from the locale by itself — whether the hour is on a
12-hour clock, and whether the day comes before the month.

Both answers are derived from `langinfo` strings the caller looks up, so
this stays testable without setting a process-wide locale: the rules are
about the *shape* of a format string, and a format string is data.
"""

from __future__ import annotations

from typing import Literal

ClockPreference = Literal["automatic", "12-hour", "24-hour"]

# `%I` is the 12-hour hour, `%r` is the whole 12-hour time. `%p` alone is
# not enough: a few locales append an empty AM/PM designator to a 24-hour
# format, which renders as a trailing space and means nothing.
_TWELVE_HOUR_MARKERS = ("%I", "%r", "%l")


def uses_12_hour(t_fmt: str) -> bool:
    """Whether a locale's time format (`langinfo` `T_FMT`) is 12-hour."""
    return any(marker in t_fmt for marker in _TWELVE_HOUR_MARKERS)


def month_leads(d_fmt: str) -> bool:
    """Whether a locale writes the month before the day (`langinfo` `D_FMT`).

    US English is `%m/%d/%Y`; most of the rest of the world is `%d/%m/%Y`
    or `%Y-%m-%d`. Only the relative order of the two matters here — the
    separators and the year are not part of the line Salon draws.
    """
    month = _first_index(d_fmt, ("%m", "%b", "%B", "%-m"))
    day = _first_index(d_fmt, ("%d", "%e", "%-d"))
    if month is None or day is None:
        return False
    return month < day


def clock_format(preference: ClockPreference, t_fmt: str) -> str:
    """The strftime format for the big clock.

    `%-I` rather than `%I` because a leading zero on a wall clock is
    wrong — "08:15 PM" is not how anyone writes it — and `%-H` is *not*
    used for the same reason in reverse: 24-hour clocks are conventionally
    zero-padded.
    """
    twelve = uses_12_hour(t_fmt) if preference == "automatic" else preference == "12-hour"
    return "%-I:%M %p" if twelve else "%H:%M"


def date_format(d_fmt: str) -> str:
    """The strftime format for the line under the clock.

    Always a weekday and a full month name: this is a television, not a
    form, and "Tuesday, 25 August" is what it is for. Only the order is in
    question.
    """
    return "%A, %B %-d" if month_leads(d_fmt) else "%A, %-d %B"


def spoken_format(preference: ClockPreference, t_fmt: str, d_fmt: str) -> str:
    """What a screen reader is given: the same instant, said in full.

    Derived from the same two rules as the drawn strings rather than
    written out separately, which is how the two came to disagree.
    """
    return f"{clock_format(preference, t_fmt)}, {date_format(d_fmt)}"


def _first_index(text: str, needles: tuple[str, ...]) -> int | None:
    found = [text.index(needle) for needle in needles if needle in text]
    return min(found) if found else None

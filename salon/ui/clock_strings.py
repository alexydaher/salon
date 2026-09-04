# SPDX-License-Identifier: GPL-3.0-or-later
"""Looking the locale's date and time shapes up, once.

`core/clockformat.py` holds the rules and takes `langinfo` strings as
data, so it stays pure and testable. This is the one place that actually
asks the C library, and it asks once: `nl_langinfo` is cheap but the clock
ticks every second and the answer cannot change without the process being
restarted.

`setlocale` is called here rather than in `main`, because this is the only
part of Salon that depends on it. Python starts every process in the `C`
locale whatever the environment says, so without it `%B` renders English
month names on a French television — which is the failure this whole
module exists to stop, arriving by a different route.
"""

from __future__ import annotations

import locale
from datetime import datetime

from salon.core import clockformat
from salon.core.clockformat import ClockPreference

_initialised = False
_t_fmt = "%H:%M:%S"
_d_fmt = "%d/%m/%y"


def _ensure() -> None:
    global _initialised, _t_fmt, _d_fmt
    if _initialised:
        return
    _initialised = True
    try:
        locale.setlocale(locale.LC_TIME, "")
    except locale.Error:
        # An unset or unsupported LC_TIME is not worth failing over: the
        # defaults above are the 24-hour, day-first shapes Salon already
        # shipped, so this degrades to exactly the previous behaviour.
        return
    try:
        _t_fmt = locale.nl_langinfo(locale.T_FMT) or _t_fmt
        _d_fmt = locale.nl_langinfo(locale.D_FMT) or _d_fmt
    except (AttributeError, ValueError):
        pass


def clock_format(preference: ClockPreference) -> str:
    _ensure()
    return clockformat.clock_format(preference, _t_fmt)


def split_clock(moment: datetime, preference: ClockPreference) -> tuple[str, str]:
    """The hour, and the AM/PM designator on its own.

    Two strings because the console draws them at two sizes on one
    baseline: "8:15 PM" set at the full clock size overflows the column's
    fixed width, and a designator as tall as the digits is not how a clock
    is drawn anyway. The designator is empty on a 24-hour dial.
    """
    _ensure()
    fmt = clockformat.clock_format(preference, _t_fmt)
    if "%p" not in fmt:
        return moment.strftime(fmt), ""
    hour = moment.strftime(fmt.replace(" %p", "").replace("%p", "")).strip()
    return hour, moment.strftime("%p")


def date_format() -> str:
    _ensure()
    return clockformat.date_format(_d_fmt)


def spoken_format(preference: ClockPreference) -> str:
    _ensure()
    return clockformat.spoken_format(preference, _t_fmt, _d_fmt)

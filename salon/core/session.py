# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether Salon is the whole session, or a window in someone's desktop.

Pure — no gi — because the answer changes behaviour that has to be testable
without a display.

The distinction matters because the two cases want opposite things from the
rest of GNOME. Started from Show Applications, Salon is a guest: it should
change nothing about the machine and put everything back. Started as the
session, Salon *is* the machine, and some desktop defaults are actively
wrong for a television — most sharply the screen lock, which asks for a
typed password that no gamepad and no CEC remote can provide.

Detection is by environment, both halves written by the same wayland-sessions
entry: `DesktopNames=GNOME;Salon;` becomes XDG_CURRENT_DESKTOP, and the
entry's filename becomes DESKTOP_SESSION. Either alone is enough; neither is
set by `./bin/salon` from a terminal or by the autostart entry, which is the
behaviour that matters — a guest must never be mistaken for the host.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

SESSION_NAME = "salon"
DESKTOP_NAME = "Salon"


def is_session(environ: Mapping[str, str] | None = None) -> bool:
    """True when this process was started by `gnome-session --session=salon`."""
    env = os.environ if environ is None else environ

    current = env.get("XDG_CURRENT_DESKTOP", "")
    if any(part.strip() == DESKTOP_NAME for part in current.split(":")):
        return True

    return env.get("DESKTOP_SESSION", "").strip() == SESSION_NAME

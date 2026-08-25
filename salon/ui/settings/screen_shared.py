# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""The Settings screen shell (§6.8).

Two panes, like search: sections on the left, the current panel on the
right. RIGHT or OK from a section enters it; LEFT always leaves, whichever
pane and however deep. Panels form a stack, so the tile editor can drill
from rows to one row to one tile and BACK unwinds it a level at a time
rather than dumping the user back at the home screen.

The horizontal axis reads the same way at every depth: **RIGHT goes in,
LEFT comes back out**, and LEFT is never a value change. A row with a set of
values does not change on a direction key at all — OK raises the values as a
small list beside the row (`popup.py`) and the choice is made there, which is
how a console does it and the only arrangement where the alternatives can be
seen before one is picked. See `widgets.py` for the two designs this
replaced and why.

Panels are rebuilt from their `build()` callback whenever anything changes,
rather than mutated in place. A settings list is a few dozen widgets and
the alternative — keeping a retained tree in sync with a catalogue the user
is actively editing — is exactly the kind of bookkeeping that goes wrong
quietly.

Two things here are about being able to *leave*, which is not a detail on a
device with no window controls:

* a legend along the bottom naming what each button does, because BACK
  unwinding one level at a time is only obvious to whoever wrote it;
* LEFT from the section list, and MENU from anywhere, both close the screen
  outright — so there is always a single press between Settings and home
  however deep the tile editor has been walked into.

And one is about being able to *see*: a row marked `preview` collapses this
whole screen to a strip along the bottom edge and lets the live home screen
render behind it, because accent colour, tile size, row density and safe
area cannot be judged against a list of their own names.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gio, GLib, Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.config import Config  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.core.provider import ProviderOutcome  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.providers.registry import ProviderRegistry  # noqa: E402
from salon.ui import motion  # noqa: E402
from salon.ui.motion import SizeReporter  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings import panels as panel_builders  # noqa: E402
from salon.ui.settings import providers as provider_panels  # noqa: E402
from salon.ui.settings import tiles as tile_panels  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.popup import ValuePopup  # noqa: E402
from salon.ui.settings.widgets import ActionRow, SettingsList, SettingsRow  # noqa: E402

_BUMP_DISTANCE_DU = 26.0
_MAX_NOTES = 12


class Pane(Enum):
    SECTIONS = auto()
    PANEL = auto()


__all__ = [name for name in globals() if not name.startswith("__")]

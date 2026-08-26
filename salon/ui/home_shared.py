# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""The home screen (§6.1, §6.2, §6.9): rows, anchoring, focus, launching.

Layout is a stack of `Gtk.Fixed` viewports translated by springs, because
what the brief asks for is not what a scrolled window does. A
`Gtk.ScrolledWindow` scrolls to keep the focused child *visible*; §6.1 wants
the focused row pinned at a fixed vertical anchor and the focused tile
pinned at the left safe-area margin, with everything else moving around
them. So each axis is a `Gtk.Fixed` clipping (`overflow=HIDDEN`) around
oversized content, translated by a `Gsk.Transform` that an
`Adw.SpringAnimation` drives — the same mechanism `ui/tile.py` uses for
scale, and the reason a direction reversal mid-scroll settles physically.

Three geometry decisions here are worth knowing before changing anything:

* **Row viewports span the full window width, not the safe area.** The
  focused tile sits at the safe-area margin and the previous tile peeks
  into the margin beside it, which only works if the clip boundary is the
  screen edge. Clipping at the safe-area margin instead — which is what
  this did originally — cut the focused tile's bloom off in a hard vertical
  line partway across the screen.
* **Scroll offsets are clamped to the content bounds on both axes.** A row
  left-anchors its focused tile right up until doing so would strand empty
  space at the right edge, and then it stops. Without that, focusing the
  last tile of a short row leaves most of a 1920px screen empty, which is
  what it did before.
* **Rows are positioned by absolute y, not stacked in a box.** Every tile
  carries transparent bleed for its bloom to render into, so consecutive
  rows' footprints have to overlap. A box's non-negative spacing can't
  express that; explicit positions can.

All pixel geometry comes from the du scale (`ui/scale.py`) and is rebuilt
when the window moves to a monitor with a different height.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkWayland", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, GdkWayland, Gio, GLib, Graphene, Gsk, Gtk  # noqa: E402

from salon import config as app_config  # noqa: E402
from salon.core import buttons, editing, nowplaying, ranking, tokens  # noqa: E402
from salon.core import config as tile_config  # noqa: E402
from salon.core.bindings import CEC, GAMEPAD, KEYBOARD, Bindings  # noqa: E402
from salon.core.catalog import Catalog, sanitize  # noqa: E402
from salon.core.errors import ConfigError  # noqa: E402
from salon.core.focus import Bump, FocusModel  # noqa: E402
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile  # noqa: E402
from salon.core.provider import CatalogBuild, ProviderOutcome  # noqa: E402
from salon.core.remote import (  # noqa: E402
    RemoteNowPlaying,
    RemoteRow,
    RemoteState,
    RemoteTile,
)
from salon.input.actions import Action, Repeater, RepeaterTiming  # noqa: E402
from salon.input.cec_in import CecSource  # noqa: E402
from salon.input.gamepad import GamepadSource  # noqa: E402
from salon.input.keyboard import action_for_keyval  # noqa: E402
from salon.providers import favourites, recents  # noqa: E402
from salon.providers.registry import ProviderRegistry  # noqa: E402
from salon.services import appinfo, audio, cec_out, pointer_injector, power  # noqa: E402
from salon.services.artwork import (  # noqa: E402
    Artwork,
    ArtworkResolver,
    artwork_drop_dir,
    to_hex,
)
from salon.services.launcher import LauncherService  # noqa: E402
from salon.services.mpris import NowPlayingWatcher  # noqa: E402
from salon.services.pairing import PairingServer  # noqa: E402
from salon.services.pointer_injector import (  # noqa: E402
    PointerInjector,
    onscreen_keyboard_available,
    onscreen_keyboard_enabled,
    set_onscreen_keyboard_enabled,
)
from salon.ui import motion  # noqa: E402
from salon.ui.appsgrid import AppsGrid  # noqa: E402
from salon.ui.backdrop import Backdrop  # noqa: E402
from salon.ui.detailbar import DetailBar  # noqa: E402
from salon.ui.legend import Legend  # noqa: E402
from salon.ui.motion import SizeReporter  # noqa: E402
from salon.ui.nowplaying_status import NowPlayingStatus  # noqa: E402
from salon.ui.onboarding import Onboarding  # noqa: E402
from salon.ui.osd import VolumeOsd  # noqa: E402
from salon.ui.overlays import LaunchingOverlay, MenuFrame, SystemMenu, SystemMenuItem  # noqa: E402
from salon.ui.phonepairing import PhonePairing  # noqa: E402
from salon.ui.remotehint import RemoteHint  # noqa: E402
from salon.ui.scale import Scale, ScaleManager  # noqa: E402
from salon.ui.screensaver import ScreenSaver  # noqa: E402
from salon.ui.search import SearchOverlay  # noqa: E402
from salon.ui.settings.screen import SettingsScreen  # noqa: E402
from salon.ui.statusbar import StatusBar, StatusInfo  # noqa: E402
from salon.ui.textentry import TextEntryOverlay  # noqa: E402
from salon.ui.theme import ThemeManager  # noqa: E402
from salon.ui.tile import (  # noqa: E402
    SPRING_DAMPING_RATIO,
    SPRING_MASS,
    SPRING_STIFFNESS,
    TileMetrics,
    TileWidget,
    metrics_for,
)

# Pixels of cursor motion per poll tick at full stick deflection (~60 ticks/s).
_POINTER_SPEED = 22.0

# Coalesces bursts of filesystem events from a single save (tiles.json's
# save() writes a .tmp file then renames it over the target; artwork drops
# can also arrive as several events for one file) into one rebuild.
_RELOAD_DEBOUNCE_MS = 300

# How long to wait, after an app closes, before opening the one the phone
# asked for over the top of it. Long enough for the compositor to hand focus
# back to Salon, because the next launch's return detection is the window
# going *inactive* and a window that is already inactive never does.
_RELAUNCH_DELAY_MS = 250

# How many results the phone's search returns, and how large an icon it
# resolves for a card on it. The phone shows about six results at a time and
# nobody scrolls a remote control; past this the ranking is doing work
# nobody reads. The icon size is a phone card's worth of pixels on a dense
# screen, not the television's, which would be four times the download.
_PHONE_SEARCH_RESULTS = 40
_PHONE_ICON_SIZE_PX = 256

_DIRECTIONS = (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT)

# How often the held-direction repeater is polled. Independent of the
# Repeater's own fire cadence (400/120/60ms) — this just needs to be
# frequent enough not to miss the fastest of those intervals.
_REPEAT_POLL_MS = 30

# Boundary rubber-band (§6.2): hitting the end of a row or the last row
# produces a short overshoot-and-settle rather than silence, which reads as
# a broken remote.
_BUMP_DISTANCE_DU = 26.0
# How far the row band's top and bottom edges fade out *when there is
# something hanging over them* — see `HomeView._update_edge_fades`.
#
# Short, and doing a different job from the fade that used to be here. The
# band no longer reaches under the two bars at all — it is inset to the gap
# between them — so nothing has to be dimmed to keep it off the clock. What
# is left is that a tile cut by a hard clip edge reads as a rendering fault,
# and a tile's bloom needs somewhere to go. Forty du is about a quarter of a
# wide tile: enough that a row leaving the band looks like it is leaving,
# little enough that it costs nothing while it goes.
_EDGE_FADE_DU = 40.0
_BUMP_MS = 90

# The phone remote's name on the shared pairing server. Named rather than
# anonymous because a text field can be holding the same server at the same
# time and neither may stop it out from under the other.
_REMOTE_HOLDER = "phone-remote"
# The corner card's own hold on the pairing server (ui/remotehint.py).
# Separate from the one above so that Settings' toggle and "there is
# nothing to press with" are independent reasons for the server to run,
# and neither can take the port from under the other.
_HINT_HOLDER = "remote-hint"
# How often the corner card re-asks whether a phone is talking to us.
# `connected` is a time window, so nothing signals its expiry; two
# seconds is well inside the window and costs one property read.
_HINT_POLL_MS = 2000

_FALLBACK_VIEWPORT_WIDTH_PX = 1920
_FALLBACK_VIEWPORT_HEIGHT_PX = 1080


def _point(x: float, y: float) -> Graphene.Point:
    point = Graphene.Point()
    point.init(x, y)
    return point


def _translate(dx: float, dy: float) -> Gsk.Transform:
    return Gsk.Transform.new().translate(_point(dx, dy))


__all__ = [name for name in globals() if not name.startswith("__")]

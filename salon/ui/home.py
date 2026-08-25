# SPDX-License-Identifier: GPL-3.0-or-later
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
from salon.core import config as tile_config  # noqa: E402
from salon.core import editing, nowplaying, ranking, tokens  # noqa: E402
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
    onscreen_keyboard_enabled,
    set_onscreen_keyboard_enabled,
)
from salon.ui import motion  # noqa: E402
from salon.ui.appsgrid import AppsGrid  # noqa: E402
from salon.ui.backdrop import Backdrop  # noqa: E402
from salon.ui.detailbar import DetailBar  # noqa: E402
from salon.ui.motion import SizeReporter  # noqa: E402
from salon.ui.onboarding import Onboarding  # noqa: E402
from salon.ui.osd import VolumeOsd  # noqa: E402
from salon.ui.overlays import LaunchingOverlay, SystemMenu, SystemMenuItem  # noqa: E402
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


class _LayoutViewport(Gtk.Fixed):
    """A Gtk.Fixed that reports its own resizes and fades out at the top and
    bottom edges.

    The resize part exists because every layout constant here is derived
    from the window's real size and Gtk.Widget has no resize signal, so the
    one place that knows the size changed is size_allocate.

    The fade exists because the rows are taller than the screen whenever
    there are more than about three of them, and a row sliced off by a hard
    clip edge reads as a rendering fault. Masking the *rows* rather than
    painting a scrim over them keeps the backdrop's ambient glow intact
    underneath. Each end is faded by however much is actually overhanging
    it, so an end with nothing past it is not faded at all — a constant ramp
    at the top dimmed the first row's heading permanently.

    It used to be doing a second job as well, and no longer is. The fades
    were the width of the two bars — the status strip and the detail strip —
    because this viewport spanned the whole window and rows really did pass
    behind the clock; dimming them was what kept the clock readable. The
    viewport is now inset to the gap between the bars instead
    (`HomeView._apply_viewport_insets`), so nothing overlaps them at all and
    what is left here is a short softening of the band's own edges.
    """

    def __init__(self) -> None:
        super().__init__()
        self._top_fade = 0.0
        self._bottom_fade = 0.0

    def set_fades(self, top: float, bottom: float) -> None:
        self._top_fade = top
        self._bottom_fade = bottom
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0 or (self._top_fade <= 0 and self._bottom_fade <= 0):
            Gtk.Fixed.do_snapshot(self, snapshot)
            return

        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)

        snapshot.push_mask(Gsk.MaskMode.ALPHA)
        opaque = Gdk.RGBA()
        opaque.red = opaque.green = opaque.blue = opaque.alpha = 1.0
        clear = Gdk.RGBA()
        clear.red = clear.green = clear.blue = clear.alpha = 0.0
        stops = []
        for offset, color in (
            (0.0, clear),
            (self._top_fade / height, opaque),
            (1.0 - self._bottom_fade / height, opaque),
            (1.0, clear),
        ):
            stop = Gsk.ColorStop()
            stop.offset = max(0.0, min(1.0, offset))
            stop.color = color
            stops.append(stop)
        snapshot.append_linear_gradient(bounds, _point(0.0, 0.0), _point(0.0, height), stops)
        snapshot.pop()

        Gtk.Fixed.do_snapshot(self, snapshot)
        snapshot.pop()


class _AxisSpring:
    """Animates one translate offset along one axis, reapplying it as a
    Gsk.Transform on `child` within `viewport` every tick.

    Shared by the vertical row anchor and each row's horizontal tile scroll,
    so both move with the same physics. Gsk.Transform is immutable with
    chaining semantics in PyGObject (§11) — every value has to be reassigned,
    never mutated in place.
    """

    def __init__(
        self,
        viewport: Gtk.Fixed,
        child: Gtk.Widget,
        *,
        vertical: bool,
        on_value: Callable[[float], None] | None = None,
    ) -> None:
        self._viewport = viewport
        self._child = child
        self._vertical = vertical
        self._value = 0.0
        self._resting = 0.0
        self._animations_enabled = True
        # Called on every frame of the animation, not just when it settles:
        # the band's edge fades are a function of how far the content has
        # actually moved, and reading the target instead would snap them to
        # full strength while the rows were still travelling.
        self._on_value = on_value

        params = Adw.SpringParams.new(SPRING_DAMPING_RATIO, SPRING_MASS, SPRING_STIFFNESS)
        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.SpringAnimation.new(viewport, 0.0, 0.0, params, target)

        bump_target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._bump_animation = Adw.TimedAnimation.new(viewport, 0.0, 0.0, _BUMP_MS, bump_target)
        self._bump_animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self._bump_animation.connect("done", self._on_bump_done)

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = enabled

    @property
    def value(self) -> float:
        return self._value

    def _on_tick(self, value: float) -> None:
        self._value = value
        dx, dy = (0.0, value) if self._vertical else (value, 0.0)
        self._viewport.set_child_transform(self._child, _translate(dx, dy))
        if self._on_value is not None:
            self._on_value(value)

    def animate_to(self, target_value: float) -> None:
        self._resting = target_value
        if target_value == self._value:
            return
        if not self._animations_enabled:
            self.jump_to(target_value)
            return
        self._animation.set_value_from(self._value)
        self._animation.set_value_to(target_value)
        self._animation.play()

    def jump_to(self, value: float) -> None:
        self._resting = value
        self._on_tick(value)

    def bump(self, distance: float) -> None:
        """§6.2's rubber-band: a short overshoot away from the boundary that
        springs back, so hitting the end of a row is felt rather than
        silently ignored."""
        if not self._animations_enabled:
            return
        self._animation.pause()
        self._bump_animation.set_value_from(self._resting)
        self._bump_animation.set_value_to(self._resting + distance)
        self._bump_animation.play()

    def _on_bump_done(self, _animation: Adw.Animation) -> None:
        target = self._resting
        self._animation.set_value_from(self._value)
        self._animation.set_value_to(target)
        self._animation.play()


class _RowWidgets:
    """The widgets and geometry for one catalogue row."""

    def __init__(
        self,
        heading: Gtk.Label,
        viewport: Gtk.Fixed,
        tiles_box: Gtk.Fixed,
        tiles: list[TileWidget],
        metrics: TileMetrics,
    ) -> None:
        self.heading = heading
        self.viewport = viewport
        self.tiles_box = tiles_box
        self.tiles = tiles
        self.metrics = metrics
        self.scroller = _AxisSpring(viewport, tiles_box, vertical=False)

    @property
    def content_width(self) -> float:
        if not self.tiles:
            return 0.0
        return len(self.tiles) * self.metrics.step - self.metrics.gap


def _is_browser_launch(tile: Tile) -> bool:
    """Whether launching this tile hands control to a browser window we
    can't reach directly — the case where the gamepad should drive the
    system pointer instead of tile navigation."""
    if tile.launch.kind is LaunchKind.URL:
        return True
    return tile.launch.kind is LaunchKind.DESKTOP and tile.launch.target == "com.google.Chrome"


def _seed_rows() -> list[Row]:
    """Written to ~/.config/salon/tiles.json the first time Salon runs and
    finds no config there. Hand-editing the file is always possible and
    never required — this just gives a fresh install something real to look
    at instead of an empty screen."""
    return [
        Row(
            id="apps",
            title="Apps",
            provider_id="static",
            tiles=[
                Tile(
                    id="files",
                    title="Files",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.Nautilus"),
                    artwork=None,
                    icon_name="org.gnome.Nautilus",
                    accent=None,
                ),
                Tile(
                    id="text-editor",
                    title="Text Editor",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.TextEditor"),
                    artwork=None,
                    icon_name="org.gnome.TextEditor",
                    accent=None,
                ),
                Tile(
                    id="calculator",
                    title="Calculator",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.Calculator"),
                    artwork=None,
                    icon_name="org.gnome.Calculator",
                    accent=None,
                ),
                Tile(
                    id="chrome",
                    title="Chrome",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="com.google.Chrome"),
                    artwork=None,
                    icon_name="com.google.Chrome",
                    accent=None,
                ),
                Tile(
                    id="settings",
                    title="Settings",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.BUILTIN, target="settings"),
                    artwork=None,
                    icon_name="preferences-system-symbolic",
                    accent=None,
                ),
            ],
        ),
        Row(
            id="streaming",
            title="Streaming",
            provider_id="static",
            tiles=[
                Tile(
                    id="netflix",
                    title="Netflix",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.netflix.com",
                        browser_profile="netflix",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent="#E50914",
                ),
                Tile(
                    id="prime-video",
                    title="Prime Video",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.primevideo.com",
                        browser_profile="prime-video",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent="#00A8E1",
                ),
                Tile(
                    id="geforce-now",
                    title="GeForce NOW",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.FLATPAK, target="com.nvidia.geforcenow"),
                    artwork=None,
                    icon_name="com.nvidia.geforcenow",
                    accent="#76B900",
                ),
            ],
        ),
        Row(
            id="web",
            title="Web",
            provider_id="static",
            tiles=[
                Tile(
                    id="gnome-org",
                    title="GNOME.org",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.gnome.org",
                        browser_profile="gnome-org",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent=None,
                ),
            ],
        ),
    ]


class HomeView(Gtk.Box):
    def __init__(
        self,
        application: Gtk.Application,
        scale_manager: ScaleManager,
        theme_manager: ThemeManager,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._application = application
        self._scale_manager = scale_manager
        self._theme_manager = theme_manager
        self._scale = scale_manager.scale
        self._config_path = tile_config.default_config_path()
        self._settings = Gio.Settings.new(app_config.APP_ID)

        # The user's button overrides, shared by all three input sources.
        # Read before any of them is built, and rebuilt whenever the
        # setting changes so a rebind takes effect on the next press
        # rather than the next start.
        self._bindings = Bindings(self._settings.get_value("input-bindings").unpack())
        self._settings.connect("changed::input-bindings", lambda *_: self._reload_bindings())
        # Set while the settings screen is waiting for someone to press the
        # button they want to bind; see _capture_binding.
        self._binding_capture: Callable[[str, int], None] | None = None

        self._viewport_width = _FALLBACK_VIEWPORT_WIDTH_PX
        self._viewport_height = _FALLBACK_VIEWPORT_HEIGHT_PX
        # Filled by _recompute_row_tops once the rows exist; every geometry
        # helper below reads them, including on the first pass before any
        # row has been built.
        self._row_tops: list[float] = []
        self._content_height_px = 0.0

        self._toast_overlay = Adw.ToastOverlay()
        self.append(self._toast_overlay)

        self._overlay = Gtk.Overlay()
        self._toast_overlay.set_child(self._overlay)

        self._backdrop = Backdrop()
        self._overlay.set_child(self._backdrop)
        self._apply_wallpaper()
        for key in ("changed::wallpaper-path", "changed::wallpaper-dim"):
            self._settings.connect(key, lambda *_: self._apply_wallpaper())

        self._viewport = _LayoutViewport()
        self._viewport.set_overflow(Gtk.Overflow.HIDDEN)
        # propagate_minimum=False, for the third time in this project and the
        # last place that was missing it: a Gtk.Fixed measures to fit its
        # children, so a band around four rows of tiles asks to be taller
        # than the window and an overlay child is granted exactly that. The
        # margins in `_apply_viewport_insets` were being applied to a widget
        # that then overhung the screen anyway, which is why tiles were
        # drawn across the detail strip, why the band's bottom fade landed
        # off-screen, and why `_viewport_height` was the *content's* height
        # — so `_row_anchor_y` concluded everything fitted and the home
        # screen stopped scrolling altogether.
        self._viewport_host = SizeReporter(
            self._viewport, self._on_viewport_resized, propagate_minimum=False
        )
        self._viewport_host.set_hexpand(True)
        self._viewport_host.set_vexpand(True)
        self._overlay.add_overlay(self._viewport_host)

        # A Fixed rather than a Box: consecutive rows' footprints overlap,
        # because every tile carries transparent bleed for its bloom, and a
        # box's non-negative spacing can't express an overlap.
        self._rows_content = Gtk.Fixed()
        self._viewport.put(self._rows_content, 0, 0)
        self._row_anchor = _AxisSpring(
            self._viewport,
            self._rows_content,
            vertical=True,
            on_value=lambda _value: self._update_edge_fades(),
        )

        # One server, one port, one code for the whole application: the
        # phone remote and an open text field can both want the phone at
        # once. Actions arrive as if from any other input source, which is
        # the whole reason the vocabulary exists.
        #
        # Built before the overlay children rather than beside the rest of
        # the phone state below, because the corner pairing card reads it
        # and has to go into the overlay under the screensaver.
        self._pairing = PairingServer(
            on_action=self._on_phone_action,
            on_pointer=self._on_phone_pointer,
            on_click=self._on_phone_click,
            on_locked=self._on_phone_locked,
            on_launch=self._on_phone_launch,
            on_transport=self._on_phone_transport,
            art_for=self._art_for_phone,
            pointer_ready=lambda: self._pointer.ready,
            on_remote_text=self._type_remotely,
            on_search=self._search_for_phone,
            on_tile_action=self._on_phone_tile_action,
            on_volume=self._on_phone_volume,
            on_mute=self._on_phone_mute,
            on_scroll=self._on_phone_scroll,
            on_scroll_end=self._on_phone_scroll_end,
            on_button=self._on_phone_button,
        )

        # Two corners, not one strip: what the machine is on the left, what
        # the user can press on the right. See ui/statusbar.py.
        self._status_info = StatusInfo(self._scale)
        self._overlay.add_overlay(self._status_info)

        self._status_bar = StatusBar(
            self._scale,
            on_search=self._open_search,
            on_apps=self._open_apps,
            on_phone=self._open_phone_pairing,
            on_settings=lambda: self._open_settings(),
            on_power=self._show_system_menu,
        )
        # UP from the first row of tiles moves into the bar; DOWN comes back.
        self._nav_focused = False
        self._overlay.add_overlay(self._status_bar)

        # Below the rows and above the bottom safe margin: what the cursor
        # is on and what OK will do with it. Its height is reserved in the
        # row stack's bottom inset, so rows never scroll underneath it.
        self._detail_bar = DetailBar(self._scale)
        self._overlay.add_overlay(self._detail_bar)

        # The standing pairing code, bottom right. Only ever on screen when
        # there is neither a controller nor a phone — see _update_remote_hint
        # and ui/remotehint.py. Added here so every full-bleed overlay above
        # (search, the grid, Settings, both menus) covers it.
        self._gamepad_count = 0
        self._remote_hint = RemoteHint(
            self._scale, self._pairing, on_open=self._open_phone_pairing
        )
        self._overlay.add_overlay(self._remote_hint)

        # What is playing, wherever it is playing. Takes the detail strip
        # while it has something to say, and gives the remote's transport
        # keys somewhere to go — Action.PLAY_PAUSE has been in the
        # vocabulary since the beginning and was handled nowhere.
        self._now_playing = NowPlayingWatcher(self._on_now_playing)
        self._now_playing.start()

        self._launching_overlay = LaunchingOverlay(self._scale)
        self._overlay.add_overlay(self._launching_overlay)

        # Above everything except the menus that have to survive anything:
        # it replaces the whole screen, and it is dismissed by any press
        # rather than navigated.
        self._screensaver = ScreenSaver(self._scale)
        self._overlay.add_overlay(self._screensaver)
        self._idle_id: int | None = None
        self._last_input = time.monotonic()
        self._apply_screensaver_setting()

        self._osd = VolumeOsd(self._scale)
        self._overlay.add_overlay(self._osd)

        # The reachable escape hatch on a fullscreen, keyboard-less kiosk:
        # without this there is no way to suspend/shut down the machine or
        # exit Salon at all. CanSuspend/CanReboot/CanPowerOff are one cheap
        # synchronous D-Bus round-trip at startup (same category as the
        # other one-time sync setup calls here, e.g. Gio.Settings.new) so
        # the menu only ever offers actions logind says are available.
        self._artwork = ArtworkResolver(
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()),
            on_fetched=self._rebuild_row_widgets,
        )

        # What the phone draws, kept in step with what is on the television.
        # Rebuilt with the row widgets — which is also when artwork arrives,
        # so a poster that finishes downloading shows up on the phone too —
        # and republished whenever the cursor or the player moves.
        self._remote_rows: tuple[RemoteRow, ...] = ()
        # Every installed application, for the phone's search. Scanned once
        # on a worker thread when the remote starts rather than per query:
        # `/search` answers on the main loop, so the one thing it must not
        # do is touch the disk. Empty until the scan lands, which costs the
        # first search or two its installed-app half and nothing else.
        self._phone_apps: list[Tile] = []
        self._phone_apps_scanned = False
        # What the volume slider on the phone shows. Read from the sink
        # asynchronously, so the snapshot carries the last known value
        # rather than blocking a publish on PulseAudio.
        self._phone_volume = -1.0
        self._phone_muted = False
        self._current_player: nowplaying.Player | None = None

        self._search = SearchOverlay(
            self._scale,
            self._artwork,
            self._pairing,
            on_launch=self._launch_tile,
            on_close=self.grab_focus,
        )
        self._overlay.add_overlay(self._search)

        self._apps_grid = AppsGrid(
            self._scale,
            self._artwork,
            on_launch=self._launch_tile,
            on_close=self.grab_focus,
        )
        self._overlay.add_overlay(self._apps_grid)

        self._rows: list[_RowWidgets] = []
        self._config = self._load_config()
        self._provider_registry = ProviderRegistry(self._settings)
        self._provider_outcomes: tuple[ProviderOutcome, ...] = ()
        self._catalog_generation = 0

        # Added after search so they stack above it, and text entry above
        # Settings, because the keyboard is what Settings opens on top of
        # itself to fill in a tile's title or URL.
        self._settings_screen = SettingsScreen(
            self._scale,
            self._settings,
            config=self._config,
            save_config=self._save_config,
            toast=self._toast,
            edit_text=self._edit_text,
            installed_apps=appinfo.list_installed_async,
            provider_registry=self._provider_registry,
            provider_outcomes=lambda: self._provider_outcomes,
            reload_catalog=lambda: self._refresh_catalog(preserve_focus=True),
            quit_app=self._application.quit,
            on_close=self.grab_focus,
            phone_remote_running=self.phone_remote_running,
            set_phone_remote=self.set_phone_remote,
            phone_remote_hint=self.phone_remote_hint,
            pointer_backend=lambda: self._pointer.backend,
            bindings=self.bindings,
            capture_binding=self.begin_binding_capture,
            cancel_capture=self.cancel_binding_capture,
            rebind=self.rebind,
            reset_bindings=self.reset_bindings,
            version=app_config.VERSION,
            config_path=str(self._config_path),
        )
        self._overlay.add_overlay(self._settings_screen)

        # Both menus go on *top* of search, the all-apps grid and Settings.
        # Overlay children paint in the order they were added, and while
        # these sat underneath, OPTIONS over a tile in the grid opened a
        # menu that was drawn behind the grid and swallowed every button.
        self._system_menu = SystemMenu(self._build_system_menu_items(), self._scale)
        self._overlay.add_overlay(self._system_menu)

        # Same widget, different contents: what OPTIONS opens over whichever
        # tile is under the cursor. Built empty and filled per press, since
        # its items depend on the tile (and on whether it's already pinned).
        self._tile_menu = SystemMenu([], self._scale)
        self._overlay.add_overlay(self._tile_menu)

        # Opened from the system menu, so it stacks above both menus. The
        # phone remote used to be reachable only from Settings → Input and
        # from the search keyboard; MENU is the one button that works from
        # anywhere, which is where the best input Salon has belongs.
        self._phone_pairing = PhonePairing(
            self._scale,
            self._pairing,
            on_start=lambda: self.set_phone_remote(True),
            on_close=self._close_phone_pairing,
            on_stop=self._stop_phone_remote,
        )
        self._overlay.add_overlay(self._phone_pairing)

        self._text_entry = TextEntryOverlay(self._scale, self._pairing)
        self._overlay.add_overlay(self._text_entry)

        # Topmost, and shown before anything else on a first run: it is the
        # only thing on screen that explains the buttons.
        self._onboarding = Onboarding(self._scale, self._finish_onboarding)
        self._overlay.add_overlay(self._onboarding)

        # The way back from a launched application, and the one transition
        # nothing else can supply: GNOME Kiosk's compositor has no destroy
        # animation at all, so without this a closing child leaves Salon
        # simply *there*, mid-frame, with the compositor's black behind it.
        # Under Shell it is a second animation over the Shell's own, which
        # is why it is a fade rather than anything with a direction.
        # Set before the first tiles are built, because a TileWidget reads
        # the shared spring once at construction. A speed changed later only
        # reaches existing tiles through the rebuild that
        # `_apply_animation_setting` forces for exactly that reason.
        motion.set_animation_speed(self._settings.get_double("animation-scale"))
        self._return_fade = motion.FadeIn(self._overlay, motion.RETURN_FADE_MS)
        # Every surface that opens over the home screen. Collected so the
        # reduced-motion decision reaches all of them in one pass.
        self._faded_surfaces: tuple[motion.Fadable, ...] = (
            self._search,
            self._apps_grid,
            self._settings_screen,
            self._system_menu,
            self._tile_menu,
            self._phone_pairing,
            self._launching_overlay,
        )

        # Starts empty and fills in when the providers answer — usually
        # within a frame or two, and never blocking startup on one of them.
        self._catalog = Catalog([])
        self._focus = FocusModel([])
        self._apply_metrics()
        self._rebuild_row_widgets()
        self._refresh_catalog(preserve_focus=False)

        # Drives accelerating repeat (400ms initial delay, 120ms interval,
        # ramping to 60ms after six repeats — §6.2) for whichever direction
        # is currently held, from either keyboard or gamepad.
        self._repeater = Repeater(time.monotonic, self._repeat_timing())
        self._repeat_action: Action | None = None
        self._repeat_timer_id: int | None = None
        # Keyboard-only: GTK re-fires key-pressed on OS auto-repeat while a
        # key is held, using the same keyval each time. We drive our own
        # repeat cadence instead, so those re-fires need to be told apart
        # from a fresh physical press and swallowed.
        self._held_keyvals: set[int] = set()

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        controller.connect("key-released", self._on_key_released)
        self.add_controller(controller)
        self.set_can_focus(True)
        self.set_focusable(True)
        # This widget is the one that actually holds GTK focus — the tiles
        # never do — so it is what assistive technology lands on, and it has
        # to say both what it is and which tile the cursor is on. The latter
        # is ACTIVE_DESCENDANT, republished by _update_focus.
        self.set_accessible_role(Gtk.AccessibleRole.GRID)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Home"])

        # Mouse is a first-class input here, not an afterthought: the brief's
        # own hardware list is "controller, or a phone acting as a trackpad",
        # and a phone trackpad only ever produces pointer events.
        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES
            | Gtk.EventControllerScrollFlags.DISCRETE
        )
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)
        pointer_motion = Gtk.EventControllerMotion()
        pointer_motion.connect("motion", self._on_pointer_motion)
        self.add_controller(pointer_motion)
        self._last_pointer_xy: tuple[float, float] | None = None
        # Cursor stays hidden until the mouse actually moves: a TV launcher
        # that boots with an arrow parked in the middle of the screen looks
        # broken, and the pointer is only one of three input paths here.
        self._pointer_visible = False

        self._pointer_mode = False
        self._child_active = False
        # A tile the phone asked for while another app was still in front;
        # started once that one has gone. See _launch_tile.
        self._pending_launch: Tile | None = None
        self._current_launch_is_browser = False
        self._pointer = PointerInjector(
            on_ready=self._on_pointer_ready,
            load_restore_token=lambda: self._settings.get_string(
                "remote-desktop-restore-token"
            ),
            save_restore_token=lambda token: self._settings.set_string(
                "remote-desktop-restore-token", token
            ),
            backend=self._settings.get_string("input-injection"),
        )

        self._launcher = LauncherService(
            application,
            idle_inhibit_seconds=self._settings.get_int("idle-inhibit-seconds"),
            browser_scale_factor=tokens.browser_scale_factor(self._scale.viewport_height_px),
        )
        self._launcher.on_launch_started = self._on_launch_started
        self._launcher.on_child_focused = self._on_child_focused
        self._launcher.on_launch_timed_out = self._on_launch_timed_out
        self._launcher.on_returned = self._on_returned
        self._launcher.on_error = self._on_launch_error

        # Keep a reference alive — GamepadSource holds the only strong ref
        # to the Manette.Monitor/Device connections that keep signals firing.
        self._gamepad = GamepadSource(
            self._on_gamepad_action,
            on_right_stick=self._on_right_stick,
            on_action_release=self._stop_repeat,
            bindings=self._bindings,
            on_raw=lambda code: self._on_raw_input(GAMEPAD, code),
            on_devices_changed=self._on_gamepads_changed,
        )
        self._gamepad_count = self._gamepad.device_count

        # The TV's own remote, over HDMI-CEC. Same reference-keeping reason:
        # the source owns the cec-client subprocess and its stream reader.
        self._cec = CecSource(
            self._on_cec_action,
            bindings=self._bindings,
            on_raw=lambda code: self._on_raw_input(CEC, code),
        )
        self._apply_cec_setting()
        self._settings.connect("changed::cec-enabled", lambda *_: self._apply_cec_setting())
        self._settings.connect(
            "changed::screensaver-minutes", lambda *_: self._apply_screensaver_setting()
        )

        self._reload_timeout_id: int | None = None
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        config_dir = Gio.File.new_for_path(str(self._config_path.parent))
        # Watch the directory, not the file: our own save() (and any editor)
        # writes via a temp file + rename, which some monitor backends only
        # report against the containing directory.
        self._config_monitor = config_dir.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self._config_monitor.connect("changed", self._on_config_dir_changed)

        self._artwork_reload_timeout_id: int | None = None
        artwork_dir = artwork_drop_dir()
        artwork_dir.mkdir(parents=True, exist_ok=True)
        self._artwork_monitor = Gio.File.new_for_path(str(artwork_dir)).monitor_directory(
            Gio.FileMonitorFlags.NONE, None
        )
        self._artwork_monitor.connect("changed", self._on_artwork_dir_changed)

        self._scale_manager.subscribe(self._on_scale_changed)
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.connect(
                "notify::gtk-enable-animations", lambda *_: self._apply_animation_setting()
            )
        for key in ("reduced-motion", "animation-scale"):
            self._settings.connect(f"changed::{key}", lambda *_: self._apply_animation_setting())
        # Once at startup as well as on every change: reduced motion is a
        # setting that is already true when Salon opens, and nothing else
        # hands it to the tiles, the springs or the surfaces' fades.
        self._apply_animation_setting()
        for key in ("tile-scale", "row-spacing-scale", "safe-area-percent"):
            self._settings.connect(f"changed::{key}", lambda *_: self._apply_layout_settings())
        for key in ("key-repeat-initial-ms", "key-repeat-interval-ms"):
            self._settings.connect(f"changed::{key}", lambda *_: self._apply_repeat_settings())
        self._settings.connect(
            "changed::volume-step-percent",
            lambda *_: audio.set_volume_step(self._settings.get_int("volume-step-percent")),
        )
        self._settings.connect("changed::audio-sink", lambda *_: self._apply_preferred_sink())
        # The accent lives in two worlds: CSS (ThemeManager's provider) and
        # do_snapshot (tile ring, backdrop pool). Only the second needs a
        # nudge to redraw.
        self._theme_manager.subscribe(self._on_accent_changed)
        audio.set_volume_step(self._settings.get_int("volume-step-percent"))
        self._apply_preferred_sink()

        self._settings.connect("changed::remote-hint", lambda *_: self._update_remote_hint())
        self._update_remote_hint()
        GLib.timeout_add(_HINT_POLL_MS, self._poll_remote_hint)

    # --- the standing pairing code ---------------------------------------

    def _on_gamepads_changed(self, count: int) -> None:
        self._gamepad_count = count
        self._update_remote_hint()

    def _poll_remote_hint(self) -> bool:
        """`PairingServer.connected` is a time window, so nothing signals
        its expiry — a phone that closes the page just stops talking."""
        self._update_remote_hint()
        return bool(GLib.SOURCE_CONTINUE)

    def _update_remote_hint(self) -> None:
        """Decide whether the corner card is on screen, and keep the pairing
        server up for as long as it is.

        The rule is "does the user have anything to press with": a pad
        plugged in, or a phone that spoke to us in the last few seconds.
        With neither, the card is the only way to get an input device onto
        this machine that does not already require one.

        The hold is dropped a beat late on purpose. `release()` stops the
        server outright once the last holder lets go, so letting go the
        instant a phone connects would tear down the session that phone just
        opened. The card hides immediately; the hold goes when there is no
        longer a phone to lose.
        """
        wanted = self._settings.get_boolean("remote-hint") and self._gamepad_count == 0
        if wanted:
            if not self._pairing.holds(_HINT_HOLDER):
                self._start_remote(_HINT_HOLDER, take_pointer=False)
        elif self._pairing.holds(_HINT_HOLDER) and not self._pairing.connected:
            self._pairing.release(_HINT_HOLDER)
        if (
            self._pairing.connected
            and self._pairing.holds(_HINT_HOLDER)
            and self._settings.get_boolean("gamepad-pointer")
            and not self._pointer.ready
        ):
            # A phone answered the card. Now the trackpad is a thing someone
            # is about to use, so the grant is worth asking for.
            self._start_pointer_session()
        visible = wanted and not self._pairing.connected and self._remote_hint.refresh()
        self._remote_hint.set_visible(visible)

    # --- scale / geometry -------------------------------------------------

    @property
    def _animations_enabled(self) -> bool:
        """§7.2: respect gtk-enable-animations and the reduced-motion
        override. When off, focus changes are instant — the tile's ring and
        bloom carry the indication instead of the motion."""
        if self._settings.get_boolean("reduced-motion"):
            return False
        # "Animation speed: Off" is the third way to say the same thing, and
        # it has to be answered here rather than only inside `motion` — the
        # springs and fades ask this property, not the speed.
        if not motion.enabled():
            return False
        settings = Gtk.Settings.get_default()
        if settings is None:
            return True
        return bool(settings.get_property("gtk-enable-animations"))

    def _apply_metrics(self) -> None:
        scale = self._scale
        # The three user-facing geometry preferences (§6.8 Appearance) are
        # read here rather than cached at startup, so a change lands as soon
        # as the row widgets are rebuilt.
        self._tile_scale = self._settings.get_double("tile-scale")
        self._metrics = metrics_for(scale, size_scale=self._tile_scale)
        self._safe_margin = scale.du(
            tokens.REFERENCE_VIEWPORT_HEIGHT_PX
            * self._settings.get_double("safe-area-percent")
            / 100.0
        )
        heading = tokens.type_token("row-heading")
        self._heading_height = scale.du(heading.size_du * 1.35)
        self._heading_gap = scale.du(tokens.ROW_HEADING_GAP_DU)
        self._row_gap = scale.du(
            tokens.ROW_GAP_DU * self._settings.get_double("row-spacing-scale")
        )
        self._status_height = scale.du(tokens.STATUS_BAR_HEIGHT_DU)
        self._detail_height = scale.du(tokens.DETAIL_BAR_HEIGHT_DU)
        self._bump_distance = scale.du(_BUMP_DISTANCE_DU)

    def _recompute_row_tops(self) -> None:
        """Stack the rows, giving each one its *own* height.

        Rows do not all have the same tile aspect — a poster row is 300du
        tall where a wide row is 180 — so a single row pitch is wrong the
        moment a catalogue mixes them. It was: a poster row's tiles ran
        straight through the heading of the row beneath it, and because the
        same pitch also fed `_content_height`, the whole stack measured
        shorter than it was and the screen decided it had nothing to scroll.
        """
        tops: list[float] = []
        y = 0.0
        for row in self._rows:
            tops.append(y)
            y += self._heading_height + self._heading_gap + row.metrics.height + self._row_gap
        self._row_tops = tops
        trailing = self._rows[-1].metrics.bleed if self._rows else 0.0
        # The last row's bleed counts as content. It is the room the tile
        # needs for the focus growth and the bloom, and a scroll limit that
        # stopped at the card's own bottom edge put both of them past the end
        # of the band: the focused tile in the last row had its ring sliced
        # off by the clip, which is exactly the rendering fault the edge fade
        # exists to avoid.
        self._content_height_px = max(0.0, y - self._row_gap + trailing)

    def _row_top(self, row_index: int) -> float:
        if 0 <= row_index < len(self._row_tops):
            return self._row_tops[row_index]
        return 0.0

    def _row_tile_top(self, row_index: int) -> float:
        return self._row_top(row_index) + self._heading_height + self._heading_gap

    def _focused_tile_height(self) -> float:
        if 0 <= self._focus.row < len(self._rows):
            return self._rows[self._focus.row].metrics.height
        return self._metrics.height

    def _content_height(self) -> float:
        return self._content_height_px

    def _on_scale_changed(self, scale: Scale) -> None:
        self._scale = scale
        self._apply_metrics()
        self._status_info.set_scale(scale)
        self._remote_hint.set_scale(scale)
        self._status_bar.set_scale(scale)
        self._detail_bar.set_scale(scale)
        self._launching_overlay.set_scale(scale)
        self._osd.set_scale(scale)
        self._system_menu.set_scale(scale)
        self._tile_menu.set_scale(scale)
        self._search.set_scale(scale)
        self._apps_grid.set_scale(scale)
        self._settings_screen.set_scale(scale)
        self._text_entry.set_scale(scale)
        self._phone_pairing.set_scale(scale)
        self._onboarding.set_scale(scale)
        self._launcher.browser_scale_factor = tokens.browser_scale_factor(
            scale.viewport_height_px
        )
        self._rebuild_row_widgets()

    def _on_viewport_resized(self, width: int, height: int) -> None:
        self._viewport_width = width
        self._viewport_height = height
        self._layout_rows()
        self._update_focus(animate=False)

    def _apply_layout_settings(self) -> None:
        self._apply_metrics()
        self._rebuild_row_widgets()

    def _repeat_timing(self) -> RepeaterTiming:
        interval = self._settings.get_int("key-repeat-interval-ms") / 1000.0
        # Acceleration keeps the design's 2:1 relationship (§6.2) rather
        # than a fixed 60ms floor: a user who slowed repeat down because it
        # was too fast must not get a fast phase quicker than their choice.
        return RepeaterTiming(
            initial_delay=self._settings.get_int("key-repeat-initial-ms") / 1000.0,
            interval=interval,
            fast_interval=interval / 2.0,
        )

    def _apply_repeat_settings(self) -> None:
        # Rebuilt rather than mutated: RepeaterTiming is frozen, and any
        # direction held across the change is released against the new
        # object harmlessly.
        self._repeater = Repeater(time.monotonic, self._repeat_timing())
        self._repeat_action = None

    def _apply_preferred_sink(self) -> None:
        """§6.8 Audio: the chosen output is stored by description, because
        wireplumber node ids are not stable across reboots. Missing hardware
        is not an error — an output that isn't plugged in today simply
        leaves the system default alone."""
        wanted = self._settings.get_string("audio-sink")
        if not wanted:
            return

        def choose(sinks: list[audio.Sink]) -> None:
            for sink in sinks:
                if sink.description == wanted and not sink.is_default:
                    audio.set_default_sink(sink.id)
                    return

        audio.list_sinks(choose)

    def _on_accent_changed(self) -> None:
        self._backdrop.queue_draw()
        for row in self._rows:
            for widget in row.tiles:
                widget.queue_draw()

    def _apply_animation_setting(self) -> None:
        # The speed goes first: `_animations_enabled` asks the motion module
        # whether the dial is at zero, so reading it before this line would
        # answer for the previous value.
        motion.set_animation_speed(self._settings.get_double("animation-scale"))
        enabled = self._animations_enabled
        self._row_anchor.set_animations_enabled(enabled)
        for row in self._rows:
            row.scroller.set_animations_enabled(enabled)
        self._return_fade.set_enabled(enabled)
        for surface in self._faded_surfaces:
            surface.set_fade_enabled(enabled)
        self._rebuild_row_widgets()

    # --- config / catalog -----------------------------------------------

    def _toast(self, message: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast(title=message))

    def _load_config(self) -> tile_config.Config:
        if not self._config_path.exists():
            tile_config.save(tile_config.Config(rows=_seed_rows()), self._config_path)
        try:
            return tile_config.load(self._config_path)
        except ConfigError as exc:
            self._toast(f"Your tiles file couldn't be read, so none are shown. {exc}")
            return tile_config.Config()

    def _save_config(self) -> None:
        """The tile editor's only write path.

        It writes the same file a hand edit writes and lets the existing
        directory monitor reload it, so there is exactly one way the
        catalogue ever comes back in — no second, editor-only reload path
        that could drift from the one everybody else uses.
        """
        try:
            tile_config.save(self._config, self._config_path)
        except OSError as exc:
            self._toast(f"That change couldn't be saved. {exc}")

    def _edit_text(
        self, title: str, initial: str, on_done: Callable[[str | None], None]
    ) -> None:
        self._text_entry.open(title=title, initial=initial, on_done=on_done)

    def _show_system_menu(self) -> None:
        self._rebuild_system_menu()
        self._system_menu.show()

    def _open_settings(self, panel_id: str = "") -> None:
        self._clear_for_settings()
        if panel_id:
            self._settings_screen.open_at(panel_id)
        else:
            self._settings_screen.open()

    def _clear_for_settings(self) -> None:
        self._system_menu.hide()
        if self._search.get_visible():
            self._search.close()
        if self._apps_grid.get_visible():
            self._apps_grid.close()
        # A mouse can click the top bar's buttons without the D-pad ever
        # having gone up there, and a click that leaves the bar highlighted
        # behind a full-screen overlay is a cursor in two places at once.
        self._set_nav_focused(False)

    def _settings_screen_open_tile(self, row_id: str, tile_id: str) -> None:
        self._clear_for_settings()
        self._settings_screen.open_tile(row_id, tile_id)

    def _locate_in_config(self, tile_id: str) -> tuple[str, str] | None:
        """Where a tile lives in tiles.json, if it lives there at all.

        A tile on screen is not necessarily an entry in the catalogue file:
        Recents, Favourites and the apps grid all produce tiles that no row
        in tiles.json contains, and offering to edit one of those would open
        an editor for a row that does not exist.
        """
        for row in self._config.rows:
            for tile in row.tiles:
                if tile.id == tile_id:
                    return row.id, tile.id
        return None

    def _refresh_catalog(self, *, preserve_focus: bool) -> None:
        """Ask the providers for a fresh catalogue (§6.10).

        Asynchronous, because `collect()` waits up to three seconds and one
        misbehaving provider must not freeze the interface every time a tile
        is launched. The tile to land on is captured *now*, before the
        rebuild, since by the time the answer arrives the focus model may
        have been reset by something else.
        """
        focused_tile = (
            self._catalog.tile_at(self._focus.row, self._focus.col) if preserve_focus else None
        )
        target_id = focused_tile.id if focused_tile is not None else None
        if target_id is None and not self._catalog.rows:
            # Nothing focused yet — this is the first build, so honour the
            # tile the last session left off on.
            target_id = self._settings.get_string("last-focused-tile") or None

        self._catalog_generation += 1
        generation = self._catalog_generation
        self._provider_registry.build_async(
            self._config,
            lambda build: self._on_catalog_built(build, generation, target_id),
        )

    def _on_catalog_built(
        self, build: CatalogBuild, generation: int, target_id: str | None
    ) -> None:
        # Edits can outrun a slow provider; an older build landing after a
        # newer one would silently undo it.
        if generation != self._catalog_generation:
            return

        self._provider_outcomes = build.outcomes
        # The registry isolated the providers from each other; what's left is
        # a clash *within* one provider's rows, which Catalog rejects.
        # Falling back to an empty catalogue there would blank the screen
        # over one duplicated tile id, so the ambiguous rows are dropped and
        # everything else is kept.
        rows, problems = sanitize(build.rows)
        for message in problems:
            self._toast(message)
        for failure in build.failures:
            self._toast(f"The {failure.provider_id} provider: {failure.reason}")

        # A row with no tiles is a heading with a void under it: there is
        # nothing to focus, nothing to launch, and (before this) landing on
        # one swallowed the focus entirely. They still exist in the config
        # and in the tile editor, which is where an empty row you just
        # created is supposed to be visible — the home screen just doesn't
        # draw them.
        rows = [row for row in rows if row.tiles]

        self._catalog = Catalog(rows)
        self._focus.set_row_lengths(self._catalog.row_lengths())
        if target_id is not None:
            pos = self._catalog.find(target_id)
            if pos is not None:
                self._focus.jump_to(*pos)
        self._rebuild_row_widgets()

    # --- row/tile widgets --------------------------------------------------

    def _rebuild_row_widgets(self) -> None:
        child = self._rows_content.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._rows_content.remove(child)
            child = next_child

        animations = self._animations_enabled
        self._rows = []
        remote_rows: list[RemoteRow] = []
        for row_index, row in enumerate(self._catalog.rows):
            metrics = metrics_for(
                self._scale, row.tile_aspect, size_scale=self._tile_scale
            )

            heading = Gtk.Label(label=row.title or "")
            heading.set_halign(Gtk.Align.START)
            heading.set_xalign(0.0)
            heading.set_yalign(0.5)
            heading.add_css_class("salon-row-heading")
            self._rows_content.put(heading, 0, 0)

            row_viewport = Gtk.Fixed()
            row_viewport.set_overflow(Gtk.Overflow.HIDDEN)
            row_viewport.set_accessible_role(Gtk.AccessibleRole.ROW)
            row_viewport.update_property(
                [Gtk.AccessibleProperty.LABEL], [row.title or "Untitled row"]
            )

            tiles_box = Gtk.Fixed()
            tiles: list[TileWidget] = []
            remote_tiles: list[RemoteTile] = []
            for col, tile in enumerate(row.tiles):
                artwork = self._artwork.resolve(tile, icon_size=round(metrics.height * 0.5))
                # The phone's copy of this tile, built from the artwork that
                # was just resolved rather than resolving it a second time.
                # A symbolic icon is monochrome and reads as a smudge on a
                # phone-sized card, so it counts as no artwork and the
                # accent card is drawn instead — the same judgement the
                # television makes at level 5.
                # Levels: 1 is a real image and fills the card; 3 and 4 are
                # icons drawn small on the accent, exactly as ui/tile.py
                # draws them. Built by the same helper the phone's search
                # results go through, so a result and a home-screen tile are
                # the same card rather than two that drift apart.
                remote_tiles.append(self._remote_tile_from(tile, artwork))
                widget = TileWidget(
                    tile, artwork, metrics, self._scale, animations_enabled=animations
                )
                self._attach_pointer(widget, row_index, col)
                # Tiles start at x=0, not at -bleed: a child placed at a
                # negative x inside the tiles box is clipped along that
                # edge, which cut the left half of the first tile's bloom
                # clean off. The row's scroll offset carries the bleed
                # instead — see _row_scroll_x.
                tiles_box.put(widget, col * metrics.step, 0.0)
                tiles.append(widget)
            row_viewport.put(tiles_box, 0, 0)
            self._rows_content.put(row_viewport, 0, 0)

            widgets = _RowWidgets(heading, row_viewport, tiles_box, tiles, metrics)
            widgets.scroller.set_animations_enabled(animations)
            self._rows.append(widgets)
            remote_rows.append(
                RemoteRow(
                    id=row.id,
                    title=row.title,
                    tiles=tuple(remote_tiles),
                    aspect=row.tile_aspect,
                )
            )

        self._remote_rows = tuple(remote_rows)
        self._row_anchor.set_animations_enabled(animations)
        self._layout_rows()
        # _update_focus publishes, so the phone picks the new catalogue up
        # on its next poll without a second hook here.
        self._update_focus(animate=False)

    def _layout_rows(self) -> None:
        """Position every row at an absolute y, and size the row viewports
        to the full window width so the only horizontal clip is the screen
        edge itself."""
        width = self._viewport_width
        heading_width = max(1, round(width - 2 * self._safe_margin))
        self._recompute_row_tops()
        for index, row in enumerate(self._rows):
            top = self._row_top(index)
            row.heading.set_size_request(heading_width, round(self._heading_height))
            self._rows_content.move(row.heading, self._safe_margin, top)

            row.viewport.set_size_request(width, round(row.metrics.outer_height))
            self._rows_content.move(
                row.viewport, 0.0, self._row_tile_top(index) - row.metrics.bleed
            )
        self._rows_content.set_size_request(width, max(1, round(self._content_height())))
        self._apply_viewport_insets()
        self._update_edge_fades()

    def _update_edge_fades(self) -> None:
        """Fade each band edge by as much as is actually hanging over it.

        A constant fade at both ends is wrong at rest. The band's top is
        exactly where the first row's heading sits when nothing is scrolled,
        so a permanent 40du ramp there dimmed "Favourites" — and only
        "Favourites" — for the whole life of the screen, with no row passing
        under it to justify the softening. The fade exists so a row *leaving*
        the band isn't sliced by a hard clip edge; when nothing is leaving,
        there is nothing to soften.

        So each end fades by min(overflow, 40du): zero when the content ends
        inside the band, ramping in over the first few pixels of travel and
        capping at the full ramp once a row is genuinely passing under a bar.
        """
        fade = self._scale.du(_EDGE_FADE_DU)
        band_height = float(self._viewport_height or _FALLBACK_VIEWPORT_HEIGHT_PX)
        offset = self._row_anchor.value
        above = max(0.0, -offset)
        below = max(0.0, self._content_height() + offset - band_height)
        self._viewport.set_fades(min(fade, above), min(fade, below))

    def _apply_viewport_insets(self) -> None:
        """Shrink the scrolling band to the gap between the two bars.

        The top bar and the detail strip are the two places on this screen
        that *report* — the time, the network, what the cursor is on and
        what OK will do with it — and a row of artwork sliding underneath
        text is unreadable in both directions. This used to be a fade: the
        band covered the whole window and its top and bottom were masked out
        over exactly the bands the bars occupy. That kept them legible and
        still put half-transparent tiles behind them.

        Margins on the viewport host instead, so the clip really happens at
        the bars' edges and no tile pixel is ever drawn in either strip.
        `Gtk.Overflow.HIDDEN` on the viewport does the rest.

        Set here rather than in `_apply_metrics` because the bottom inset is
        *measured* off the detail strip, which changes height with its own
        contents. Assigning an unchanged margin is a no-op in GTK, so the
        steady state costs nothing and this cannot drive a resize loop even
        though `_layout_rows` runs from inside an allocation.
        """
        self._viewport_host.set_margin_top(round(self._top_inset()))
        self._viewport_host.set_margin_bottom(round(self._bottom_inset()))

    def _attach_pointer(self, widget: TileWidget, row: int, col: int) -> None:
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self._on_tile_clicked(row, col))
        widget.add_controller(click)

        hover = Gtk.EventControllerMotion()
        # `motion`, not `enter`: focus should follow a pointer the user is
        # actually moving, not jump because a row scrolled a different tile
        # under a stationary cursor.
        hover.connect("motion", lambda *_: self._on_tile_hovered(row, col))
        widget.add_controller(hover)

    def _on_tile_clicked(self, row: int, col: int) -> None:
        if self._system_menu.get_visible() or self._launcher.is_launching:
            return
        if (row, col) != self._focus.position:
            self._focus.jump_to(row, col)
            self._update_focus()
        self._launch_focused()

    def _on_tile_hovered(self, row: int, col: int) -> None:
        if not self._pointer_visible:
            return  # a tile scrolled under a parked cursor, not a real hover
        if self._system_menu.get_visible() or self._launcher.is_launching:
            return
        if (row, col) == self._focus.position:
            return
        self._focus.jump_to(row, col)
        self._update_focus()

    # --- focus / scrolling -------------------------------------------------

    def _update_focus(self, *, animate: bool = True) -> None:
        for r, row in enumerate(self._rows):
            focused_row = r == self._focus.row
            for c, widget in enumerate(row.tiles):
                # Nothing in the rows carries the ring while the top bar
                # holds the cursor: two full-strength highlights on screen
                # leaves no answer to "what does OK do right now".
                widget.set_focused(
                    not self._nav_focused and focused_row and c == self._focus.col
                )
            if focused_row:
                row.heading.add_css_class("row-focused")
            else:
                row.heading.remove_css_class("row-focused")

        tile = self._catalog.tile_at(self._focus.row, self._focus.col)
        self._detail_bar.set_tile(tile)
        if tile is not None:
            self._settings.set_string("last-focused-tile", tile.id)
            focused_widget = self._focused_widget()
            if focused_widget is not None:
                self._backdrop.set_focus(
                    focused_widget.artwork_accent, focused_widget.artwork_source
                )
                self._publish_active_descendant(focused_widget)
        self._update_backdrop_position()
        # Every row, not only the focused one: rows scroll independently and
        # each has its own remembered column (§6.2), so a row left at column
        # 4 must still be showing column 4 when the user comes back to it.
        # Only the focused row animates — the others are off-screen or about
        # to be, and animating them is motion nobody asked for.
        for index in range(len(self._rows)):
            self._update_row_scroll(
                index,
                self._focus.column_for(index),
                animate=animate and index == self._focus.row,
            )
        self._update_row_anchor(animate=animate)
        self._publish_remote_state()

    def _publish_remote_state(self) -> None:
        """Offer the phone a fresh snapshot of the television.

        Called from every place the phone's view could have changed — the
        cursor moving, the catalogue rebuilding, a player appearing, a
        screen opening. That is a lot of call sites, and it is affordable
        because `StateFeed` compares the snapshot to the last one and does
        nothing if they match: no JSON is produced until a phone actually
        polls for a version it has not seen.

        Skipped outright when the server is down, which is most of the time.
        """
        if not self._pairing.running:
            return
        player = self._current_player
        playing: RemoteNowPlaying | None = None
        if player is not None:
            title, detail = nowplaying.describe(player)
            playing = RemoteNowPlaying(
                title=title,
                detail=detail,
                playing=player.status == nowplaying.PLAYING,
                can_next=player.can_go_next,
                can_previous=player.can_go_previous,
            )
        timing = self._repeat_timing()
        self._pairing.publish(
            RemoteState(
                rows=self._remote_rows,
                now_playing=playing,
                focus=(self._focus.row, self._focus.col),
                screen=self._current_screen(),
                # The phone opens its keyboard by itself when the television
                # puts a field on screen, rather than making someone find
                # the tab for it while an empty box blinks at them.
                wants_text=self._text_entry.get_visible() or self._search.get_visible(),
                remote_input=self._pointer.ready,
                repeat_delay_ms=round(timing.initial_delay * 1000),
                repeat_interval_ms=round(timing.interval * 1000),
                accent=self._settings.get_string("accent-color") or "#E8A33D",
                # Named separately from `screen`, which carries the same
                # string but as one of six reserved words. The page hides
                # half its own controls on this, so it cannot be guessing.
                app=self._app_in_front(),
                volume=self._phone_volume,
                muted=self._phone_muted,
            )
        )

    def _app_in_front(self) -> str:
        """The title of the application covering the television, or "".

        Same test `_current_screen` makes, named on its own because the
        phone reshapes itself around the answer: with an app up, the D-pad
        and Search do nothing at all, and only the trackpad, the volume and
        Menu still mean something.
        """
        if self._child_active or self._pointer_mode or self._launcher.has_child:
            return self._launcher.child_title or "an app"
        return ""

    def _current_screen(self) -> str:
        """Which screen is in front, for the phone's title bar.

        Ordered the way `_handle_action` is: the thing that would take the
        next press is the thing the phone should be naming.
        """
        if self._system_menu.get_visible() or self._tile_menu.get_visible():
            return "menu"
        if self._text_entry.get_visible():
            return "keyboard"
        if self._settings_screen.get_visible():
            return "settings"
        if self._search.get_visible():
            return "search"
        if self._apps_grid.get_visible():
            return "apps"
        if self._launcher.is_launching:
            return f"Opening {self._launcher.child_title or 'an app'}…"
        # pointer_mode as well as child_active: a *browser* tile puts Salon
        # behind Chrome without ever setting child_active, so testing only
        # the latter told the phone it was on the home screen while Netflix
        # was on the television.
        if self._child_active or self._pointer_mode:
            return self._launcher.child_title or "app"
        return "home"

    def _publish_active_descendant(self, widget: Gtk.Widget) -> None:
        """aria-activedescendant, the standard answer for a composite widget
        that keeps the keyboard focus and moves a cursor inside itself. The
        top bar takes it while the cursor is up there, so what is announced
        and what is drawn with the ring are never two different things."""
        target = self._status_bar if self._nav_focused else widget
        self.update_relation([Gtk.AccessibleRelation.ACTIVE_DESCENDANT], [target])

    def _focused_widget(self) -> TileWidget | None:
        if not (0 <= self._focus.row < len(self._rows)):
            return None
        tiles = self._rows[self._focus.row].tiles
        if not (0 <= self._focus.col < len(tiles)):
            return None
        return tiles[self._focus.col]

    def _update_backdrop_position(self) -> None:
        """Put the ambient pool of light roughly behind the focused tile."""
        if not self._rows or self._viewport_width <= 0 or self._viewport_height <= 0:
            return
        metrics = self._rows[min(self._focus.row, len(self._rows) - 1)].metrics
        x = (self._safe_margin + metrics.width / 2.0) / self._viewport_width
        y = tokens.ROW_ANCHOR_FRACTION
        self._backdrop.set_focus_position(x, y)

    def _row_scroll_x(self, row: _RowWidgets, col: int) -> float:
        """Left-anchor the focused tile's *card* at the safe-area margin, but
        never scroll past the end of the row — stranding empty space at the
        right edge looks broken, and the last screenful of a row reads better
        flush-right than left-anchored with a void beside it.

        Offsets are in tiles-box coordinates, where a tile's card sits one
        bleed to the right of the tile widget's own origin.
        """
        bleed = row.metrics.bleed
        max_offset = self._safe_margin - bleed
        desired = max_offset - col * row.metrics.step
        min_offset = min(
            max_offset,
            self._viewport_width - self._safe_margin - bleed - row.content_width,
        )
        return max(min_offset, min(max_offset, desired))

    def _update_row_scroll(self, row_index: int, col: int, *, animate: bool) -> None:
        if not (0 <= row_index < len(self._rows)):
            return
        row = self._rows[row_index]
        target = self._row_scroll_x(row, col)
        row.scroller.animate_to(target) if animate else row.scroller.jump_to(target)

    def _top_inset(self) -> float:
        """How much of the top of the screen the rows may not use.

        Measured off the two status widgets rather than taken from
        STATUS_BAR_HEIGHT_DU, for the same reason `_bottom_inset` is
        measured: both carry their own safe-area top margin and both scale
        with the du pipeline, and the token is a design figure rather than
        what the widgets actually ask for. The larger of the two, because
        they are side by side — the buttons are taller than the clock.
        """
        natural = max(
            self._status_info.get_preferred_size()[1].height,
            self._status_bar.get_preferred_size()[1].height,
        )
        if natural > 0:
            return float(natural)
        return self._safe_margin + self._status_height

    def _bottom_inset(self) -> float:
        """How much of the bottom of the screen the rows may not use.

        Measured off the detail strip rather than taken from a constant:
        the strip is two lines of type plus its own bottom margin, all of
        which move with the du scale and with the safe-area preference, and
        a guessed constant was 104px against a real 165 — sixty pixels of
        rows scrolling underneath text.
        """
        natural = self._detail_bar.get_preferred_size()[1].height
        if natural > 0:
            return float(natural)
        return self._safe_margin + self._detail_height

    def _row_anchor_y(self) -> float:
        """The focused row holds a fixed vertical anchor (§6.1), clamped at
        both ends of the content.

        In **band** coordinates: the scrolling viewport no longer spans the
        window, it spans the gap between the top bar and the detail strip
        (`_apply_viewport_insets`), so 0 here is the top of that gap and not
        the top of the screen. The anchor line itself is still measured on
        the *window*, because 38% of a television is a design figure about
        where a human looks and not about where this widget happens to
        start — hence the `- top_inset` converting it back.

        The top clamp keeps a catalogue shorter than the band sitting at the
        top of it rather than floating in the middle of dead space. The
        bottom clamp stops the stack scrolling past its own end.

        That bottom clamp was removed once, because it left barely 90px of
        travel on a four-row 1080p screen and parked the last row under the
        fold with its tiles half off. The diagnosis was right and the cure
        was wrong: the fault was a limit that ignored the insets, not the
        existence of a limit. Computed properly the last row lands fully
        visible with the detail strip beneath it, and the case the removal
        caused goes away too: with three rows and the cursor on the last of
        them, an unclamped anchor scrolled 409px into empty space and left
        sixty per cent of a television blank.
        """
        band_height = self._viewport_height or _FALLBACK_VIEWPORT_HEIGHT_PX
        top_inset = self._top_inset()
        window_height = band_height + top_inset + self._bottom_inset()
        content_height = self._content_height()

        if content_height <= band_height:
            return 0.0

        focused_center = self._row_tile_top(self._focus.row) + self._focused_tile_height() / 2.0
        anchor_line = window_height * tokens.ROW_ANCHOR_FRACTION - top_inset
        desired = anchor_line - focused_center
        lowest = band_height - content_height
        return min(0.0, max(lowest, desired))

    def _update_row_anchor(self, *, animate: bool) -> None:
        target = self._row_anchor_y()
        self._row_anchor.animate_to(target) if animate else self._row_anchor.jump_to(target)

    def _rubber_band(self, bump: Bump) -> None:
        distance = self._bump_distance
        if bump is Bump.LEFT or bump is Bump.RIGHT:
            if not (0 <= self._focus.row < len(self._rows)):
                return
            scroller = self._rows[self._focus.row].scroller
            scroller.bump(distance if bump is Bump.LEFT else -distance)
        elif bump is Bump.UP:
            self._row_anchor.bump(distance)
        elif bump is Bump.DOWN:
            self._row_anchor.bump(-distance)

    # --- filesystem watches ----------------------------------------------

    def _on_config_dir_changed(
        self,
        monitor: Gio.FileMonitor,
        file: Gio.File,
        other_file: Gio.File | None,
        event_type: Gio.FileMonitorEvent,
    ) -> None:
        if file.get_basename() != self._config_path.name:
            return
        if self._reload_timeout_id is not None:
            GLib.source_remove(self._reload_timeout_id)
        self._reload_timeout_id = GLib.timeout_add(_RELOAD_DEBOUNCE_MS, self._reload_from_disk)

    def _reload_from_disk(self) -> bool:
        self._reload_timeout_id = None
        try:
            self._config = tile_config.load(self._config_path)
        except ConfigError as exc:
            self._toast(f"Your tiles file couldn't be reloaded, so nothing changed. {exc}")
            return GLib.SOURCE_REMOVE
        # Our own save comes back through here too, as a new Config object;
        # the editor has to be repointed at it or the next edit is applied
        # to a detached copy of the catalogue.
        self._settings_screen.set_config(self._config)
        self._refresh_catalog(preserve_focus=True)
        return GLib.SOURCE_REMOVE

    def _on_artwork_dir_changed(
        self,
        monitor: Gio.FileMonitor,
        file: Gio.File,
        other_file: Gio.File | None,
        event_type: Gio.FileMonitorEvent,
    ) -> None:
        if self._artwork_reload_timeout_id is not None:
            GLib.source_remove(self._artwork_reload_timeout_id)
        self._artwork_reload_timeout_id = GLib.timeout_add(
            _RELOAD_DEBOUNCE_MS, self._on_artwork_reload_timeout
        )

    def _on_artwork_reload_timeout(self) -> bool:
        self._artwork_reload_timeout_id = None
        self._rebuild_row_widgets()
        return GLib.SOURCE_REMOVE

    # --- input -------------------------------------------------------------

    def _set_pointer_visible(self, visible: bool) -> None:
        """A mouse cursor parked over a TV interface looks like a stuck
        pixel, so it's hidden the moment the user drives with anything else
        and restored as soon as the pointer moves again."""
        if visible == self._pointer_visible:
            return
        self._pointer_visible = visible
        self._apply_pointer_state()

    def _apply_pointer_state(self) -> None:
        visible = self._pointer_visible
        # Hover-to-select follows the same flag: GTK delivers a motion event
        # whenever a widget maps or scrolls under a stationary cursor, so
        # acting on hover regardless of whether the pointer is actually in
        # use makes focus jump to wherever the mouse was left sitting.
        self._system_menu.set_hover_enabled(visible)
        self._phone_pairing.set_hover_enabled(visible)
        self._tile_menu.set_hover_enabled(visible)
        self._status_bar.set_hover_enabled(visible)
        self._search.set_pointer_active(visible)
        self._apps_grid.set_pointer_active(visible)
        self._settings_screen.set_pointer_active(visible)
        self._text_entry.set_pointer_active(visible)
        root = self.get_root()
        if isinstance(root, Gtk.Window):
            root.set_cursor(None if visible else Gdk.Cursor.new_from_name("none", None))

    def on_mapped(self) -> None:
        """Called once the window has a surface — the first moment there's a
        root to hang a cursor on."""
        self.grab_focus()
        self._apply_pointer_state()
        if not self._settings.get_boolean("onboarding-complete"):
            self._onboarding.start()
        self._prewarm_pointer_session()

    def _finish_onboarding(self) -> None:
        self._settings.set_boolean("onboarding-complete", True)
        self.grab_focus()

    def _prewarm_pointer_session(self) -> None:
        """Take the RemoteDesktop grant now rather than mid-launch.

        The portal's consent dialog appears once — after that the restore
        token reopens the session silently — but *where* that once lands
        matters. Asking here puts it over Salon's own home screen, anchored
        to Salon's window, while nothing is launching; asking at child-focus
        time put it on top of Netflix the moment it opened, which is what it
        used to do.

        Nothing is launching yet, so the dialog stealing focus can't be
        mistaken for the child taking it (LauncherService ignores
        active-state changes while idle). Skipped entirely when there is no
        browser tile to point at, so a catalogue of native apps never sees a
        permission prompt at all.
        """
        if not self._settings.get_boolean("gamepad-pointer"):
            return
        if not any(
            _is_browser_launch(tile) for row in self._catalog.rows for tile in row.tiles
        ):
            return
        self._start_pointer_session()

    def _on_pointer_motion(
        self, controller: Gtk.EventControllerMotion, x: float, y: float
    ) -> None:
        """Only *movement* counts as the pointer being in use.

        GTK delivers a motion event when a window maps under a stationary
        cursor, and taking that at face value meant Salon started up with
        the cursor revealed and hover-to-focus armed — so the first widget
        rebuild under the parked mouse silently stole focus. Comparing
        against the last position is what tells a real move from that.
        """
        previous = self._last_pointer_xy
        self._last_pointer_xy = (x, y)
        if previous is None:
            return
        if abs(x - previous[0]) < 1.0 and abs(y - previous[1]) < 1.0:
            return
        self.wake()
        self._set_pointer_visible(True)

    def _on_scroll(self, controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
        self.wake()
        if self._system_menu.get_visible():
            self._handle_action(Action.DOWN if dy > 0 else Action.UP)
            return True
        if dy:
            self._handle_action(Action.DOWN if dy > 0 else Action.UP)
        if dx:
            self._handle_action(Action.RIGHT if dx > 0 else Action.LEFT)
        return True

    def _on_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: object,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            # Dev-only quit shortcut, deliberately outside the Action
            # pipeline — a real TV launcher shouldn't be closeable by a
            # single button, and this must never be reachable from the
            # gamepad (B already means BACK, not quit).
            root = self.get_root()
            if isinstance(root, Gtk.Window):
                root.close()
            return True
        if self._binding_capture is not None:
            self._on_raw_input(KEYBOARD, keyval)
            return True
        action = action_for_keyval(keyval, self._bindings)
        if action is None:
            return False
        self._set_pointer_visible(False)
        if action in _DIRECTIONS:
            if keyval in self._held_keyvals:
                return True  # OS auto-repeat re-fire — our own Repeater drives repeats
            self._held_keyvals.add(keyval)
            self._start_repeat(action)
        self._handle_action(action)
        return True

    def _on_key_released(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: object,
    ) -> None:
        self._held_keyvals.discard(keyval)
        action = action_for_keyval(keyval, self._bindings)
        if action is not None:
            self._stop_repeat(action)

    def _apply_cec_setting(self) -> None:
        """Start or stop the CEC source, and wake the television when it's
        turned on. Starting `cec-client` claims the adapter, so this only
        ever runs when the user asked for it."""
        if self._settings.get_boolean("cec-enabled"):
            if not self._cec.running and self._cec.start():
                cec_out.wake_display()
        else:
            self._cec.stop()

    def _on_cec_action(self, action: Action) -> None:
        if self._binding_capture is not None:
            return
        # A TV remote produces discrete presses with no key-up, so it feeds
        # _handle_action directly rather than the Repeater — the television
        # is already doing its own auto-repeat.
        self._set_pointer_visible(False)
        self._handle_action(action)

    # --- rebinding -------------------------------------------------------

    def _reload_bindings(self) -> None:
        self._bindings = Bindings(self._settings.get_value("input-bindings").unpack())
        self._gamepad.set_bindings(self._bindings)
        self._cec.set_bindings(self._bindings)

    def _save_bindings(self) -> None:
        self._settings.set_value(
            "input-bindings", GLib.Variant("a{ss}", self._bindings.to_storage())
        )

    def begin_binding_capture(self, on_captured: Callable[[str, int], None]) -> None:
        """Wait for the next physical button, from any source, and hand its
        code back.

        Every source is armed at once on purpose: someone rebinding OK does
        not want to be asked first whether they are holding a controller or
        pointing a remote. Whatever they press is the answer, including a
        button that currently does nothing — which is exactly the case
        rebinding exists for.
        """
        self._binding_capture = on_captured

    def cancel_binding_capture(self) -> None:
        self._binding_capture = None

    def _on_raw_input(self, source: str, code: int) -> None:
        capture = self._binding_capture
        if capture is None:
            return
        self._binding_capture = None
        capture(source, code)

    def bindings(self) -> Bindings:
        return self._bindings

    def rebind(self, source: str, code: int, action: str) -> None:
        self._bindings.bind(source, code, action)
        self._save_bindings()

    def reset_bindings(self) -> None:
        self._bindings.clear_all()
        self._save_bindings()

    def _apply_wallpaper(self) -> None:
        self._backdrop.set_wallpaper(
            self._settings.get_string("wallpaper-path"),
            self._settings.get_double("wallpaper-dim"),
        )

    # --- the idle screen -------------------------------------------------

    def _apply_screensaver_setting(self) -> None:
        if self._idle_id is not None:
            GLib.source_remove(self._idle_id)
            self._idle_id = None
        self._screensaver.hide()
        if self._settings.get_int("screensaver-minutes") <= 0:
            return
        # Polled once a second rather than armed for the whole delay: the
        # deadline moves on every button press, and rearming a timer on
        # every press of a held direction is far more work than one cheap
        # comparison a second.
        self._idle_id = GLib.timeout_add_seconds(1, self._check_idle)

    def _check_idle(self) -> bool:
        minutes = self._settings.get_int("screensaver-minutes")
        if minutes <= 0:
            self._idle_id = None
            return bool(GLib.SOURCE_REMOVE)
        if self._screensaver.showing:
            return bool(GLib.SOURCE_CONTINUE)
        # Never over something Salon started. While a child app owns the
        # screen Salon is not being looked at, and the child has its own
        # idea about idling; while a launch is in flight, covering the
        # overlay would hide the only feedback there is.
        if self._child_active or self._pointer_mode or self._launcher.is_launching:
            self._last_input = time.monotonic()
            return bool(GLib.SOURCE_CONTINUE)
        if time.monotonic() - self._last_input >= minutes * 60:
            # The one moment nobody is looking at the home screen, which is
            # exactly when a slideshow should change picture: doing it on a
            # timer would swap the background out from under someone
            # mid-navigation.
            self._backdrop.next_wallpaper()
            self._screensaver.show()
        return bool(GLib.SOURCE_CONTINUE)

    def wake(self) -> None:
        """Any input at all, including the kinds that never become an
        Action — a mouse moving, a click on the status bar."""
        self._last_input = time.monotonic()
        if self._screensaver.showing:
            self._screensaver.hide()

    # --- what is playing -------------------------------------------------

    def _on_now_playing(self, player: nowplaying.Player | None) -> None:
        """Hand the detail strip over to the player, or give it back.

        The strip shows one thing at a time on purpose: a television has
        exactly one place the eye looks for "what is happening right now",
        and splitting it between the cursor and the music would make both
        harder to read from a sofa.
        """
        self._current_player = player
        self._publish_remote_state()
        if player is None:
            self._detail_bar.clear_override()
            return
        title, detail = nowplaying.describe(player)
        self._detail_bar.set_override(title, detail)

    # --- the phone -------------------------------------------------------

    def _on_phone_action(self, name: str) -> None:
        """A button on the phone remote. Goes through `_handle_action` like
        every other source, so the phone can do exactly what a controller
        can and nothing more — including MENU, which is the one button that
        has to work when a launched app is covering the screen."""
        try:
            action = Action(name)
        except ValueError:
            return
        # A D-pad press is the phone saying "I am driving now", exactly like
        # a key or a controller button, so the cursor goes away — a mouse
        # left parked over a tile otherwise keeps hover-to-focus armed and
        # yanks the selection back the moment a row scrolls under it. The
        # trackpad brings it straight back. Pointer mode is the exception,
        # same as the gamepad: there the cursor *is* the interface.
        self._set_pointer_visible(self._pointer_mode)
        self._handle_action(action)

    def _on_phone_pointer(self, dx: float, dy: float) -> None:
        """The trackpad. Straight into the same RemoteDesktop session the
        right stick drives, which is what makes a phone useful over a
        browser tile that was never built for a remote.

        The cursor has to be *revealed*, and that is not incidental. Salon
        hides it until a real mouse moves, and the reveal hangs off GTK
        motion events — which portal-injected motion does not reliably
        produce over Salon's own window. So the pointer moved and nothing
        was drawn: a finger dragging something invisible. The gamepad path
        has always said this explicitly; this one never did.
        """
        if not self._pointer.ready:
            return
        self._set_pointer_visible(True)
        self.wake()
        self._pointer.move(dx, dy)

    def _on_phone_click(self) -> None:
        if self._pointer.ready:
            self._set_pointer_visible(True)
            self.wake()
            self._pointer.click()

    def _type_remotely(self, text: str) -> bool:
        """Text from the phone with no Salon field asking for it.

        Goes to whatever the compositor has focused — in practice a search
        box inside a launched browser, which is the one place typing on a
        television is unavoidable and the one place Salon's own keyboard
        cannot reach. Returns False when there is no input grant, so the
        phone is told why rather than watching its keystrokes vanish.
        """
        if not self._pointer.ready:
            return False
        self.wake()
        return self._pointer.type_text(text)

    def _open_phone_pairing(self) -> None:
        self._system_menu.hide()
        if not self._phone_pairing.open():
            self._toast("Couldn't start the phone remote — port 8437 is already in use.")
            return
        self._phone_pairing.set_hover_enabled(self._pointer_visible)
        self._publish_remote_state()

    def _close_phone_pairing(self) -> None:
        # The remote keeps running: connecting a phone and then dismissing
        # the screen is the whole gesture this exists for.
        self.grab_focus()
        self._rebuild_system_menu()

    def _stop_phone_remote(self) -> None:
        self.set_phone_remote(False)
        self.grab_focus()
        self._rebuild_system_menu()
        self._toast("Phone remote off.")

    def _rebuild_system_menu(self) -> None:
        """The first item's label depends on whether the remote is running,
        so the menu is rebuilt rather than built once at startup."""
        self._system_menu.set_items(self._build_system_menu_items())

    def _on_phone_launch(self, tile_id: str) -> None:
        """A tile tapped on the phone. Goes through `_launch_tile`, so it is
        the same launch — recents, the launching overlay, the idle inhibit
        and the way back out — as pressing OK on the television. The server
        has already checked the id against what the phone was shown; this
        checks it against the catalogue, because a rebuild can have landed
        in between."""
        position = self._catalog.find(tile_id)
        if position is None:
            self._toast("That isn't on the television any more.")
            return
        tile = self._catalog.tile_at(*position)
        if tile is None:
            return
        # The cursor follows the phone. Coming back to the television and
        # finding it parked where the last button press left it, rather than
        # on what was actually opened, is the kind of small dishonesty that
        # makes two input methods feel like two applications — and the mouse
        # gets out of the way for the same reason a button press does.
        self._set_pointer_visible(self._pointer_mode)
        self._focus.jump_to(*position)
        self._update_focus()
        self._launch_tile(tile)

    def _search_for_phone(self, query: str) -> list[RemoteTile]:
        """Rank the catalogue and every installed app for the phone.

        Answers on the main loop, inside the HTTP handler, so it must not
        touch the disk — the installed-app list is the one scanned when the
        remote started. Empty query returns the catalogue, exactly as the
        television's search screen does: someone who opened search wants to
        go somewhere, and a blank page makes them type before it will admit
        anything exists.

        `ranking.rank_best` is the same call the television makes, which is
        the point: two search surfaces that ordered results differently
        would be two things to learn.
        """
        catalogue = self._searchable_tiles()
        text = query.strip()
        if not text:
            chosen = catalogue[:_PHONE_SEARCH_RESULTS]
        else:
            by_id = {tile.id: tile for tile in (*catalogue, *self._phone_apps)}
            pairs = appinfo.search_pairs(catalogue) + appinfo.search_pairs(self._phone_apps)
            chosen = [
                by_id[tile_id]
                for tile_id in ranking.rank_best(text, pairs, _PHONE_SEARCH_RESULTS)
            ]
        return [self._remote_tile(tile) for tile in chosen]

    def _remote_tile(self, tile: Tile) -> RemoteTile:
        """One tile in the shape the phone draws, artwork and all.

        Shared with the catalogue snapshot's own construction so a search
        result and a home-screen tile are the same card with the same
        image — a result that rendered as a bare coloured rectangle would
        read as a different, lesser kind of thing.
        """
        return self._remote_tile_from(
            tile, self._artwork.resolve(tile, icon_size=_PHONE_ICON_SIZE_PX)
        )

    def _remote_tile_from(self, tile: Tile, artwork: Artwork) -> RemoteTile:
        return RemoteTile(
            id=tile.id,
            title=tile.title,
            subtitle=tile.subtitle,
            accent=to_hex(artwork.accent),
            has_art=artwork.level <= 4 and not artwork.icon_is_symbolic,
            fit="cover" if artwork.level == 1 else "contain",
            pinned=favourites.is_favourite(self._settings, tile.id),
            removable=self._locate_in_config(tile.id) is not None,
        )

    def _scan_apps_for_phone(self) -> None:
        """The installed-app list the phone's search ranks against.

        Once, when the remote first starts, and never on the request path.
        Scanning every `.desktop` file on the system takes long enough that
        doing it inside `/search` would stall the frame clock on every
        keystroke somebody types on their phone.
        """
        if self._phone_apps_scanned:
            return
        self._phone_apps_scanned = True

        def scanned(tiles: list[Tile]) -> None:
            self._phone_apps = tiles

        appinfo.list_installed_async(scanned)

    def _phone_tile(self, tile_id: str) -> Tile | None:
        """The catalogue tile behind an id from the phone, or the installed
        app if it is one of those — a search result can be either."""
        position = self._catalog.find(tile_id)
        if position is not None:
            return self._catalog.tile_at(*position)
        return next((tile for tile in self._phone_apps if tile.id == tile_id), None)

    def _on_phone_tile_action(self, tile_id: str, what: str) -> str:
        """The phone's long-press menu. Returns what to tell the phone.

        Every one of these already exists behind `Action.OPTIONS` on the
        television; this is the same set reached from the one surface that
        shows every tile at once. `edit` opens the television's own editor
        rather than reimplementing a form with eight fields on a phone —
        and says so, because a screen changing over there with no
        acknowledgement in your hand is indistinguishable from a dead
        button.
        """
        tile = self._phone_tile(tile_id)
        if tile is None:
            return "That isn't on the television any more."
        if what in ("pin", "unpin"):
            pinned = favourites.is_favourite(self._settings, tile_id)
            if (what == "pin") == pinned:
                return f"{tile.title} is already {'pinned' if pinned else 'unpinned'}."
            favourites.toggle_favourite(self._settings, tile_id)
            self._refresh_catalog(preserve_focus=True)
            return f"{tile.title} {'pinned to' if what == 'pin' else 'removed from'} Favourites"
        located = self._locate_in_config(tile_id)
        if located is None:
            # Recents, Favourites and the apps grid all produce tiles that
            # no row in tiles.json contains; there is nothing to edit or
            # delete, and saying so beats a button that quietly fails.
            return f"{tile.title} isn't one of your own tiles, so it can't be changed."
        row_id, located_id = located
        if what == "edit":
            self._settings_screen_open_tile(row_id, located_id)
            return f"Editing {tile.title} on the television."
        if editing.remove_tile(self._config, row_id, located_id):
            self._save_config()
            return f"{tile.title} removed."
        return f"{tile.title} couldn't be removed."

    def _on_phone_volume(self, level: float) -> None:
        """The slider. Absolute, and the OSD comes up on the television too
        — someone else in the room should see why it got quieter."""
        self.wake()
        audio.set_volume(level, lambda: audio.get_volume(self._on_volume_read))

    def _on_phone_mute(self) -> None:
        self.wake()
        audio.toggle_mute(lambda: audio.get_volume(self._on_volume_read))

    def _on_volume_read(self, level: float, muted: bool) -> None:
        self._osd.show_volume(level, muted)
        self._phone_volume = level
        self._phone_muted = muted
        self._publish_remote_state()

    def _refresh_phone_volume(self) -> None:
        """Read the sink so the phone's slider starts in the right place."""
        audio.get_volume(self._on_volume_read)

    def _on_phone_scroll(self, dx: float, dy: float) -> None:
        """Two fingers on the trackpad. Straight through to the same
        RemoteDesktop session the one-finger drag uses."""
        if not self._pointer.ready:
            return
        self._set_pointer_visible(True)
        self.wake()
        self._pointer.scroll(dx, dy)

    def _on_phone_scroll_end(self) -> None:
        if self._pointer.ready:
            self._pointer.scroll_finish()

    def _on_phone_button(self, button: str, what: str) -> None:
        """A named mouse button, clicked or held.

        Held is what a double-tap-and-drag needs: a click that releases
        itself 50ms later cannot move a window or select a line of text,
        and those are the two things a trackpad is for that a D-pad is not.
        """
        if not self._pointer.ready:
            return
        code = pointer_injector.BUTTONS.get(button)
        if code is None:
            return
        self._set_pointer_visible(True)
        self.wake()
        if what == "click":
            self._pointer.click(code)
        elif what == "down":
            self._pointer.press(code)
        else:
            self._pointer.release(code)

    def _on_phone_transport(self, what: str) -> bool:
        """Play/pause, next track, previous track, for the player the phone
        can see. Not routed through `Action`: see the comment on the page's
        transport buttons."""
        if what == "play_pause":
            done = self._now_playing.play_pause()
        elif what == "next":
            done = self._now_playing.next_track()
        else:
            done = self._now_playing.previous_track()
        if not done:
            self._toast("Nothing is playing.")
        return done

    def _art_for_phone(self, tile_id: str) -> Path | None:
        """The image file behind a tile the phone is drawing.

        Through `_phone_tile`, so it covers a search result as well as
        something on the home screen. Looking only in the catalogue — which
        is what this did — meant every installed application in a result
        list reported artwork it could not then serve, and the card fell
        back to a coloured letter after a 404 per tile.
        """
        tile = self._phone_tile(tile_id)
        return None if tile is None else self._artwork.artwork_file(tile)

    def _on_phone_locked(self) -> None:
        self._toast(
            "Phone remote locked — too many wrong codes. "
            "Turn it off and on again in Settings for a new code."
        )

    def phone_remote_running(self) -> bool:
        return self._pairing.holds(_REMOTE_HOLDER)

    def phone_remote_hint(self) -> str:
        if not self.phone_remote_running():
            # The server can still be up: the corner pairing card holds it
            # too, and saying "Off" over a code that is on screen right now
            # is the kind of small lie that makes a settings screen useless.
            if self._pairing.holds(_HINT_HOLDER):
                return "Off — but running while the corner pairing code is showing"
            return "Off"
        if self._pairing.locked:
            return "Locked — too many wrong codes. Turn it off and on again."
        if self._pairing.connected:
            return "A phone is connected. MENU → Phone remote shows the code again."
        url = self._pairing.url or "this machine"
        return (
            f"Scan the code under MENU → Phone remote, "
            f"or open {url} and enter {self._pairing.code}"
        )

    def set_phone_remote(self, enabled: bool) -> bool:
        """Returns False if the server refused to start, so Settings can say
        so rather than leaving a toggle that lies."""
        if not enabled:
            self._pairing.release(_REMOTE_HOLDER)
            return True
        return self._start_remote(_REMOTE_HOLDER)

    def _start_remote(self, holder: str, *, take_pointer: bool = True) -> bool:
        """Start the server on behalf of `holder` *and* fill in everything a
        phone needs to be useful the moment it connects.

        Taken out of `set_phone_remote` when the corner pairing card became
        a second reason to start it: a phone that scanned the card's code
        arrived at an empty catalogue and a volume slider reading nothing,
        because the setup below only ran on the Settings toggle's path.

        `take_pointer` is what the two paths do *not* share. Asking the
        portal for a remote-control grant puts a permission dialog on screen
        the first time, and that is fair when the user has just switched the
        remote on and unreasonable when Salon started it by itself because
        nothing was plugged in. The card's session takes the pointer when a
        phone actually turns up instead — see `_update_remote_hint`.
        """
        started = self._pairing.acquire(holder)
        if started:
            # The two things the phone needs that Salon does not otherwise
            # keep to hand: the installed-app list its search ranks against,
            # and where the volume actually is.
            self._scan_apps_for_phone()
            self._refresh_phone_volume()
            # The first snapshot, so a phone that connects immediately has
            # something to draw rather than an empty catalogue until the
            # cursor next moves.
            self._publish_remote_state()
            # And the pointer session, which the phone's trackpad injects
            # into. It is normally taken only when the catalogue has a
            # browser tile — that test is about the *gamepad* stick, which
            # exists to aim at a web page. A phone trackpad is useful over
            # anything, including Salon itself, so switching the remote on
            # is its own reason to ask. Still gated on the same consent
            # setting: this is the user saying whether Salon may move the
            # system pointer at all.
            if (
                take_pointer
                and self._settings.get_boolean("gamepad-pointer")
                and not self._pointer.ready
            ):
                self._start_pointer_session()
        return started

    def _on_gamepad_action(self, action: Action) -> None:
        if self._binding_capture is not None:
            # The press is being captured as a binding; acting on it as
            # well would navigate away from the screen doing the capturing.
            return
        self._set_pointer_visible(self._pointer_mode)
        if action in _DIRECTIONS:
            self._start_repeat(action)
        self._handle_action(action)

    def _start_repeat(self, action: Action) -> None:
        self._repeater.press(action)
        self._repeat_action = action
        if self._repeat_timer_id is None:
            self._repeat_timer_id = GLib.timeout_add(_REPEAT_POLL_MS, self._poll_repeat)

    def _stop_repeat(self, action: Action) -> None:
        if self._repeat_action is action:
            self._repeater.release()
            self._repeat_action = None

    def _poll_repeat(self) -> bool:
        action = self._repeater.poll()
        if action is not None:
            self._handle_action(action)
        return bool(GLib.SOURCE_CONTINUE)

    def _handle_action(self, action: Action) -> None:
        """Every input source lands here, and every screen change starts
        here — so this is also the one place the phone's snapshot has to be
        refreshed from. Wrapping the dispatch rather than adding a publish
        to each of its two dozen early returns: one of those would have been
        forgotten, and the symptom would be a phone showing the wrong screen
        with no clue why."""
        self._dispatch_action(action)
        self._publish_remote_state()

    def _dispatch_action(self, action: Action) -> None:
        self._last_input = time.monotonic()
        if self._screensaver.showing:
            # Swallowed, not acted on. Someone reaching for the remote to
            # see the clock must not launch Netflix by doing so.
            self._screensaver.hide()
            return

        if self._onboarding.get_visible():
            # Ahead of even MENU: the introduction is what explains that
            # MENU exists, and there is nothing behind it worth reaching.
            self._onboarding.handle_action(action)
            return

        if action is Action.MENU:
            # Highest priority, deliberately ahead of every other mode —
            # this is the only reachable way to suspend/shut down or exit
            # Salon on a fullscreen, keyboard-less kiosk, so it must never
            # be one of the things a stuck launch or an active pointer
            # session can swallow.
            if self._child_active or self._pointer_mode or self._launcher.has_child:
                # ...and while something else is in front of Salon it means
                # "bring me home", because a menu drawn in Salon's own
                # window would appear underneath Netflix where nobody can
                # see it. See _return_from_child.
                #
                # `has_child` is asked as well as the two mode flags, and it
                # is the one that makes MENU *reliable*. Those flags are set
                # from `on_child_focused`, which needs Salon's window to go
                # from active to inactive — an edge that never happens when
                # the window was already inactive at launch, which is what
                # the phone does every time it opens a tile while another
                # app is in front. Without this, MENU fell through to
                # opening the system menu underneath the app: invisible,
                # swallowing the next press to close itself again, and
                # looking for all the world like a button that works every
                # other time.
                self._return_from_child()
                return
            if self._text_entry.get_visible():
                # The keyboard is open on top of Settings. Closing Settings
                # from under it would leave a text field editing a panel
                # that is no longer on screen.
                return
            if self._settings_screen.get_visible():
                self._settings_screen.handle_action(action)
                return
            if self._phone_pairing.get_visible():
                # It is drawn above the system menu, so opening one behind
                # it would be a menu nobody can see taking every press.
                self._phone_pairing.close()
                return
            if self._system_menu.get_visible():
                self._system_menu.hide()
            else:
                self._show_system_menu()
            return

        # Above the menus it is opened from, and below MENU, which closes
        # everything: a screen showing a code is not a place MENU should
        # stop working.
        if self._phone_pairing.get_visible():
            self._phone_pairing.handle_action(action)
            return

        for menu in (self._system_menu, self._tile_menu):
            if not menu.get_visible():
                continue
            if action is Action.UP:
                menu.move(-1)
            elif action is Action.DOWN:
                menu.move(1)
            elif action is Action.OK:
                menu.activate_selected()
            elif action in (Action.BACK, Action.OPTIONS):
                menu.hide()
            return

        # Innermost first: text entry is opened *by* Settings, on top of
        # it, so it has to be offered the action before Settings is.
        if self._text_entry.get_visible():
            self._text_entry.handle_action(action)
            return

        if self._settings_screen.get_visible():
            self._settings_screen.note_action(action)
            self._settings_screen.handle_action(action)
            return

        if self._apps_grid.get_visible():
            if action is Action.OPTIONS:
                self._open_tile_menu(self._apps_grid.focused_tile, from_grid=True)
            else:
                self._apps_grid.handle_action(action)
            return

        if self._search.get_visible():
            self._search.handle_action(action)
            return

        # Volume is the one group that is true whatever is on screen: it
        # acts on the system's audio, not on a window, so it stays above
        # the "something else is in front" guards below.
        # `_on_volume_read` rather than the OSD directly: it shows the OSD
        # *and* carries the new level to the phone, so a slider in someone's
        # hand does not sit at the old position until they drag it.
        if action is Action.VOLUME_UP:
            audio.adjust_volume(1, lambda: audio.get_volume(self._on_volume_read))
            return
        if action is Action.VOLUME_DOWN:
            audio.adjust_volume(-1, lambda: audio.get_volume(self._on_volume_read))
            return
        if action is Action.MUTE:
            audio.toggle_mute(lambda: audio.get_volume(self._on_volume_read))
            return

        # Everything from here down draws or acts on Salon's own window, so
        # the guards for "an app is covering it" come first. They used not
        # to, and the three actions that sat above them all misfired from
        # behind a launched app: SEARCH opened the search overlay where
        # nobody could see it and then took every press, POWER opened the
        # system menu the same way, and PLAY_PAUSE with nothing playing fell
        # through to *launching the focused tile* on top of the app that was
        # already running — which is also what left MENU with no child to
        # close. The rule the MENU handler above states ("a menu drawn in
        # Salon's own window would appear underneath Netflix") is this one.
        if self._pointer_mode or self._child_active:
            if action is Action.PLAY_PAUSE:
                # The transport half only. The launch fallback below makes
                # sense on an idle home screen and nowhere else.
                if not self._now_playing.play_pause():
                    self._toast("Nothing is playing.")
                return
            if self._pointer_mode:
                if action is Action.SEARCH:
                    # While the cursor is being driven over a browser
                    # window, Salon's own search is the wrong thing to open
                    # — the text field the user is aiming at belongs to
                    # Chrome, so SEARCH toggles GNOME's on-screen keyboard
                    # for it instead.
                    set_onscreen_keyboard_enabled(not onscreen_keyboard_enabled())
                elif action is Action.OK:
                    self._pointer.click()
                elif action is Action.BACK:
                    self._pointer_mode = False
                    self._toast("Cursor off. Press MENU to close the app and come back.")
                return
            # A native app (e.g. a game client) reads the same raw gamepad
            # device directly — that input bypasses window focus entirely,
            # unlike keyboard/mouse, so Salon has to deliberately go quiet
            # rather than fight it for button presses. Resumes on exit, or
            # on MENU, which is handled above.
            return

        if action is Action.SEARCH:
            self._open_search()
            return
        if action is Action.PLAY_PAUSE:
            # Falls through to launching the focused tile when nothing is
            # playing: on a remote whose only large button is play, the
            # useless outcome is the one that does nothing at all.
            if not self._now_playing.play_pause():
                self._launch_focused()
            return
        if action is Action.POWER:
            # The system menu, not an immediate suspend. A television
            # remote's power key is one press away from every other key on
            # it, and Salon cannot know whether it was meant for the TV.
            self._show_system_menu()
            return

        if action is Action.BACK:
            if self._launcher.is_launching:
                self._launcher.cancel()
            # Otherwise a no-op: there's no parent screen at the top level
            # yet (no search overlay stack built), and BACK must never quit
            # Salon outright — see _on_key_pressed's dev-only Escape
            # shortcut, or MENU -> Exit Salon, for that.
            return

        if self._nav_focused:
            self._handle_nav_action(action)
            return

        if action is Action.OPTIONS:
            self._open_tile_menu(
                self._catalog.tile_at(self._focus.row, self._focus.col), from_grid=False
            )
            return

        if action in _DIRECTIONS:
            change = self._focus.handle(action)
            if change.moved:
                self._update_focus()
            elif change.bump is Bump.UP:
                # The top of the tiles is not a wall: it's the top bar. This
                # is the whole reason Search/Settings/Power are reachable at
                # all without knowing that MENU exists.
                self._set_nav_focused(True)
            elif change.bump is not Bump.NONE:
                self._rubber_band(change.bump)
        elif action is Action.OK:
            self._launch_focused()

    # --- top bar ----------------------------------------------------------

    def _set_nav_focused(self, focused: bool) -> None:
        self._nav_focused = focused
        self._status_bar.set_nav_focused(focused, index=0 if focused else None)
        widget = self._focused_widget()
        if widget is not None:
            self._publish_active_descendant(widget)
        # Only one thing on screen may carry the strong highlight at a time,
        # so the tile under the cursor drops its ring while the bar has it.
        self._update_focus()

    def _handle_nav_action(self, action: Action) -> None:
        if action is Action.DOWN or action is Action.BACK:
            self._set_nav_focused(False)
            return
        if action is Action.UP:
            self._rubber_band(Bump.UP)
            return
        if action in (Action.LEFT, Action.RIGHT):
            if not self._status_bar.move(-1 if action is Action.LEFT else 1):
                self._rubber_band(Bump.LEFT if action is Action.LEFT else Bump.RIGHT)
            return
        if action is Action.OK:
            # Whatever it opens covers the home screen, so hand focus back
            # to the tiles now — closing that screen must not drop the user
            # back onto a highlighted power button.
            self._set_nav_focused(False)
            self._status_bar.activate()

    def _on_right_stick(self, x: float, y: float) -> None:
        if self._pointer_mode and self._pointer.ready:
            self._pointer.move(x * _POINTER_SPEED, y * _POINTER_SPEED)

    def _on_pointer_ready(self, ok: bool) -> None:
        # The phone shows whether its trackpad and keyboard can reach other
        # applications, so the grant arriving (or being refused) is a change
        # it needs to hear about.
        self._publish_remote_state()
        if not ok:
            self._pointer_mode = False
            self._toast(
                "Salon wasn't allowed to move the pointer. You can grant it "
                "again from Settings, under Input."
            )

    def _start_pointer_session(self) -> None:
        # Export our window handle so the portal's consent dialog is
        # properly anchored to Salon instead of appearing unparented —
        # without this, xdg-desktop-portal logs "Failed to associate portal
        # window with parent window" and the dialog isn't reliably visible.
        root = self.get_root()
        surface = root.get_surface() if isinstance(root, Gtk.Window) else None
        if isinstance(surface, GdkWayland.WaylandToplevel):
            exported = surface.export_handle(self._on_handle_exported)
            if exported:
                return
        self._pointer.start()

    def _on_handle_exported(
        self, toplevel: GdkWayland.WaylandToplevel, handle: str, user_data: object = None
    ) -> None:
        self._pointer.start(parent_window=f"wayland:{handle}")

    # --- launching -----------------------------------------------------

    def on_window_active_changed(self, is_active: bool) -> None:
        """Called by SalonWindow's notify::is-active handler — half of the
        dual return-detection signal in §6.4 (the other half is the child
        process actually exiting, handled inside LauncherService)."""
        self._launcher.notify_window_active(is_active)

    def _open_search(self) -> None:
        self._set_nav_focused(False)
        self._search.open(self._searchable_tiles())

    def _searchable_tiles(self) -> list[Tile]:
        """Every catalogue tile, once.

        Deduplicated by id: a tile that is also in Recents legitimately
        appears in the catalogue twice, and listing it twice in the results
        reads as a bug. Shared with the phone's `/search`, which searches
        the same catalogue and would otherwise have its own copy of this to
        get subtly different.
        """
        seen: set[str] = set()
        tiles: list[Tile] = []
        for row in self._catalog.rows:
            for tile in row.tiles:
                if tile.id not in seen:
                    seen.add(tile.id)
                    tiles.append(tile)
        return tiles

    def _open_apps(self) -> None:
        """The all-apps grid, from the top bar's grid button."""
        self._system_menu.hide()
        if self._search.get_visible():
            self._search.close()
        self._set_nav_focused(False)
        self._apps_grid.open()

    # --- the per-tile options menu ---------------------------------------

    def _open_tile_menu(self, tile: Tile | None, *, from_grid: bool) -> None:
        """OPTIONS over a tile: what else can be done with this one thing.

        Deliberately not MENU. MENU has to keep meaning "system menu" at
        every depth — it is the escape hatch — so per-item actions need
        their own button, and every input source grew one (X on a pad, F10
        or `o` on a keyboard, contents-menu on a CEC remote).
        """
        if tile is None:
            return
        pinned = favourites.is_favourite(self._settings, tile.id)
        items: list[SystemMenuItem] = []
        if from_grid:
            items.append(SystemMenuItem(f"Open {tile.title}", lambda: self._launch_tile(tile)))
        items.append(
            SystemMenuItem(
                "Remove from Favourites" if pinned else "Add to Favourites",
                lambda: self._toggle_favourite(tile),
            )
        )
        if from_grid and self._config.rows:
            items.append(SystemMenuItem("Add to Home", lambda: self._add_tile_to_home(tile)))
        if not from_grid:
            # Straight to *this* tile's editor. Landing on the section list
            # instead — which is what this did — means four more navigations
            # to reach the thing the user already had the cursor on.
            located = self._locate_in_config(tile.id)
            if located is not None:
                row_id, tile_id = located
                items.append(
                    SystemMenuItem(
                        f"Edit {tile.title}…",
                        lambda: self._settings_screen_open_tile(row_id, tile_id),
                    )
                )
            items.append(SystemMenuItem("Edit tiles…", lambda: self._open_settings("tiles")))
        items.append(SystemMenuItem("Cancel", lambda: None))
        self._tile_menu.set_items(items, title=tile.title)
        self._tile_menu.show()

    def _toggle_favourite(self, tile: Tile) -> None:
        pinned = favourites.toggle_favourite(self._settings, tile.id)
        self._toast(
            f"{tile.title} pinned to Favourites"
            if pinned
            else f"{tile.title} removed from Favourites"
        )
        self._refresh_catalog(preserve_focus=True)

    def _add_tile_to_home(self, tile: Tile) -> None:
        """Copy an installed app out of the grid and into the catalogue.

        It goes into the first row, which is the one nearest the top of the
        screen and the only choice that doesn't need a second picker in
        front of a user holding a remote. Moving it afterwards is what the
        tile editor is for.
        """
        if any(t.id == tile.id for row in self._config.rows for t in row.tiles):
            self._toast(f"{tile.title} is already on the home screen.")
            return
        row = self._config.rows[0]
        # A copy, because add_tile renames the id it is handed to keep it
        # unique within the row — and the object the grid passed in is the
        # one its own widget is still rendering.
        if editing.add_tile(self._config, row.id, replace(tile)) is None:
            self._toast(f"{tile.title} couldn't be added.")
            return
        self._save_config()
        self._toast(f"{tile.title} added to {row.title or 'the first row'}.")

    # --- launching -------------------------------------------------------

    def _return_from_child(self) -> None:
        """Come back to Salon from whatever is in front of it.

        This is the answer to "how do I get out of Netflix with a
        controller". Wayland forbids a client raising itself, so Salon
        cannot simply put its own window back on top — the only lever it has
        over a window it does not own is the process it started, so MENU
        ends that process and the compositor hands focus back by itself.

        The gamepad is what makes this reachable at all: libmanette reads
        evdev directly, so button presses arrive even while Chrome holds
        keyboard focus. A CEC remote reaches it the same way. A keyboard
        does not, and can't — its events go to the focused window — which is
        why the toast at launch names the controller button.
        """
        title = self._launcher.child_title or "the app"
        if self._launcher.close_child():
            self._toast(f"Closing {title}…")
            return
        # No handle on it: a .desktop launch whose pid was a wrapper that
        # exited immediately (§11). Saying so beats a button that silently
        # does nothing — and the launcher is told to stop tracking it,
        # because nothing will ever report that app going away and MENU
        # would otherwise keep answering "I can't close that" long after the
        # user closed it themselves.
        self._pointer_mode = False
        self._child_active = False
        self._launcher.abandon()
        self._toast(f"Salon can't close {title} — use the app's own way out.")

    def _launch_focused(self) -> None:
        tile = self._catalog.tile_at(self._focus.row, self._focus.col)
        if tile is not None:
            self._launch_tile(tile)

    def _launch_tile(self, tile: Tile) -> None:
        """The single launch entry point, shared by the home rows and by
        search results — a tile found through search must go through exactly
        the same path as one on the home screen."""
        if tile.launch.kind is LaunchKind.BUILTIN:
            self._handle_builtin(tile.launch.target)
            return
        # Whichever full-screen browser it came from gets out of the way:
        # the launching overlay is stacked *below* search and the all-apps
        # grid, so leaving one of those up hides the only feedback that
        # anything is happening at all.
        if self._apps_grid.get_visible():
            self._apps_grid.close()
        if self._search.get_visible():
            self._search.close()
        if self._launcher.has_child:
            # Something is already out there. Only the phone can reach this
            # — on the television the launcher is behind the app and nobody
            # can press OK on a tile they cannot see — and launching over
            # the top of it is what breaks MENU: the launcher would forget
            # the first child completely, so the button that closes an app
            # would close the *new* one and leave the old app on screen with
            # nothing tracking it.
            #
            # So: close what is there, and open this once it has gone.
            self._pending_launch = tile
            self._return_from_child()
            return
        self._launcher.launch(tile)

    def _handle_builtin(self, target: str) -> None:
        if target == "settings":
            self._open_settings()
        elif target == "search":
            self._open_search()
        else:
            self._toast(f"There's nothing behind the {target} tile yet.")

    def _build_system_menu_items(self) -> list[SystemMenuItem]:
        # The reachable escape hatch on a fullscreen, keyboard-less kiosk:
        # a way into Settings, a way to power the machine down, and a way
        # out of Salon. Only the power actions logind says are available
        # are offered.
        # logind can refuse — an inhibitor holding a block lock, or a polkit
        # prompt that lands behind Salon's fullscreen window. Those used to
        # arrive as nothing at all: the menu closed and the machine carried
        # on running, which is indistinguishable from a button that isn't
        # wired up. Now the refusal is named.
        def fail(what: str) -> Callable[[str], None]:
            return lambda message: self._toast(f"{what} didn't happen: {message}")

        items: list[SystemMenuItem] = [
            SystemMenuItem("Settings", lambda: self._open_settings()),
            # Named for its state, because this is the only place that says
            # whether the remote is running at all.
            SystemMenuItem(
                "Phone remote" if self.phone_remote_running() else "Connect a phone",
                self._open_phone_pairing,
            ),
        ]
        if power.can_suspend():
            items.append(SystemMenuItem("Suspend", lambda: power.suspend(fail("Suspend"))))
        # Between Suspend and Restart, and above them in consequence: it is
        # the way to get from Salon to another session — the desktop, a
        # different user — without powering the machine down. "Exit Salon"
        # below leaves the process; this leaves the session, which under the
        # Salon unit's Restart=always is the only one of the two that
        # actually ends up somewhere else.
        if power.can_log_out():
            items.append(SystemMenuItem("Log Out", lambda: power.log_out(fail("Log out"))))
        if power.can_reboot():
            items.append(
                SystemMenuItem("Restart", lambda: power.reboot(fail("Restart")), danger=True)
            )
        if power.can_power_off():
            items.append(
                SystemMenuItem(
                    "Shut Down", lambda: power.power_off(fail("Shut down")), danger=True
                )
            )
        items.append(SystemMenuItem("About Salon", lambda: self._open_settings("about")))
        items.append(SystemMenuItem("Exit Salon", self._application.quit))
        items.append(SystemMenuItem("Cancel", lambda: None))
        return items

    def _on_launch_started(self, tile: Tile) -> None:
        self._current_launch_is_browser = _is_browser_launch(tile)
        # Resolved from the tile rather than read off the focused widget:
        # a launch can come from a search result, which has no counterpart
        # in the home rows at all. The resolver caches, so this is cheap.
        artwork = self._artwork.resolve(tile, icon_size=round(self._metrics.height * 0.5))
        self._launching_overlay.show_for(
            tile,
            accent=artwork.accent,
            hint=f"{self._close_hint()} to close it and come back to Salon",
        )
        recents.push_recent(self._settings, tile.id)
        self._refresh_catalog(preserve_focus=True)
        self._publish_remote_state()

    def _on_child_focused(self) -> None:
        self._launching_overlay.hide()
        tile_title = self._launcher.child_title or "the app"
        # On by default, but still a preference: the RemoteDesktop grant is
        # taken once at startup and restored silently after that (see
        # _prewarm_pointer_session), which is what made it affordable to
        # default on. Turning it off in Settings → Input leaves a browser
        # tile navigable only by whatever the site itself offers.
        if self._current_launch_is_browser and self._settings.get_boolean("gamepad-pointer"):
            self._pointer_mode = True
            self._start_pointer_session()
            self._toast(
                "Right stick = cursor, A = click, Y = keyboard, "
                + ("START or phone Menu" if self._pairing.connected else "START")
                + " = close and come back"
            )
        else:
            self._child_active = True
            self._toast(f"{self._close_hint()} to close {tile_title} and come back.")
        # The child taking focus arrives asynchronously, long after the
        # press that launched it — so without this the phone's header still
        # said "home" while the application was on the television, and only
        # caught up at the *next* button press. It is the one line on the
        # phone that answers "where am I", and it was always one event
        # behind.
        self._publish_remote_state()

    def _on_launch_timed_out(self) -> None:
        self._launching_overlay.show_timed_out()
        self._publish_remote_state()

    def _on_returned(self) -> None:
        self._launching_overlay.hide()
        # Salon's own way back in. Under GNOME Shell this rides on top of
        # the Shell's window-close animation; under GNOME Kiosk, whose
        # compositor hides a destroyed window with no transition at all, it
        # is the entire thing standing between an application and the home
        # screen.
        self._return_fade.play()
        self._pointer_mode = False
        self._child_active = False
        self._publish_remote_state()
        pending, self._pending_launch = self._pending_launch, None
        if pending is not None:
            # A tile tapped on the phone while another app was in front. The
            # old one has just gone; give the compositor a moment to hand
            # focus back before spawning the next, because the return
            # detection for *that* launch is the window going inactive and
            # it can only go inactive from active.
            GLib.timeout_add(_RELAUNCH_DELAY_MS, lambda: self._start_pending(pending))

    def _start_pending(self, tile: Tile) -> bool:
        self._launch_tile(tile)
        return bool(GLib.SOURCE_REMOVE)

    def _close_hint(self) -> str:
        """How to get back out, named for the hardware that is actually
        connected. A phone in someone's hand has a Menu button of its own,
        and telling them to press START on a controller they may not own is
        the difference between a way out and a trapped television."""
        if self._pairing.connected:
            return "Press START on the controller, or Menu on your phone,"
        return "Press START on the controller"

    def _on_launch_error(self, message: str) -> None:
        self._toast(message)

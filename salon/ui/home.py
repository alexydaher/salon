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
from salon.core import editing, tokens  # noqa: E402
from salon.core.catalog import Catalog, sanitize  # noqa: E402
from salon.core.errors import ConfigError  # noqa: E402
from salon.core.focus import Bump, FocusModel  # noqa: E402
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile  # noqa: E402
from salon.core.provider import CatalogBuild, ProviderOutcome  # noqa: E402
from salon.input.actions import Action, Repeater, RepeaterTiming  # noqa: E402
from salon.input.cec_in import CecSource  # noqa: E402
from salon.input.gamepad import GamepadSource  # noqa: E402
from salon.input.keyboard import action_for_keyval  # noqa: E402
from salon.providers import favourites, recents  # noqa: E402
from salon.providers.registry import ProviderRegistry  # noqa: E402
from salon.services import appinfo, audio, cec_out, power  # noqa: E402
from salon.services.artwork import ArtworkResolver, artwork_drop_dir  # noqa: E402
from salon.services.launcher import LauncherService  # noqa: E402
from salon.services.pointer_injector import (  # noqa: E402
    PointerInjector,
    onscreen_keyboard_enabled,
    set_onscreen_keyboard_enabled,
)
from salon.ui.appsgrid import AppsGrid  # noqa: E402
from salon.ui.backdrop import Backdrop  # noqa: E402
from salon.ui.motion import SizeReporter  # noqa: E402
from salon.ui.onboarding import Onboarding  # noqa: E402
from salon.ui.osd import VolumeOsd  # noqa: E402
from salon.ui.overlays import LaunchingOverlay, SystemMenu, SystemMenuItem  # noqa: E402
from salon.ui.scale import Scale, ScaleManager  # noqa: E402
from salon.ui.search import SearchOverlay  # noqa: E402
from salon.ui.settings.screen import SettingsScreen  # noqa: E402
from salon.ui.statusbar import StatusBar  # noqa: E402
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

_DIRECTIONS = (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT)

# How often the held-direction repeater is polled. Independent of the
# Repeater's own fire cadence (400/120/60ms) — this just needs to be
# frequent enough not to miss the fastest of those intervals.
_REPEAT_POLL_MS = 30

# Boundary rubber-band (§6.2): hitting the end of a row or the last row
# produces a short overshoot-and-settle rather than silence, which reads as
# a broken remote.
_BUMP_DISTANCE_DU = 26.0
_BUMP_MS = 90

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
    clip edge — especially under the status bar, where it collides with the
    clock — reads as a rendering fault. Masking the *rows* rather than
    painting a scrim over them keeps the backdrop's ambient glow intact
    underneath.
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

    def __init__(self, viewport: Gtk.Fixed, child: Gtk.Widget, *, vertical: bool) -> None:
        self._viewport = viewport
        self._child = child
        self._vertical = vertical
        self._value = 0.0
        self._resting = 0.0
        self._animations_enabled = True

        params = Adw.SpringParams.new(SPRING_DAMPING_RATIO, SPRING_MASS, SPRING_STIFFNESS)
        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.SpringAnimation.new(viewport, 0.0, 0.0, params, target)

        bump_target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._bump_animation = Adw.TimedAnimation.new(viewport, 0.0, 0.0, _BUMP_MS, bump_target)
        self._bump_animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self._bump_animation.connect("done", self._on_bump_done)

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = enabled

    def _on_tick(self, value: float) -> None:
        self._value = value
        dx, dy = (0.0, value) if self._vertical else (value, 0.0)
        self._viewport.set_child_transform(self._child, _translate(dx, dy))

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

        self._viewport = _LayoutViewport()
        self._viewport.set_overflow(Gtk.Overflow.HIDDEN)
        self._viewport_host = SizeReporter(self._viewport, self._on_viewport_resized)
        self._viewport_host.set_hexpand(True)
        self._viewport_host.set_vexpand(True)
        self._overlay.add_overlay(self._viewport_host)

        # A Fixed rather than a Box: consecutive rows' footprints overlap,
        # because every tile carries transparent bleed for its bloom, and a
        # box's non-negative spacing can't express an overlap.
        self._rows_content = Gtk.Fixed()
        self._viewport.put(self._rows_content, 0, 0)
        self._row_anchor = _AxisSpring(self._viewport, self._rows_content, vertical=True)

        self._status_bar = StatusBar(
            self._scale,
            on_search=self._open_search,
            on_apps=self._open_apps,
            on_settings=self._open_settings,
            on_power=self._show_system_menu,
        )
        # UP from the first row of tiles moves into the bar; DOWN comes back.
        self._nav_focused = False
        self._overlay.add_overlay(self._status_bar)

        self._launching_overlay = LaunchingOverlay(self._scale)
        self._overlay.add_overlay(self._launching_overlay)

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

        self._search = SearchOverlay(
            self._scale,
            self._artwork,
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

        self._text_entry = TextEntryOverlay(self._scale)
        self._overlay.add_overlay(self._text_entry)

        # Topmost, and shown before anything else on a first run: it is the
        # only thing on screen that explains the buttons.
        self._onboarding = Onboarding(self._scale, self._finish_onboarding)
        self._overlay.add_overlay(self._onboarding)

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
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_pointer_motion)
        self.add_controller(motion)
        self._last_pointer_xy: tuple[float, float] | None = None
        # Cursor stays hidden until the mouse actually moves: a TV launcher
        # that boots with an arrow parked in the middle of the screen looks
        # broken, and the pointer is only one of three input paths here.
        self._pointer_visible = False

        self._pointer_mode = False
        self._child_active = False
        self._current_launch_is_browser = False
        self._pointer = PointerInjector(
            on_ready=self._on_pointer_ready,
            load_restore_token=lambda: self._settings.get_string(
                "remote-desktop-restore-token"
            ),
            save_restore_token=lambda token: self._settings.set_string(
                "remote-desktop-restore-token", token
            ),
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
        )

        # The TV's own remote, over HDMI-CEC. Same reference-keeping reason:
        # the source owns the cec-client subprocess and its stream reader.
        self._cec = CecSource(self._on_cec_action)
        self._apply_cec_setting()
        self._settings.connect("changed::cec-enabled", lambda *_: self._apply_cec_setting())

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
        self._settings.connect(
            "changed::reduced-motion", lambda *_: self._apply_animation_setting()
        )
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

    # --- scale / geometry -------------------------------------------------

    @property
    def _animations_enabled(self) -> bool:
        """§7.2: respect gtk-enable-animations and the reduced-motion
        override. When off, focus changes are instant — the tile's ring and
        bloom carry the indication instead of the motion."""
        if self._settings.get_boolean("reduced-motion"):
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
        self._content_height_px = max(0.0, y - self._row_gap)

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
        self._status_bar.set_scale(scale)
        self._launching_overlay.set_scale(scale)
        self._osd.set_scale(scale)
        self._system_menu.set_scale(scale)
        self._tile_menu.set_scale(scale)
        self._search.set_scale(scale)
        self._apps_grid.set_scale(scale)
        self._settings_screen.set_scale(scale)
        self._text_entry.set_scale(scale)
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
        enabled = self._animations_enabled
        self._row_anchor.set_animations_enabled(enabled)
        for row in self._rows:
            row.scroller.set_animations_enabled(enabled)
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
        self._system_menu.show()

    def _open_settings(self) -> None:
        self._system_menu.hide()
        if self._search.get_visible():
            self._search.close()
        if self._apps_grid.get_visible():
            self._apps_grid.close()
        # A mouse can click the top bar's buttons without the D-pad ever
        # having gone up there, and a click that leaves the bar highlighted
        # behind a full-screen overlay is a cursor in two places at once.
        self._set_nav_focused(False)
        self._settings_screen.open()

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
            for col, tile in enumerate(row.tiles):
                artwork = self._artwork.resolve(tile, icon_size=round(metrics.height * 0.5))
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

        self._row_anchor.set_animations_enabled(animations)
        self._layout_rows()
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
        self._viewport.set_fades(self._status_height, self._safe_margin)

    def _attach_pointer(self, widget: TileWidget, row: int, col: int) -> None:
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self._on_tile_clicked(row, col))
        widget.add_controller(click)

        motion = Gtk.EventControllerMotion()
        # `motion`, not `enter`: focus should follow a pointer the user is
        # actually moving, not jump because a row scrolled a different tile
        # under a stationary cursor.
        motion.connect("motion", lambda *_: self._on_tile_hovered(row, col))
        widget.add_controller(motion)

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
        if tile is not None:
            self._settings.set_string("last-focused-tile", tile.id)
            focused_widget = self._focused_widget()
            if focused_widget is not None:
                self._backdrop.set_accent(focused_widget.artwork_accent)
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

    def _row_anchor_y(self) -> float:
        """The focused row holds a fixed vertical anchor (§6.1) — clamped at
        the top so a catalogue shorter than the screen sits under the status
        bar rather than floating in the middle of dead space.

        Deliberately *not* clamped at the bottom. Refusing to scroll past
        the end of the content is right for a row (a horizontal void beside
        the last tile looks broken) and wrong for the stack of rows: with
        four rows on a 1080p screen it left barely 90px of travel, so the
        bottom two rows could never come up to the anchor and the last one
        stayed parked under the fold with its tiles half off-screen. Every
        ten-foot launcher lets the last row rise to the anchor line and
        leaves empty space below it; that space is where the backdrop lives.
        """
        viewport_height = self._viewport_height or _FALLBACK_VIEWPORT_HEIGHT_PX
        top_inset = self._status_height + self._safe_margin
        bottom_inset = self._safe_margin
        content_height = self._content_height()

        if content_height <= viewport_height - top_inset - bottom_inset:
            return top_inset

        focused_center = self._row_tile_top(self._focus.row) + self._focused_tile_height() / 2.0
        desired = viewport_height * tokens.ROW_ANCHOR_FRACTION - focused_center
        return min(top_inset, desired)

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
        self._set_pointer_visible(True)

    def _on_scroll(self, controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
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
        action = action_for_keyval(keyval)
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
        action = action_for_keyval(keyval)
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
        # A TV remote produces discrete presses with no key-up, so it feeds
        # _handle_action directly rather than the Repeater — the television
        # is already doing its own auto-repeat.
        self._set_pointer_visible(False)
        self._handle_action(action)

    def _on_gamepad_action(self, action: Action) -> None:
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
            if self._child_active or self._pointer_mode:
                # ...and while something else is in front of Salon it means
                # "bring me home", because a menu drawn in Salon's own
                # window would appear underneath Netflix where nobody can
                # see it. See _return_from_child.
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
            if self._system_menu.get_visible():
                self._system_menu.hide()
            else:
                self._system_menu.show()
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

        if action is Action.SEARCH:
            if self._pointer_mode:
                # While the gamepad is driving the system cursor over a
                # browser window, Salon's own search is the wrong thing to
                # open — the text field the user is aiming at belongs to
                # Chrome, so SEARCH toggles GNOME's on-screen keyboard for
                # it instead.
                set_onscreen_keyboard_enabled(not onscreen_keyboard_enabled())
            else:
                self._open_search()
            return
        if action is Action.VOLUME_UP:
            audio.adjust_volume(1, lambda: audio.get_volume(self._osd.show_volume))
            return
        if action is Action.VOLUME_DOWN:
            audio.adjust_volume(-1, lambda: audio.get_volume(self._osd.show_volume))
            return
        if action is Action.MUTE:
            audio.toggle_mute(lambda: audio.get_volume(self._osd.show_volume))
            return

        if self._pointer_mode:
            if action is Action.OK:
                self._pointer.click()
            elif action is Action.BACK:
                self._pointer_mode = False
                self._toast("Cursor off. Press MENU to close the app and come back.")
            return

        if self._child_active:
            # A native app (e.g. a game client) reads the same raw gamepad
            # device directly — that input bypasses window focus entirely,
            # unlike keyboard/mouse, so Salon has to deliberately go quiet
            # rather than fight it for button presses. Resumes on exit, or
            # on MENU, which is handled above.
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
        # Deduplicated by id: a tile that's also in Recents legitimately
        # appears in the catalogue twice, and listing it twice in the
        # results reads as a bug.
        seen: set[str] = set()
        tiles: list[Tile] = []
        for row in self._catalog.rows:
            for tile in row.tiles:
                if tile.id not in seen:
                    seen.add(tile.id)
                    tiles.append(tile)
        self._set_nav_focused(False)
        self._search.open(tiles)

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
            items.append(SystemMenuItem("Edit tiles…", self._open_settings))
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
        # does nothing.
        self._pointer_mode = False
        self._child_active = False
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

        items: list[SystemMenuItem] = [SystemMenuItem("Settings", self._open_settings)]
        if power.can_suspend():
            items.append(SystemMenuItem("Suspend", lambda: power.suspend(fail("Suspend"))))
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
        items.append(SystemMenuItem("About Salon", self._open_settings))
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
            hint="Press START on the controller to close it and come back to Salon",
        )
        recents.push_recent(self._settings, tile.id)
        self._refresh_catalog(preserve_focus=True)

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
                "START = close and come back"
            )
        else:
            self._child_active = True
            self._toast(f"Press START on the controller to close {tile_title} and come back.")

    def _on_launch_timed_out(self) -> None:
        self._launching_overlay.show_timed_out()

    def _on_returned(self) -> None:
        self._launching_overlay.hide()
        self._pointer_mode = False
        self._child_active = False

    def _on_launch_error(self, message: str) -> None:
        self._toast(message)

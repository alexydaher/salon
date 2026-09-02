# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

import os

from salon.services.component import ServiceComponent
from salon.ui.home_rows import _RowWidgets
from salon.ui.home_shared import (
    CEC,
    AppsGrid,
    ArtworkResolver,
    ConsoleSidebar,
    DetailBar,
    Gdk,
    Gtk,
    LaunchingOverlay,
    Legend,
    NowPlayingStatus,
    NowPlayingWatcher,
    PairingServer,
    RemoteHint,
    RemoteHintHost,
    RemoteRow,
    ScaleManager,
    ScreenSaver,
    SearchOverlay,
    StatusBar,
    StatusInfo,
    ThemeManager,
    Tile,
    VolumeOsd,
    nowplaying,
    time,
)


class HomeSurfaceSetup(ServiceComponent):
    def _setup_surfaces(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        self._owner._pairing = PairingServer(
            on_action=self._owner._on_phone_action,
            on_pointer=self._owner._on_phone_pointer,
            on_click=self._owner._on_phone_click,
            on_locked=self._owner._on_phone_locked,
            on_launch=self._owner._on_phone_launch,
            on_transport=self._owner._on_phone_transport,
            on_running=self._owner._on_phone_running,
            art_for=self._owner._art_for_phone,
            pointer_ready=lambda: self._owner._pointer.ready,
            on_remote_text=self._owner._type_remotely,
            on_clear_text=self._owner._clear_remote_field,
            on_search=self._owner._search_for_phone,
            on_tile_action=self._owner._on_phone_tile_action,
            on_volume=self._owner._on_phone_volume,
            on_mute=self._owner._on_phone_mute,
            on_scroll=self._owner._on_phone_scroll,
            on_scroll_end=self._owner._on_phone_scroll_end,
            on_button=self._owner._on_phone_button,
            on_apps=self._owner._all_apps_for_phone,
            np_art_for=self._owner._now_playing_art_for_phone,
            tune_read=self._owner._tune_read_for_phone,
            tune_write=self._owner._tune_write_for_phone,
        )
        self._owner._status_info = StatusInfo(self._owner._scale)
        self._owner._status_bar = StatusBar(
            self._owner._scale,
            on_search=self._owner._open_search,
            on_apps=self._owner._open_apps,
            on_phone=self._owner._open_phone_pairing,
            on_settings=self._owner._open_settings,
            on_power=self._owner._show_power_menu,
        )
        self._owner._nav_focused = False
        self._owner._menu_focus_owned = False
        self._owner._menu_origin_nav_focused = False
        self._owner._overlay.add_overlay(self._owner._status_bar)
        # Playback is global state rather than detail about the selected
        # tile, so give it the otherwise quiet centre of the top bar.  It is
        # an independent overlay child: putting it in the bottom row made it
        # compete with both the selection description and the button legend.
        self._owner._now_playing_status = NowPlayingStatus(
            self._owner._scale, on_activate=self._owner._toggle_source_playback
        )
        self._owner._console_sidebar = ConsoleSidebar(
            self._owner._scale,
            self._owner._status_info,
            self._owner._now_playing_status,
        )
        self._owner._overlay.add_overlay(self._owner._console_sidebar)
        self._owner._home_title = Gtk.Label(label="Home")
        self._owner._home_title.add_css_class("salon-home-title")
        self._owner._home_title.set_halign(Gtk.Align.START)
        self._owner._home_title.set_valign(Gtk.Align.START)
        self._owner._home_title.set_can_target(False)
        self._owner._overlay.add_overlay(self._owner._home_title)
        # One row, not two overlay children. Both remaining widgets want the
        # bottom of the screen and one of them has to ellipsize when they
        # meet; as independent overlay children each was given its natural
        # size and the description simply ran under the legend.
        self._owner._detail_bar = DetailBar(self._owner._scale)
        self._owner._legend = Legend(self._owner._scale)
        self._owner._bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._owner._bottom_bar.add_css_class("salon-bottom-bar")
        self._owner._bottom_bar.set_valign(Gtk.Align.END)
        self._owner._bottom_bar.set_halign(Gtk.Align.FILL)
        self._owner._bottom_bar.set_can_target(False)
        self._owner._bottom_bar.append(self._owner._detail_bar)
        self._owner._bottom_bar.append(self._owner._legend)
        self._owner._overlay.add_overlay(self._owner._bottom_bar)
        # Which kind of device sent the last press, so the legend can name
        # its buttons rather than Salon's intents. Starts as the remote's
        # vocabulary: "OK" and "Menu" are what a television's own remote
        # says, and it is the input this is built for.
        self._owner._input_source = CEC
        self._owner._gamepad_count = 0
        self._owner._remote_hint = RemoteHintHost(
            RemoteHint(
                self._owner._scale,
                self._owner._pairing,
                on_open=self._owner._open_phone_pairing,
            ),
            self._owner._scale,
        )
        self._owner._launching_overlay = LaunchingOverlay(self._owner._scale)
        self._owner._overlay.add_overlay(self._owner._launching_overlay)
        self._owner._screensaver = ScreenSaver(self._owner._scale)
        self._owner._overlay.add_overlay(self._owner._screensaver)
        self._owner._idle_id: int | None = None
        self._owner._last_input = time.monotonic()
        self._owner._apply_screensaver_setting()
        self._owner._osd = VolumeOsd(self._owner._scale)
        self._owner._overlay.add_overlay(self._owner._osd)
        self._owner._artwork = ArtworkResolver(
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()),
            on_fetched=self._owner._on_artwork_fetched,
        )
        self._owner._current_player: nowplaying.Player | None = None
        self._owner._now_playing = NowPlayingWatcher(self._owner._on_now_playing)
        if not os.environ.get("SALON_CAPTURE_MODE"):
            self._owner._now_playing.start()
        self._owner._remote_rows: tuple[RemoteRow, ...] = ()
        self._owner._phone_apps: list[Tile] = []
        self._owner._phone_apps_scanned = False
        self._owner._phone_volume = -1.0
        self._owner._phone_muted = False
        self._owner._search = SearchOverlay(
            self._owner._scale,
            self._owner._artwork,
            self._owner._pairing,
            on_launch=self._owner._launch_tile,
            on_options=lambda tile: self._owner._open_tile_menu(tile, from_grid=True),
            on_close=self._owner._on_global_surface_closed,
        )
        self._owner._overlay.add_overlay(self._owner._search)
        self._owner._apps_grid = AppsGrid(
            self._owner._scale,
            self._owner._artwork,
            tile_scale=self._owner._settings.get_double("tile-scale"),
            on_launch=self._owner._launch_tile,
            on_close=self._owner._on_global_surface_closed,
            on_focus_top_bar=lambda: self._owner._set_nav_focused(True),
            on_count=self._owner._status_info.set_application_count,
        )
        self._owner._overlay.add_overlay(self._owner._apps_grid)
        self._owner._rows: list[_RowWidgets] = []

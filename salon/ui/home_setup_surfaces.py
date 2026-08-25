# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view construction stage."""

from salon.services.component import ServiceComponent
from salon.ui.home_rows import *
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomeSurfaceSetup(ServiceComponent):
    def _setup_surfaces(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
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
        self._nav_focused = False
        self._overlay.add_overlay(self._status_bar)
        self._detail_bar = DetailBar(self._scale)
        self._overlay.add_overlay(self._detail_bar)
        self._gamepad_count = 0
        self._remote_hint = RemoteHint(self._scale, self._pairing, on_open=self._open_phone_pairing)
        self._overlay.add_overlay(self._remote_hint)
        self._now_playing = NowPlayingWatcher(self._on_now_playing)
        self._now_playing.start()
        self._launching_overlay = LaunchingOverlay(self._scale)
        self._overlay.add_overlay(self._launching_overlay)
        self._screensaver = ScreenSaver(self._scale)
        self._overlay.add_overlay(self._screensaver)
        self._idle_id: int | None = None
        self._last_input = time.monotonic()
        self._apply_screensaver_setting()
        self._osd = VolumeOsd(self._scale)
        self._overlay.add_overlay(self._osd)
        self._artwork = ArtworkResolver(
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()),
            on_fetched=self._rebuild_row_widgets,
        )
        self._remote_rows: tuple[RemoteRow, ...] = ()
        self._phone_apps: list[Tile] = []
        self._phone_apps_scanned = False
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

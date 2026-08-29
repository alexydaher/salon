# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    _BUMP_DISTANCE_DU,
    _HINT_HOLDER,
    GLib,
    Gtk,
    Repeater,
    RepeaterTiming,
    Scale,
    audio,
    metrics_for,
    motion,
    time,
    tokens,
)


class HomePreferences(ServiceComponent):
    def _on_gamepads_changed(self, count: int) -> None:
        self._owner._gamepad_count = count
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
        self._owner._status_bar.set_connection_state(
            controller=self._owner._gamepad_count > 0,
            phone=self._owner._pairing.connected,
        )
        wanted = (
            self._owner._settings.get_boolean("remote-hint") and self._owner._gamepad_count == 0
        )
        if wanted:
            if not self._owner._pairing.holds(_HINT_HOLDER):
                self._owner._start_remote(_HINT_HOLDER, take_pointer=False)
        elif self._owner._pairing.holds(_HINT_HOLDER) and not self._owner._pairing.connected:
            self._owner._pairing.release(_HINT_HOLDER)
        if (
            self._owner._pairing.connected
            and self._owner._pairing.holds(_HINT_HOLDER)
            and self._owner._settings.get_boolean("gamepad-pointer")
            and not self._owner._pointer.ready
        ):
            # A phone answered the card. Now the trackpad is a thing someone
            # is about to use, so the grant is worth asking for.
            self._owner._start_pointer_session()
        visible = (
            wanted and not self._owner._pairing.connected and self._owner._remote_hint.refresh()
        )
        self._owner._remote_hint.set_visible(visible)

    @property
    def _animations_enabled(self) -> bool:
        """§7.2: respect gtk-enable-animations and the reduced-motion
        override. When off, focus changes are instant — the tile's ring and
        bloom carry the indication instead of the motion."""
        if self._owner._settings.get_boolean("reduced-motion"):
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
        owner, scale = self._owner, self._owner._scale
        # Read here rather than cached at startup (§6.8 Appearance), so a
        # change lands as soon as the rows are rebuilt. The heading follows
        # the tile size: 60du of fixed overhead per row, over a third of a
        # five-row pitch, so at full size it costs a whole step of scale.
        tile_scale = owner._tile_scale = owner._settings.get_double("tile-scale")
        heading_du = tokens.scaled_type_size_du("row-heading", tile_scale)
        owner._metrics = metrics_for(scale, size_scale=tile_scale)
        owner._safe_margin = scale.safe_margin
        owner._heading_size = scale.du(heading_du)
        owner._heading_height = scale.du(heading_du * 1.35)
        owner._heading_gap = scale.du(tokens.ROW_HEADING_GAP_DU * tile_scale)
        density = owner._settings.get_double("row-spacing-scale")
        owner._row_gap = scale.du(tokens.ROW_GAP_DU * density)
        owner._status_height = scale.du(tokens.STATUS_BAR_HEIGHT_DU)
        owner._detail_height = scale.du(tokens.DETAIL_BAR_HEIGHT_DU)
        owner._bump_distance = scale.du(_BUMP_DISTANCE_DU)

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
        for row in self._owner._rows:
            tops.append(y)
            y += (
                self._owner._heading_height
                + self._owner._heading_gap
                + row.metrics.height
                + self._owner._row_gap
            )
        self._owner._row_tops = tops
        trailing = self._owner._rows[-1].metrics.bleed if self._owner._rows else 0.0
        # The last row's bleed counts as content. It is the room the tile
        # needs for the focus growth and the bloom, and a scroll limit that
        # stopped at the card's own bottom edge put both of them past the end
        # of the band: the focused tile in the last row had its ring sliced
        # off by the clip, which is exactly the rendering fault the edge fade
        # exists to avoid.
        self._owner._content_height_px = max(0.0, y - self._owner._row_gap + trailing)

    def _row_top(self, row_index: int) -> float:
        if 0 <= row_index < len(self._owner._row_tops):
            return self._owner._row_tops[row_index]
        return 0.0

    def _row_tile_top(self, row_index: int) -> float:
        return self._row_top(row_index) + self._owner._heading_height + self._owner._heading_gap

    def _focused_tile_height(self) -> float:
        if 0 <= self._owner._focus.row < len(self._owner._rows):
            return self._owner._rows[self._owner._focus.row].metrics.height
        return self._owner._metrics.height

    def _content_height(self) -> float:
        return self._owner._content_height_px

    def _on_scale_changed(self, scale: Scale) -> None:
        scale = scale.with_safe_area(self._owner._settings.get_double("safe-area-percent"))
        self._owner._scale = scale
        self._apply_metrics()
        self._apply_scale_to_surfaces(scale)
        self._owner._launcher.browser_scale_factor = tokens.browser_scale_factor(
            scale.viewport_height_px
        )
        self._owner._rebuild_row_widgets()

    def _apply_scale_to_surfaces(self, scale: Scale) -> None:
        self._owner._status_info.set_scale(scale)
        self._owner._remote_hint.set_scale(scale)
        self._owner._status_bar.set_scale(scale)
        self._owner._detail_bar.set_scale(scale)
        self._owner._now_playing_status.set_scale(scale)
        self._owner._legend.set_scale(scale)
        self._owner._launching_overlay.set_scale(scale)
        self._owner._osd.set_scale(scale)
        self._owner._system_menu.set_scale(scale)
        self._owner._tile_menu.set_scale(scale)
        self._owner._search.set_scale(scale)
        self._owner._apps_grid.set_scale(scale, tile_scale=self._owner._tile_scale)
        self._owner._settings_screen.set_scale(scale)
        self._owner._text_entry.set_scale(scale)
        self._owner._phone_pairing.set_scale(scale)
        self._owner._onboarding.set_scale(scale)

    def _on_viewport_resized(self, width: int, height: int) -> None:
        self._owner._viewport_width = width
        self._owner._viewport_height = height
        self._owner._layout_rows()
        self._owner._update_focus(animate=False)

    def _apply_layout_settings(self) -> None:
        safe_area = self._owner._settings.get_double("safe-area-percent")
        self._owner._scale = self._owner._scale.with_safe_area(safe_area)
        self._apply_metrics()
        self._apply_scale_to_surfaces(self._owner._scale)
        self._owner._rebuild_row_widgets()

    def _repeat_timing(self) -> RepeaterTiming:
        interval = self._owner._settings.get_int("key-repeat-interval-ms") / 1000.0
        # Acceleration keeps the design's 2:1 relationship (§6.2) rather
        # than a fixed 60ms floor: a user who slowed repeat down because it
        # was too fast must not get a fast phase quicker than their choice.
        return RepeaterTiming(
            initial_delay=self._owner._settings.get_int("key-repeat-initial-ms") / 1000.0,
            interval=interval,
            fast_interval=interval / 2.0,
        )

    def _apply_repeat_settings(self) -> None:
        # Rebuilt rather than mutated: RepeaterTiming is frozen, and any
        # direction held across the change is released against the new
        # object harmlessly.
        self._owner._repeater = Repeater(time.monotonic, self._repeat_timing())
        self._owner._repeat_action = None

    def _apply_preferred_sink(self) -> None:
        """§6.8 Audio: the chosen output is stored by description, because
        wireplumber node ids are not stable across reboots. Missing hardware
        is not an error — an output that isn't plugged in today simply
        leaves the system default alone."""
        wanted = self._owner._settings.get_string("audio-sink")
        if not wanted:
            return

        def choose(sinks: list[audio.Sink]) -> None:
            for sink in sinks:
                if sink.description == wanted and not sink.is_default:
                    audio.set_default_sink(sink.id)
                    return

        audio.list_sinks(choose)

    def _on_accent_changed(self) -> None:
        self._owner._backdrop.queue_draw()
        for row in self._owner._rows:
            for widget in row.tiles:
                widget.queue_draw()

    def _apply_animation_setting(self) -> None:
        # The speed goes first: `_animations_enabled` asks the motion module
        # whether the dial is at zero, so reading it before this line would
        # answer for the previous value.
        motion.set_animation_speed(self._owner._settings.get_double("animation-scale"))
        enabled = self._animations_enabled
        self._owner._row_anchor.set_animations_enabled(enabled)
        for row in self._owner._rows:
            row.scroller.set_animations_enabled(enabled)
        self._owner._return_fade.set_enabled(enabled)
        for surface in self._owner._faded_surfaces:
            surface.set_fade_enabled(enabled)
        self._owner._rebuild_row_widgets()

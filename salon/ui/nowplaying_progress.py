# SPDX-License-Identifier: GPL-3.0-or-later
"""Truthful, locally advancing MPRIS timelines for the Salon sidebar."""

from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

from salon.core.nowplaying import PLAYING, Player, describe  # noqa: E402

_TICK_MS = 250


class SquareCover(Gtk.Widget):
    """A fixed-size, centre-cropped cover that cannot resize its card.

    Square with a small corner radius rather than a circle: it reads as
    album/thumbnail art in the same visual language as the tiles, and a
    square keeps more of a wide video thumbnail than a circular crop does.
    """

    def __init__(self) -> None:
        super().__init__()
        self._paintable: Gdk.Paintable | None = None
        self._size = 1
        # Never let a taller row stretch the crop into a portrait rectangle:
        # the widget keeps its own square size and centres within its slot.
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_visible(False)

    def set_size(self, size: int) -> None:
        self._size = max(1, size)
        self.queue_resize()

    def set_paintable(self, paintable: Gdk.Paintable | None) -> None:
        self._paintable = paintable
        self.set_visible(paintable is not None)
        self.queue_draw()

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        return (self._size, self._size, -1, -1)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        paintable = self._paintable
        width = float(self.get_width())
        height = float(self.get_height())
        if paintable is None or width <= 0 or height <= 0:
            return

        rect = Graphene.Rect()
        rect.init(0.0, 0.0, width, height)
        clip = Gsk.RoundedRect()
        clip.init_from_rect(rect, min(width, height) * 0.16)
        snapshot.push_rounded_clip(clip)

        intrinsic_width = float(paintable.get_intrinsic_width())
        intrinsic_height = float(paintable.get_intrinsic_height())
        if intrinsic_width > 0 and intrinsic_height > 0:
            scale = max(width / intrinsic_width, height / intrinsic_height)
            drawn_width = intrinsic_width * scale
            drawn_height = intrinsic_height * scale
        else:
            drawn_width, drawn_height = width, height
        origin = Graphene.Point()
        origin.init((width - drawn_width) / 2.0, (height - drawn_height) / 2.0)
        snapshot.save()
        snapshot.translate(origin)
        paintable.snapshot(snapshot, drawn_width, drawn_height)
        snapshot.restore()
        snapshot.pop()


_STATE_ICON_PLAYING = "media-playback-pause-symbolic"
_STATE_ICON_PAUSED = "media-playback-start-symbolic"
# Gap between the state marker and the progress bar it sits beside.
_TIMELINE_GAP = 8


def _clock(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class MediaProgress(Gtk.Box):
    """A position snapshot that advances against the local monotonic clock,
    with the play/pause marker sitting at the left of the timeline."""

    def __init__(self, state_px: int = 18) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.add_css_class("salon-media-timeline")
        # The marker shares a row with the bar, so their centres line up;
        # the times row below is inset by the same width to stay under it.
        track = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=_TIMELINE_GAP)
        self.append(track)
        self._state = Gtk.Image.new_from_icon_name(_STATE_ICON_PAUSED)
        self._state.add_css_class("salon-now-playing-state")
        self._state.set_valign(Gtk.Align.CENTER)
        self._state.set_pixel_size(state_px)
        track.append(self._state)
        self._bar = Gtk.ProgressBar()
        self._bar.add_css_class("salon-media-progress")
        self._bar.set_hexpand(True)
        self._bar.set_valign(Gtk.Align.CENTER)
        track.append(self._bar)
        times = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        times.set_margin_start(state_px + _TIMELINE_GAP)
        self._times = times
        self._elapsed = Gtk.Label()
        self._elapsed.set_hexpand(True)
        self._elapsed.set_halign(Gtk.Align.START)
        self._duration = Gtk.Label()
        self._duration.set_halign(Gtk.Align.END)
        times.append(self._elapsed)
        times.append(self._duration)
        self.append(times)
        self._position = -1.0
        self._length = 0.0
        self._playing = False
        self._valid = False
        self._sampled_at = time.monotonic()
        self.set_visible(False)
        GLib.timeout_add(_TICK_MS, self._tick)

    def set_state_size(self, state_px: int) -> None:
        self._state.set_pixel_size(state_px)
        self._times.set_margin_start(state_px + _TIMELINE_GAP)

    def set_snapshot(self, position_us: int, length_us: int, playing: bool) -> None:
        self._position = position_us / 1_000_000
        self._length = length_us / 1_000_000
        self._playing = playing
        self._sampled_at = time.monotonic()
        self._valid = self._position >= 0 and self._length > 0
        self._state.set_from_icon_name(_STATE_ICON_PLAYING if playing else _STATE_ICON_PAUSED)
        if playing:
            self._state.add_css_class("playing")
        else:
            self._state.remove_css_class("playing")
        self._bar.set_visible(self._valid)
        self._times.set_visible(self._valid)
        # Keep the row (and its marker) whenever anything is playing, so a
        # live stream with no timeline to draw still shows its state.
        self.set_visible(self._valid or playing)
        if self._valid:
            self._draw(self._sampled_at)

    def _tick(self) -> bool:
        if self.get_parent() is None:
            return GLib.SOURCE_REMOVE
        if self._valid and self.get_visible():
            self._draw(time.monotonic())
        return GLib.SOURCE_CONTINUE

    def _draw(self, now: float) -> None:
        position = self._position
        if self._playing:
            position += now - self._sampled_at
        position = min(self._length, max(0.0, position))
        self._bar.set_fraction(position / self._length)
        self._elapsed.set_label(_clock(position))
        self._duration.set_label(_clock(self._length))


def source_button(
    player: Player,
    on_activate: Callable[[str], None],
    *,
    artwork: Gdk.Paintable | None = None,
    art_px: int = 34,
) -> Gtk.Button:
    """One secondary media source, including its independent timeline.

    Same shape as the primary readout: the cover art (when the source
    published one) beside the labels, and the timeline — with its play/pause
    marker at the left — spanning the full width underneath.
    """
    playing = player.status == PLAYING
    button = Gtk.Button()
    button.add_css_class("salon-now-playing-source")
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if artwork is not None:
        cover = SquareCover()
        cover.set_size(art_px)
        cover.set_paintable(artwork)
        row.append(cover)
    copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    copy.set_hexpand(True)
    copy.set_valign(Gtk.Align.CENTER)
    title_text, detail = describe(player, include_status=False)
    title = Gtk.Label(label=title_text)
    title.add_css_class("salon-now-playing-title")
    title.set_halign(Gtk.Align.START)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    identity = Gtk.Label(label=detail)
    identity.add_css_class("salon-now-playing-detail")
    identity.set_ellipsize(Pango.EllipsizeMode.END)
    identity.set_halign(Gtk.Align.START)
    copy.append(title)
    copy.append(identity)
    row.append(copy)
    timeline = MediaProgress(state_px=max(12, round(art_px * 0.4)))
    timeline.set_snapshot(player.position_us, player.length_us, playing)
    outer.append(row)
    outer.append(timeline)
    button.set_child(outer)
    button.connect("clicked", lambda _button: on_activate(player.bus_name))
    return button

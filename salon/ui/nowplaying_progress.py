# SPDX-License-Identifier: GPL-3.0-or-later
"""Truthful, locally advancing MPRIS timelines for the Salon sidebar."""

from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from salon.core.nowplaying import PLAYING, Player  # noqa: E402

_TICK_MS = 250


def _clock(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class MediaProgress(Gtk.Box):
    """A position snapshot that advances against the local monotonic clock."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.add_css_class("salon-media-timeline")
        self._bar = Gtk.ProgressBar()
        self._bar.add_css_class("salon-media-progress")
        self.append(self._bar)
        times = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
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
        self._sampled_at = time.monotonic()
        self.set_visible(False)
        GLib.timeout_add(_TICK_MS, self._tick)

    def set_snapshot(self, position_us: int, length_us: int, playing: bool) -> None:
        self._position = position_us / 1_000_000
        self._length = length_us / 1_000_000
        self._playing = playing
        self._sampled_at = time.monotonic()
        valid = self._position >= 0 and self._length > 0
        self.set_visible(valid)
        if valid:
            self._draw(self._sampled_at)

    def _tick(self) -> bool:
        if self.get_parent() is None:
            return GLib.SOURCE_REMOVE
        if self.get_visible():
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


def source_button(player: Player, on_activate: Callable[[str], None]) -> Gtk.Button:
    """One secondary media source, including its independent timeline."""
    button = Gtk.Button()
    button.add_css_class("salon-now-playing-source")
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    glyph = Gtk.Image.new_from_icon_name(
        "media-playback-pause-symbolic"
        if player.status == PLAYING
        else "media-playback-start-symbolic"
    )
    row.append(glyph)
    copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    copy.set_hexpand(True)
    title = Gtk.Label(label=player.title or "Now playing")
    title.add_css_class("salon-now-playing-title")
    title.set_halign(Gtk.Align.START)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    identity = Gtk.Label(label=player.identity or "Media")
    identity.add_css_class("salon-now-playing-detail")
    identity.set_halign(Gtk.Align.START)
    timeline = MediaProgress()
    timeline.set_snapshot(player.position_us, player.length_us, player.status == PLAYING)
    copy.append(title)
    copy.append(identity)
    copy.append(timeline)
    row.append(copy)
    button.set_child(row)
    button.connect("clicked", lambda _button: on_activate(player.bus_name))
    return button

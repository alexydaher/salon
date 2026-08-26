# SPDX-License-Identifier: GPL-3.0-or-later
"""Transient volume/mute overlay (§8): appears on VOLUME_UP/DOWN/MUTE,
fades after 1.5s. Sized from the du scale — a desktop-sized volume popup is
unreadable from a sofa.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from salon.ui import motion  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402

_VISIBLE_SECONDS = 1.5
_FADE_MS = 220


class VolumeOsd(Gtk.Box):
    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("salon-osd")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)
        self.set_opacity(0.0)
        self.set_can_target(False)

        self._icon = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
        self.append(self._icon)

        self._bar = Gtk.ProgressBar()
        self._bar.set_valign(Gtk.Align.CENTER)
        self.append(self._bar)

        target = Adw.CallbackAnimationTarget.new(self.set_opacity)
        self._fade = Adw.TimedAnimation.new(self, 1.0, 0.0, _FADE_MS, target)
        self._fade.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self._hide_timeout_id: int | None = None

        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(20.0))
        self.set_margin_bottom(scale.safe_margin_px)
        self._icon.set_pixel_size(scale.px(40.0))
        self._bar.set_size_request(scale.px(360.0), scale.px(8.0))

    def show_volume(self, volume: float, muted: bool) -> None:
        self._icon.set_from_icon_name(
            "audio-volume-muted-symbolic" if muted else "audio-volume-high-symbolic"
        )
        self._bar.set_fraction(0.0 if muted else min(1.0, max(0.0, volume)))
        self._present()

    def _present(self) -> None:
        self._fade.pause()
        self.set_opacity(1.0)
        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
        self._hide_timeout_id = GLib.timeout_add(int(_VISIBLE_SECONDS * 1000), self._start_fade)

    def _start_fade(self) -> bool:
        self._hide_timeout_id = None
        self._fade.set_duration(motion.duration_ms(_FADE_MS))
        self._fade.play()
        return GLib.SOURCE_REMOVE

# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact now-playing status centred in the home screen's top bar."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk, Pango  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402


class _CircularCover(Gtk.Widget):
    """A fixed-size, centre-cropped paintable that cannot resize its card."""

    def __init__(self) -> None:
        super().__init__()
        self._paintable: Gdk.Paintable | None = None
        self._size = 1
        self.set_visible(False)

    def set_size(self, size: int) -> None:
        self._size = max(1, size)
        self.queue_resize()

    def set_paintable(self, paintable: Gdk.Paintable | None) -> None:
        self._paintable = paintable
        self.set_visible(paintable is not None)
        self.queue_draw()

    def do_measure(
        self, orientation: Gtk.Orientation, for_size: int
    ) -> tuple[int, int, int, int]:
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
        clip.init_from_rect(rect, min(width, height) / 2.0)
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


class NowPlayingStatus(Gtk.Box):
    def __init__(self, scale: Scale, on_activate: Callable[[], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("salon-now-playing")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.START)
        self.set_visible(False)
        # Still a STATUS rather than a BUTTON, and the click is layered on
        # top of that. The role is what makes a screen reader announce a
        # track change at all, the widget never takes Salon's cursor — the
        # focus model owns that — and the same play/pause is on a button on
        # every other input. Claiming to be a button would trade a live
        # announcement for an activation nothing can reach.
        self.set_accessible_role(Gtk.AccessibleRole.STATUS)
        self._on_activate = on_activate
        # Off unless there is something for a click to do: this is an
        # overlay child sitting over the top of the scrolling rows, and one
        # that takes pointer events it has no use for is one that eats the
        # presses meant for the tile underneath.
        self.set_can_target(on_activate is not None)
        if on_activate is not None:
            self.add_css_class("salon-now-playing-active")
            self.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
            click = Gtk.GestureClick()
            click.connect("released", self._on_click)
            self.add_controller(click)

        # The cover occupies the exact same slot as the transport glyph.
        # Its intrinsic dimensions therefore cannot make this pill larger.
        self._art = _CircularCover()
        self.append(self._art)
        self._icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        self.append(self._icon)
        labels = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(labels)
        self._title = Gtk.Label()
        self._title.add_css_class("salon-now-playing-title")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        labels.append(self._title)
        self._separator = Gtk.Label(label="·")
        self._separator.add_css_class("salon-now-playing-detail")
        labels.append(self._separator)
        self._detail = Gtk.Label()
        self._detail.add_css_class("salon-now-playing-detail")
        self._detail.set_halign(Gtk.Align.START)
        self._detail.set_ellipsize(Pango.EllipsizeMode.END)
        labels.append(self._detail)
        self._labels = labels
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(12.0))
        self._labels.set_spacing(scale.px(8.0))
        icon_size = scale.px(28.0)
        self._art.set_size(icon_size)
        self._icon.set_pixel_size(icon_size)
        self.set_size_request(scale.px(300.0), -1)
        self.set_margin_top(max(0, scale.safe_margin_px - scale.px(24.0)))

    def set_track(self, title: str, detail: str, *, playing: bool) -> None:
        state = "Playing" if playing else "Paused"
        icon_name = (
            "media-playback-pause-symbolic"
            if playing
            else "media-playback-start-symbolic"
        )
        self._icon.set_from_icon_name(icon_name)
        self._title.set_label(title)
        self._detail.set_label(detail)
        self._separator.set_visible(bool(detail))
        self._detail.set_visible(bool(detail))
        phrase = f"{state} {title}"
        if detail:
            phrase += f", {detail}"
        self.update_property([Gtk.AccessibleProperty.LABEL], [phrase])
        self.set_visible(True)

    def set_artwork(self, artwork: Gdk.Paintable | None) -> None:
        self._art.set_paintable(artwork)
        self._icon.set_visible(artwork is None)

    def clear(self) -> None:
        self.set_artwork(None)
        self.set_visible(False)

    def _on_click(
        self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float
    ) -> None:
        """A press on the readout toggles the player it is describing.

        On release rather than on press, and only the first of a double:
        the second click of an accidental double would otherwise pause and
        resume, which looks exactly like nothing happening.
        """
        if n_press != 1 or self._on_activate is None:
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._on_activate()

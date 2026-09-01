# SPDX-License-Identifier: GPL-3.0-or-later
"""Font-independent PlayStation and Xbox button artwork."""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Graphene, Gsk, Gtk, Pango  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402


@dataclass(frozen=True, slots=True)
class ControllerGlyph:
    """A vector controller mark plus the text to use if it cannot render."""

    name: str
    fallback: str


def _point(x: float, y: float) -> Graphene.Point:
    point = Graphene.Point()
    point.init(x, y)
    return point


def _rect(x: float, y: float, width: float, height: float) -> Graphene.Rect:
    rect = Graphene.Rect()
    rect.init(x, y, width, height)
    return rect


class ControllerGlyphWidget(Gtk.Widget):
    """A tiny vector mark that follows the legend's foreground colour."""

    _SUPPORTED = {
        "playstation-circle",
        "playstation-create",
        "playstation-cross",
        "playstation-options",
        "playstation-square",
        "playstation-triangle",
        "xbox-a",
        "xbox-b",
        "xbox-menu",
        "xbox-view",
        "xbox-x",
        "xbox-y",
    }

    @classmethod
    def supports(cls, name: str) -> bool:
        return name in cls._SUPPORTED

    def __init__(self, name: str, scale: Scale) -> None:
        super().__init__()
        self._name = name
        self._size = scale.px(24.0)

    def do_measure(
        self, _orientation: Gtk.Orientation, _for_size: int
    ) -> tuple[int, int, int, int]:
        return self._size, self._size, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width, height = self.get_width(), self.get_height()
        size = float(min(width, height))
        cx, cy = width / 2.0, height / 2.0
        radius = size * 0.34
        builder = Gsk.PathBuilder.new()
        name = self._name

        if name == "playstation-circle":
            builder.add_circle(_point(cx, cy), radius)
        elif name == "playstation-square":
            side = radius * 1.72
            builder.add_rect(_rect(cx - side / 2.0, cy - side / 2.0, side, side))
        elif name == "playstation-cross":
            arm = radius * 0.72
            self._line(builder, cx - arm, cy - arm, cx + arm, cy + arm)
            self._line(builder, cx + arm, cy - arm, cx - arm, cy + arm)
        elif name == "playstation-triangle":
            builder.move_to(cx, cy - radius)
            builder.line_to(cx + radius * 0.92, cy + radius * 0.72)
            builder.line_to(cx - radius * 0.92, cy + radius * 0.72)
            builder.close()
        elif name in ("playstation-options", "xbox-menu"):
            self._menu(builder, cx, cy, radius)
        elif name == "playstation-create":
            self._create(builder, cx, cy, radius)
        elif name == "xbox-view":
            self._view(builder, cx, cy, radius)
        elif name.startswith("xbox-") and name[-1:] in "abxy":
            builder.add_circle(_point(cx, cy), radius)

        path = builder.to_path()
        if path is not None:
            stroke = Gsk.Stroke.new(max(1.5, size * 0.085))
            stroke.set_line_cap(Gsk.LineCap.ROUND)
            stroke.set_line_join(Gsk.LineJoin.ROUND)
            snapshot.append_stroke(path, stroke, self.get_color())
        if name.startswith("xbox-") and name[-1:] in "abxy":
            self._letter(snapshot, name[-1].upper(), size)

    @staticmethod
    def _line(
        builder: Gsk.PathBuilder, x1: float, y1: float, x2: float, y2: float
    ) -> None:
        builder.move_to(x1, y1)
        builder.line_to(x2, y2)

    @classmethod
    def _menu(cls, builder: Gsk.PathBuilder, cx: float, cy: float, radius: float) -> None:
        half = radius * 0.82
        for offset in (-0.48, 0.0, 0.48):
            y = cy + radius * offset
            cls._line(builder, cx - half, y, cx + half, y)

    @classmethod
    def _create(cls, builder: Gsk.PathBuilder, cx: float, cy: float, radius: float) -> None:
        for y in (-0.55, 0.0, 0.55):
            cls._line(
                builder,
                cx - radius * 0.72,
                cy + radius * y,
                cx + radius * (0.18 if y else 0.58),
                cy + radius * y,
            )

    @staticmethod
    def _view(builder: Gsk.PathBuilder, cx: float, cy: float, radius: float) -> None:
        side = radius * 1.18
        shift = radius * 0.34
        builder.add_rect(
            _rect(cx - side / 2.0 - shift, cy - side / 2.0 + shift, side, side)
        )
        builder.add_rect(
            _rect(cx - side / 2.0 + shift, cy - side / 2.0 - shift, side, side)
        )

    def _letter(self, snapshot: Gtk.Snapshot, letter: str, size: float) -> None:
        layout = self.create_pango_layout(letter)
        font = Pango.FontDescription()
        font.set_family("Sans")
        font.set_weight(Pango.Weight.BOLD)
        font.set_absolute_size(size * 0.47 * Pango.SCALE)
        layout.set_font_description(font)
        text_width, text_height = layout.get_pixel_size()
        snapshot.save()
        snapshot.translate(
            _point((self.get_width() - text_width) / 2.0, (self.get_height() - text_height) / 2.0)
        )
        snapshot.append_layout(layout, self.get_color())
        snapshot.restore()

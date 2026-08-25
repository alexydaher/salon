# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Home row widgets and launch classification."""

from salon.ui.home_shared import Gtk, LaunchKind, Tile, TileMetrics, TileWidget
from salon.ui.home_spring import _AxisSpring


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
    """Whether a launch hands control to a browser window outside Salon."""
    if tile.launch.kind is LaunchKind.URL:
        return True
    return tile.launch.kind is LaunchKind.DESKTOP and tile.launch.target == "com.google.Chrome"


__all__ = [name for name in globals() if not name.startswith("__")]

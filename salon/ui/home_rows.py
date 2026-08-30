# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Home row widgets and launch classification."""

from salon.ui.home_shared import Gtk, LaunchKind, Tile, TileMetrics, TileWidget
from salon.ui.home_spring import _AxisSpring
from salon.ui.home_viewport import _RowViewport


class _RowWidgets:
    """The widgets and geometry for one catalogue row."""

    def __init__(
        self,
        heading: Gtk.Label,
        viewport: _RowViewport,
        tiles_box: Gtk.Fixed,
        tiles: list[TileWidget],
        metrics: TileMetrics,
        fade: float = 0.0,
    ) -> None:
        self.heading = heading
        self.viewport = viewport
        self.tiles_box = tiles_box
        self.tiles = tiles
        self.metrics = metrics
        self.fade = fade
        # The window's width, not the viewport's: see `_RowViewport`.
        self.visible_width = 0.0
        # The column this row is parked on, which is *its own* and not the
        # cursor's. Every row used to be scrolled to the column the focus
        # model carried, so a row with the cursor nowhere near it slid
        # sideways whenever a neighbour was walked along — see
        # `home_row_landing`. Re-applied on every layout pass, so a resize
        # or a scale change re-clamps each row where it stood instead of
        # snapping the lot back to the left.
        self.column = 0
        # Per frame, not per settle: the fade is a function of how far the
        # row has actually travelled, and reading the target instead would
        # snap it to full strength while the tiles were still moving. The
        # vertical band does the same thing through the same hook.
        self.scroller = _AxisSpring(
            viewport, tiles_box, vertical=False, on_value=self.update_fades
        )

    def update_fades(self, offset: float | None = None) -> None:
        """Fade whichever end of this row has tiles hanging past it.

        Zero at an end with nothing beyond it, so a row that fits is not
        softened at all and the first tile of an unscrolled row keeps its
        full contrast — the same rule the band applies vertically.
        """
        width = self.visible_width
        if width <= 0:
            return
        if offset is None:
            offset = self.scroller.value
        # In viewport coordinates: a tile's *card* sits one bleed to the
        # right of the tiles box's own origin.
        left_edge = offset + self.metrics.bleed
        right_edge = left_edge + self.content_width
        self.viewport.set_fades(
            min(self.fade, max(0.0, -left_edge)),
            min(self.fade, max(0.0, right_edge - width)),
            width,
        )

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

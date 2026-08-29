# SPDX-License-Identifier: GPL-3.0-or-later
"""The tile being edited, drawn as the tile it will be.

The editor sets artwork, an accent colour and a shape, and showed none of
them: the whole screen was `Name / Movie Night`, `Accent colour / #D9584B`,
`Artwork path or URL / …`. Choosing a colour by typing six hex digits on an
on-screen keyboard and then leaving Settings to find out what it looks like
is the same problem live preview was built to solve on the home screen, on
the screen that needs it more.

This is the real `TileWidget` with the real artwork pipeline behind it, so
what it shows is what the home screen will draw — the same argument as
`screen_preview.py`: nothing here is a mock-up.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.core.model import Tile  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.context import ResolveArtwork  # noqa: E402
from salon.ui.settings.settings_row import SettingsRow  # noqa: E402
from salon.ui.tile import TileWidget  # noqa: E402
from salon.ui.tile_geometry import metrics_for  # noqa: E402

# Smaller than the home screen's own default, because this sits in a column
# beside the rows that change it rather than in a band of its own.
_PREVIEW_SCALE = 0.8


class TilePreviewRow(SettingsRow):
    """A row that is a tile. Unselectable — it is the subject, not a control."""

    def __init__(
        self, tile: Tile, resolve: ResolveArtwork, aspect: str, scale: Scale
    ) -> None:
        super().__init__("")
        self.add_css_class("preview-tile")
        self.set_can_target(False)
        self.set_focusable(False)
        self._tile = tile
        self._resolve = resolve
        self._aspect = aspect
        self._widget: TileWidget | None = None
        self._holder = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._holder.set_halign(Gtk.Align.CENTER)
        self.set_child(self._holder)
        self.set_scale(scale)

    @property
    def selectable(self) -> bool:
        return False

    @property
    def actionable(self) -> bool:
        return False

    def set_scale(self, scale: Scale) -> None:
        """Rebuilt rather than rescaled.

        `TileWidget` takes its metrics at construction and the panel is
        rebuilt on every edit anyway, so keeping one alive across a scale
        change would be bookkeeping for a case that cannot arise.

        It still chains: `SettingsRow.set_scale` is what caps the row's
        content width, and skipping it left this one row uncapped and so
        the full width of the screen. Its centred tile then sat 340px to
        the right of the centre of the rows describing it.
        """
        super().set_scale(scale)
        metrics = metrics_for(scale, self._aspect, size_scale=_PREVIEW_SCALE)
        if self._widget is not None:
            self._holder.remove(self._widget)
        artwork = self._resolve(self._tile, icon_size=round(metrics.height * 0.5))
        self._widget = TileWidget(
            self._tile, artwork, metrics, scale, animations_enabled=False
        )
        # Focused, because that is the state the accent colour and the glow
        # are actually *for*: an unfocused preview would show none of what
        # the row above it is choosing. `animations_enabled=False` makes
        # that jump straight to the endpoint rather than animate on build.
        self._widget.set_focused(True)
        self._holder.append(self._widget)
        self.set_size_request(-1, metrics.height + metrics.bleed * 2)

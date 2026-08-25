# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Home row widgets and initial catalogue."""

from salon.ui.home_shared import (
    Gtk,
    LaunchKind,
    LaunchSpec,
    Row,
    Tile,
    TileMetrics,
    TileWidget,
)
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
    """Whether launching this tile hands control to a browser window we
    can't reach directly — the case where the gamepad should drive the
    system pointer instead of tile navigation."""
    if tile.launch.kind is LaunchKind.URL:
        return True
    return tile.launch.kind is LaunchKind.DESKTOP and tile.launch.target == "com.google.Chrome"


def _seed_rows() -> list[Row]:
    """Written to ~/.config/salon/tiles.json the first time Salon runs and
    finds no config there. Hand-editing the file is always possible and
    never required — this just gives a fresh install something real to look
    at instead of an empty screen."""
    return [
        Row(
            id="apps",
            title="Apps",
            provider_id="static",
            tiles=[
                Tile(
                    id="files",
                    title="Files",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.Nautilus"),
                    artwork=None,
                    icon_name="org.gnome.Nautilus",
                    accent=None,
                ),
                Tile(
                    id="text-editor",
                    title="Text Editor",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.TextEditor"),
                    artwork=None,
                    icon_name="org.gnome.TextEditor",
                    accent=None,
                ),
                Tile(
                    id="calculator",
                    title="Calculator",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.Calculator"),
                    artwork=None,
                    icon_name="org.gnome.Calculator",
                    accent=None,
                ),
                Tile(
                    id="chrome",
                    title="Chrome",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="com.google.Chrome"),
                    artwork=None,
                    icon_name="com.google.Chrome",
                    accent=None,
                ),
                Tile(
                    id="settings",
                    title="Settings",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.BUILTIN, target="settings"),
                    artwork=None,
                    icon_name="preferences-system-symbolic",
                    accent=None,
                ),
            ],
        ),
        Row(
            id="streaming",
            title="Streaming",
            provider_id="static",
            tiles=[
                Tile(
                    id="netflix",
                    title="Netflix",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.netflix.com",
                        browser_profile="netflix",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent="#E50914",
                ),
                Tile(
                    id="prime-video",
                    title="Prime Video",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.primevideo.com",
                        browser_profile="prime-video",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent="#00A8E1",
                ),
                Tile(
                    id="geforce-now",
                    title="GeForce NOW",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.FLATPAK, target="com.nvidia.geforcenow"),
                    artwork=None,
                    icon_name="com.nvidia.geforcenow",
                    accent="#76B900",
                ),
            ],
        ),
        Row(
            id="web",
            title="Web",
            provider_id="static",
            tiles=[
                Tile(
                    id="gnome-org",
                    title="GNOME.org",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.gnome.org",
                        browser_profile="gnome-org",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent=None,
                ),
            ],
        ),
    ]


__all__ = [name for name in globals() if not name.startswith("__")]

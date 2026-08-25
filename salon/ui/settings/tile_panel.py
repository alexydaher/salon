# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Focused catalogue-editing panel builder."""
from __future__ import annotations

from salon.core import editing
from salon.core.model import LaunchKind, Tile
from salon.services.artwork import artwork_drop_dir
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel
from salon.ui.settings.widgets import (
    ActionRow,
    ChoiceRow,
    InfoRow,
    SettingsRow,
    TextRow,
    ToggleRow,
)

_ASPECTS = [("wide", "Wide"), ("square", "Square"), ("poster", "Poster")]
_KINDS = [
    (LaunchKind.DESKTOP.value, "Installed app"),
    (LaunchKind.URL.value, "Web address"),
    (LaunchKind.FLATPAK.value, "Flatpak"),
    (LaunchKind.COMMAND.value, "Command"),
]
from salon.ui.settings.tile_details import (  # noqa: E402
    _delete_tile,
    _edit_accent,
    _edit_artwork,
    _edit_subtitle,
    _edit_target,
    _edit_title,
    _move_tile,
    _move_to_row,
    _set_fullscreen,
    _set_kind,
    _set_spatial_nav,
    _target_label,
)


def tile_panel(context: SettingsContext, row_id: str, tile_id: str) -> Panel:
    def build() -> list[SettingsRow]:
        tile = editing.find_tile(context.config, row_id, tile_id)
        if tile is None:
            return [InfoRow("This tile no longer exists", "")]

        rows: list[SettingsRow] = [
            TextRow("Name", lambda: tile.title, lambda: _edit_title(context, row_id, tile_id)),
            TextRow(
                "Subtitle",
                lambda: tile.subtitle or "",
                lambda: _edit_subtitle(context, row_id, tile_id),
            ),
            ChoiceRow(
                "Type",
                _KINDS,
                lambda: tile.launch.kind.value,
                lambda value: _set_kind(context, row_id, tile_id, value),
            ),
            TextRow(
                _target_label(tile),
                lambda: tile.launch.target,
                lambda: _edit_target(context, row_id, tile_id),
            ),
            TextRow(
                "Accent colour",
                lambda: tile.accent or "",
                lambda: _edit_accent(context, row_id, tile_id),
                placeholder="From artwork",
            ),
            InfoRow(
                "Artwork",
                "Set" if tile.artwork else "Drop folder",
                detail=f"Drop an image at {artwork_drop_dir()}/{tile.id}.png",
            ),
            TextRow(
                "Artwork path or URL",
                lambda: tile.artwork or "",
                lambda: _edit_artwork(context, row_id, tile_id),
                placeholder="Not set",
            ),
        ]
        if tile.launch.kind is LaunchKind.URL:
            rows.append(
                ToggleRow(
                    "Open fullscreen",
                    lambda: tile.launch.fullscreen,
                    lambda value: _set_fullscreen(context, row_id, tile_id, value),
                    detail="Starts the browser window with no chrome around the page.",
                )
            )
            rows.append(
                ToggleRow(
                    "Spatial navigation",
                    lambda: tile.launch.spatial_nav,
                    lambda value: _set_spatial_nav(context, row_id, tile_id, value),
                    detail="Arrow keys move to the nearest element. Off for sites it breaks.",
                )
            )
        rows += [
            ActionRow("Move left", lambda: _move_tile(context, row_id, tile_id, -1), value="◀"),
            ActionRow("Move right", lambda: _move_tile(context, row_id, tile_id, 1), value="▶"),
            ActionRow("Move to another row", lambda: _move_to_row(context, row_id, tile_id)),
            ActionRow(
                "Delete tile",
                lambda: _delete_tile(context, row_id, tile_id),
                danger=True,
            ),
        ]
        return rows

    return Panel(title="Tile", build=build)

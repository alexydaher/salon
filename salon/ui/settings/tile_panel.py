# SPDX-License-Identifier: GPL-3.0-or-later
"""One tile's editor: the tile itself, then everything about it.

Three things changed here at once, and they are the same thing.

**It says which tile.** The title was the word "Tile" and the breadcrumb
was `Tiles › Row › Tile` — three levels of navigation that named nothing
you had navigated to.

**It shows the tile.** Artwork, accent and shape were set by typing and
judged by leaving. The preview at the top is the real `TileWidget`.

**Position replaced three mechanisms.** "Move left", "Move right" and the
row panel's two-step "Reorder tiles" were three ways to do one thing, none
of them direct. A tile's place in its row is now a value like any other,
picked from a list with the current one ticked — which is the idiom every
other choice in Settings already uses.
"""

from __future__ import annotations

from salon.core import editing, tile_editing
from salon.core.model import LaunchKind
from salon.ui.settings.context import Panel, SettingsContext
from salon.ui.settings.tile_details import (
    KINDS,
    delete_tile,
    edit_subtitle,
    edit_target,
    edit_title,
    move_to_row,
    set_kind,
    target_label,
)
from salon.ui.settings.tile_looks import accent_row, artwork_rows, custom_accent_row
from salon.ui.settings.tile_preview import TilePreviewRow
from salon.ui.settings.widgets import (
    ActionRow,
    ChoiceRow,
    GroupRow,
    InfoRow,
    SettingsRow,
    TextRow,
    ToggleRow,
    opens_panel,
)


def tile_panel(context: SettingsContext, row_id: str, tile_id: str) -> Panel:
    def title() -> str:
        tile = editing.find_tile(context.config, row_id, tile_id)
        return tile.title if tile is not None else "Tile"

    def build() -> list[SettingsRow]:
        tile = editing.find_tile(context.config, row_id, tile_id)
        row = editing.find_row(context.config, row_id)
        if tile is None or row is None:
            return [InfoRow("This tile no longer exists", "")]

        rows: list[SettingsRow] = [
            TilePreviewRow(tile, context.resolve_artwork, row.tile_aspect, context.scale()),
            GroupRow("Name"),
            TextRow("Title", lambda: tile.title, lambda: edit_title(context, row_id, tile_id)),
            TextRow(
                "Subtitle",
                lambda: tile.subtitle or "",
                lambda: edit_subtitle(context, row_id, tile_id),
                placeholder="None",
                detail="Shown under the tile everywhere except the home screen",
            ),
            GroupRow("What it opens"),
            ChoiceRow(
                "Type",
                KINDS,
                lambda: tile.launch.kind.value,
                lambda value: set_kind(context, row_id, tile_id, value),
            ),
            TextRow(
                target_label(tile),
                lambda: tile.launch.target,
                lambda: edit_target(context, row_id, tile_id),
            ),
        ]
        if tile.launch.kind is LaunchKind.URL:
            rows += [
                ToggleRow(
                    "Open fullscreen",
                    lambda: tile.launch.fullscreen,
                    lambda value: _set_fullscreen(context, row_id, tile_id, value),
                    detail="Starts the browser window with no chrome around the page.",
                ),
                ToggleRow(
                    "Spatial navigation",
                    lambda: tile.launch.spatial_nav,
                    lambda value: _set_spatial_nav(context, row_id, tile_id, value),
                    detail="Arrow keys move to the nearest element. Off for sites it breaks.",
                ),
            ]
        rows += [
            GroupRow("How it looks"),
            accent_row(context, row_id, tile_id, tile),
            custom_accent_row(context, row_id, tile_id, tile),
            *artwork_rows(context, row_id, tile_id, tile),
            GroupRow("Where it sits"),
            _position_row(context, row_id, tile_id),
            opens_panel(
                "Move to another row",
                lambda: move_to_row(context, row_id, tile_id),
                detail=f"Currently in {row.title or 'an unlabelled row'}",
            ),
            GroupRow("Remove"),
            _delete_row(context, row_id, tile_id),
        ]
        return rows

    return Panel(title=title(), build=build, live_title=title)


def _position_row(context: SettingsContext, row_id: str, tile_id: str) -> SettingsRow:
    """Where in its row this tile sits, as a value.

    Keyed by index, and applied by stepping — `tile_editing.move_tile` takes
    a delta, and repeating it is both simpler and safer than a second
    absolute-placement function that would have to agree with it.
    """
    row = editing.find_row(context.config, row_id)
    tiles = row.tiles if row is not None else []
    current = next((index for index, tile in enumerate(tiles) if tile.id == tile_id), 0)

    def move(key: str) -> None:
        target = int(key)
        step = 1 if target > current else -1
        for _ in range(abs(target - current)):
            tile_editing.move_tile(context.config, row_id, tile_id, step)
        context.save_config()
        context.rebuild()

    return ChoiceRow(
        "Position in this row",
        [(str(index), f"{index + 1} of {len(tiles)}") for index in range(len(tiles))],
        lambda: str(current),
        move,
        detail="Which tile it sits after, left to right",
    )


def _delete_row(context: SettingsContext, row_id: str, tile_id: str) -> SettingsRow:
    return ActionRow(
        "Delete this tile",
        lambda: delete_tile(context, row_id, tile_id),
        detail="Asks first; the app itself is not touched",
        danger=True,
    )


def _set_fullscreen(context: SettingsContext, row_id: str, tile_id: str, enabled: bool) -> None:
    tile = editing.find_tile(context.config, row_id, tile_id)
    if tile is None:
        return
    tile_editing.set_fullscreen(tile, enabled)
    context.save_config()


def _set_spatial_nav(context: SettingsContext, row_id: str, tile_id: str, enabled: bool) -> None:
    tile = editing.find_tile(context.config, row_id, tile_id)
    if tile is None:
        return
    tile_editing.set_spatial_nav(tile, enabled)
    context.save_config()

# SPDX-License-Identifier: GPL-3.0-or-later
"""Two-step row and tile position pickers for catalogue reordering."""

from salon.core import editing
from salon.ui.settings.context import Panel, SettingsContext
from salon.ui.settings.widgets import ActionRow, InfoRow, SettingsRow


def reorder_rows_panel(context: SettingsContext) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            ActionRow(
                row.title or "Unlabelled row",
                lambda r=row.id: context.push(_row_position_panel(context, r)),
                detail=f"Currently position {index + 1}",
                value="›",
            )
            for index, row in enumerate(context.config.rows)
        ]

    return Panel(title="Reorder rows", build=build)


def _row_position_panel(context: SettingsContext, row_id: str) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            ActionRow(
                f"Position {index + 1}",
                lambda target=index: _move_row_to(context, row_id, target),
                detail=row.title or "Unlabelled row",
            )
            for index, row in enumerate(context.config.rows)
        ]

    return Panel(title="Choose position", build=build)


def _move_row_to(context: SettingsContext, row_id: str, target: int) -> None:
    row = editing.find_row(context.config, row_id)
    if row is None:
        return
    current = context.config.rows.index(row)
    step = 1 if target > current else -1
    for _ in range(abs(target - current)):
        editing.move_row(context.config, row_id, step)
    context.save_config()
    context.toast(f"Row moved to position {target + 1}")
    context.pop()


def reorder_tiles_panel(context: SettingsContext, row_id: str) -> Panel:
    def build() -> list[SettingsRow]:
        row = editing.find_row(context.config, row_id)
        if row is None:
            return [InfoRow("This row no longer exists", "")]
        return [
            ActionRow(
                tile.title,
                lambda t=tile.id: context.push(_tile_position_panel(context, row_id, t)),
                detail=f"Currently position {index + 1}",
                value="›",
            )
            for index, tile in enumerate(row.tiles)
        ]

    return Panel(title="Reorder tiles", build=build)


def _tile_position_panel(context: SettingsContext, row_id: str, tile_id: str) -> Panel:
    def build() -> list[SettingsRow]:
        row = editing.find_row(context.config, row_id)
        if row is None:
            return [InfoRow("This row no longer exists", "")]
        return [
            ActionRow(
                f"Position {index + 1}",
                lambda target=index: _move_tile_to(context, row_id, tile_id, target),
                detail=tile.title,
            )
            for index, tile in enumerate(row.tiles)
        ]

    return Panel(title="Choose position", build=build)


def _move_tile_to(context: SettingsContext, row_id: str, tile_id: str, target: int) -> None:
    row = editing.find_row(context.config, row_id)
    if row is None:
        return
    current = next((index for index, tile in enumerate(row.tiles) if tile.id == tile_id), None)
    if current is None:
        return
    step = 1 if target > current else -1
    for _ in range(abs(target - current)):
        editing.move_tile(context.config, row_id, tile_id, step)
    context.save_config()
    context.toast(f"Tile moved to position {target + 1}")
    context.pop()

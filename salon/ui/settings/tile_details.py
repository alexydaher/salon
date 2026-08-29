# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows and edits behind one tile, shared by the tile and add panels.

`KINDS` and `ASPECTS` live here and only here. They used to be copied into
four files, two of which never read their copy.
"""

from __future__ import annotations

from salon.core import editing
from salon.core.model import LaunchKind, Tile
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel
from salon.ui.settings.tile_edits import edit_field
from salon.ui.settings.widgets import ActionRow, InfoRow, SettingsRow

ASPECTS: list[tuple[str, str]] = [
    ("wide", "Wide"),
    ("square", "Square"),
    ("poster", "Poster"),
]

KINDS: list[tuple[str, str]] = [
    (LaunchKind.DESKTOP.value, "Installed app"),
    (LaunchKind.URL.value, "Web address"),
    (LaunchKind.FLATPAK.value, "Flatpak"),
    (LaunchKind.COMMAND.value, "Command"),
]

def target_label(tile: Tile) -> str:
    """What the launch target is *called* for this kind of tile.

    Deliberately not the same word as the Type row's value: a row labelled
    "Web address" sitting directly under a row whose value read "Web
    address" was two different facts wearing one name.
    """
    return {
        LaunchKind.URL: "Address",
        LaunchKind.DESKTOP: "Application id",
        LaunchKind.FLATPAK: "Flatpak id",
        LaunchKind.COMMAND: "Command line",
    }.get(tile.launch.kind, "Target")


def _tile(context: SettingsContext, row_id: str, tile_id: str) -> Tile | None:
    return editing.find_tile(context.config, row_id, tile_id)


def edit_title(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _tile(context, row_id, tile_id)
    if tile is None:
        return
    edit_field(
        context,
        "Tile name",
        tile.title,
        lambda text: setattr(tile, "title", text),
        allow_empty=False,
    )


def edit_subtitle(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _tile(context, row_id, tile_id)
    if tile is None:
        return
    edit_field(
        context,
        "Subtitle",
        tile.subtitle or "",
        lambda text: setattr(tile, "subtitle", text or None),
    )


def edit_target(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _tile(context, row_id, tile_id)
    if tile is None:
        return
    edit_field(
        context,
        target_label(tile),
        tile.launch.target,
        lambda text: editing.set_launch_target(tile, text),
        allow_empty=False,
    )


def set_kind(context: SettingsContext, row_id: str, tile_id: str, value: str) -> None:
    tile = _tile(context, row_id, tile_id)
    if tile is None:
        return
    editing.set_launch_kind(tile, LaunchKind(value))
    context.save_config()
    context.rebuild()


def move_to_row(context: SettingsContext, row_id: str, tile_id: str) -> None:
    def build() -> list[SettingsRow]:
        others = [row for row in context.config.rows if row.id != row_id]
        if not others:
            return [InfoRow("No other rows", "", detail="Add a row first")]
        return [
            ActionRow(
                row.title or "Unlabelled row",
                lambda r=row.id: _do_move_to_row(context, row_id, tile_id, r),
                detail=f"{len(row.tiles)} tile{'s' if len(row.tiles) != 1 else ''}",
            )
            for row in others
        ]

    context.push(Panel(title="Move to row", build=build))


def _do_move_to_row(
    context: SettingsContext, row_id: str, tile_id: str, target_row_id: str
) -> None:
    if editing.move_tile_to_row(context.config, row_id, tile_id, target_row_id):
        context.save_config()
        context.pop()  # the row picker
        context.pop()  # the tile panel, whose tile now lives elsewhere
        context.toast("Tile moved")


def delete_tile(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _tile(context, row_id, tile_id)
    title = tile.title if tile else "this tile"

    def confirmed() -> None:
        editing.remove_tile(context.config, row_id, tile_id)
        context.save_config()
        context.pop()

    context.push(confirm_panel(context, f"Delete {title}?", "Delete tile", confirmed))


__all__ = [
    "ASPECTS",
    "KINDS",
    "delete_tile",
    "edit_subtitle",
    "edit_target",
    "edit_title",
    "move_to_row",
    "set_kind",
    "target_label",
]

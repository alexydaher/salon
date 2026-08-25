# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused catalogue-editing panel builder."""

from __future__ import annotations

from salon.core import editing
from salon.core.model import LaunchKind, Tile
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel
from salon.ui.settings.widgets import (
    ActionRow,
    InfoRow,
    SettingsRow,
)

_ASPECTS = [("wide", "Wide"), ("square", "Square"), ("poster", "Poster")]
_KINDS = [
    (LaunchKind.DESKTOP.value, "Installed app"),
    (LaunchKind.URL.value, "Web address"),
    (LaunchKind.FLATPAK.value, "Flatpak"),
    (LaunchKind.COMMAND.value, "Command"),
]


def _target_label(tile: Tile) -> str:
    return {
        LaunchKind.URL: "Web address",
        LaunchKind.DESKTOP: "Application id",
        LaunchKind.FLATPAK: "Flatpak id",
        LaunchKind.COMMAND: "Command",
    }.get(tile.launch.kind, "Target")


def _with_tile(context: SettingsContext, row_id: str, tile_id: str) -> Tile | None:
    return editing.find_tile(context.config, row_id, tile_id)


def _edit_title(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None or not value.strip():
            return
        tile.title = value.strip()
        context.save_config()
        context.rebuild()

    context.edit_text("Tile name", tile.title, done)


def _edit_subtitle(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None:
            return
        tile.subtitle = value.strip() or None
        context.save_config()
        context.rebuild()

    context.edit_text("Subtitle", tile.subtitle or "", done)


def _edit_target(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None or not value.strip():
            return
        editing.set_launch_target(tile, value.strip())
        context.save_config()
        context.rebuild()

    context.edit_text(_target_label(tile), tile.launch.target, done)


def _edit_accent(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None:
            return
        text = value.strip()
        if text and not text.startswith("#"):
            text = f"#{text}"
        tile.accent = text or None
        context.save_config()
        context.rebuild()

    context.edit_text("Accent colour, e.g. #E50914", tile.accent or "#", done)


def _edit_artwork(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return

    def done(value: str | None) -> None:
        if value is None:
            return
        tile.artwork = value.strip() or None
        context.save_config()
        context.rebuild()

    context.edit_text("Artwork path or https:// URL", tile.artwork or "", done)


def _set_kind(context: SettingsContext, row_id: str, tile_id: str, value: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return
    editing.set_launch_kind(tile, LaunchKind(value))
    context.save_config()
    context.rebuild()


def _set_fullscreen(context: SettingsContext, row_id: str, tile_id: str, enabled: bool) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return
    editing.set_fullscreen(tile, enabled)
    context.save_config()


def _set_spatial_nav(context: SettingsContext, row_id: str, tile_id: str, enabled: bool) -> None:
    tile = _with_tile(context, row_id, tile_id)
    if tile is None:
        return
    editing.set_spatial_nav(tile, enabled)
    context.save_config()


def _move_tile(context: SettingsContext, row_id: str, tile_id: str, delta: int) -> None:
    if editing.move_tile(context.config, row_id, tile_id, delta):
        context.save_config()
        context.toast("Tile moved")
    else:
        context.toast("Already at the end of the row")


def _move_to_row(context: SettingsContext, row_id: str, tile_id: str) -> None:
    def build() -> list[SettingsRow]:
        others = [row for row in context.config.rows if row.id != row_id]
        if not others:
            return [InfoRow("No other rows", "Add a row first")]
        return [
            ActionRow(
                row.title or "Unlabelled row",
                lambda r=row.id: _do_move_to_row(context, row_id, tile_id, r),
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


def _delete_tile(context: SettingsContext, row_id: str, tile_id: str) -> None:
    tile = _with_tile(context, row_id, tile_id)
    title = tile.title if tile else "this tile"

    def confirmed() -> None:
        editing.remove_tile(context.config, row_id, tile_id)
        context.save_config()
        context.pop()

    context.push(confirm_panel(context, f"Delete {title}?", "Delete tile", confirmed))

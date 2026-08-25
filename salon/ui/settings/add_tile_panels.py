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


def _add_tile_menu(context: SettingsContext, row_id: str) -> None:
    """§6.8: adding a tile offers an installed application, a web address,
    or a custom command."""

    def build() -> list[SettingsRow]:
        return [
            ActionRow(
                "Installed app",
                lambda: context.push(_installed_panel(context, row_id)),
                detail="Pick from everything on this machine",
                value="›",
            ),
            ActionRow(
                "Web address",
                lambda: _add_url(context, row_id),
                detail="Opens in its own browser profile",
            ),
            ActionRow(
                "Command",
                lambda: _add_command(context, row_id),
                detail="Runs an executable directly",
            ),
        ]

    context.push(Panel(title="Add tile", build=build))


def _installed_panel(context: SettingsContext, row_id: str) -> Panel:
    """Populated asynchronously — the desktop-entry scan is far too slow to
    run on the frame clock (§10), so the panel opens saying so and fills in
    when the scan lands."""
    found: list[Tile] = []

    def build() -> list[SettingsRow]:
        if not found:
            context.installed_apps(_on_scanned)
            return [InfoRow("Looking for installed apps…", "")]
        return [
            ActionRow(app.title, lambda a=app: _add_installed(context, row_id, a))
            for app in found
        ]

    def _on_scanned(apps: list[Tile]) -> None:
        if found:
            return
        found.extend(apps)
        context.rebuild()

    return Panel(title="Installed app", build=build)


def _add_installed(context: SettingsContext, row_id: str, app: Tile) -> None:
    created = editing.new_tile(
        context.config,
        row_id,
        title=app.title,
        kind=LaunchKind.DESKTOP,
        target=app.launch.target,
        icon_name=app.icon_name,
    )
    editing.add_tile(context.config, row_id, created)
    context.save_config()
    context.pop()  # the installed-app list
    context.pop()  # the "Add tile" menu
    context.toast(f"Added {created.title}")


def _add_url(context: SettingsContext, row_id: str) -> None:
    def got_title(title: str | None) -> None:
        if title is None or not title.strip():
            return

        def got_url(url: str | None) -> None:
            if url is None or not url.strip():
                return
            target = url.strip()
            if not target.startswith(("http://", "https://")):
                target = f"https://{target}"
            created = editing.new_tile(
                context.config,
                row_id,
                title=title.strip(),
                kind=LaunchKind.URL,
                target=target,
                icon_name="web-browser-symbolic",
            )
            editing.add_tile(context.config, row_id, created)
            context.save_config()
            context.pop()
            context.toast(f"Added {created.title}")

        context.edit_text("Web address", "https://", got_url)

    context.edit_text("Tile name", "", got_title)


def _add_command(context: SettingsContext, row_id: str) -> None:
    def got_title(title: str | None) -> None:
        if title is None or not title.strip():
            return

        def got_command(command: str | None) -> None:
            if command is None or not command.strip():
                return
            created = editing.new_tile(
                context.config,
                row_id,
                title=title.strip(),
                kind=LaunchKind.COMMAND,
                target=command.strip(),
                icon_name="application-x-executable-symbolic",
            )
            editing.add_tile(context.config, row_id, created)
            context.save_config()
            context.pop()
            context.toast(f"Added {created.title}")

        context.edit_text("Command to run", "", got_command)

    context.edit_text("Tile name", "", got_title)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Providers (§6.10).

The point of this panel is accountability. A plugin system whose failure
mode is "your row silently isn't there any more" is worse than no plugin
system, so every provider is listed whether it worked or not, with what it
contributed or why it didn't, and a switch to turn it off.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core.provider import ProviderOutcome  # noqa: E402
from salon.providers.external import provider_dir  # noqa: E402
from salon.providers.registry import ProviderRegistry  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    InfoRow,
    SettingsRow,
    ToggleRow,
)


def providers_panel(
    context: SettingsContext,
    settings: Gio.Settings,
    registry: ProviderRegistry,
    outcomes: Callable[[], tuple[ProviderOutcome, ...]],
    reload_catalog: Callable[[], None],
) -> Panel:
    def build() -> list[SettingsRow]:
        by_id = {outcome.provider_id: outcome for outcome in outcomes()}
        # The two rows a provider can be *enabled* and still not produce.
        # Both were reachable only by editing dconf by hand, which for a
        # setting whose entire purpose is "put my games on the home screen"
        # is the same as not existing.
        rows: list[SettingsRow] = [
            ToggleRow(
                "Show installed games",
                lambda: settings.get_boolean("show-games-row"),
                lambda value: _set_row(context, reload_catalog, settings, "show-games-row", value),
                detail="Steam, Heroic, Lutris and RetroArch, with the cover art they downloaded",
            ),
            ToggleRow(
                "Show every application",
                lambda: settings.get_boolean("show-apps-row"),
                lambda value: _set_row(context, reload_catalog, settings, "show-apps-row", value),
                detail="One row of everything installed. Long — the all-apps grid is easier.",
            ),
        ]
        for provider in registry.all_providers():
            if provider.id not in registry.builtin_ids:
                continue
            outcome = by_id.get(provider.id)
            rows.append(
                ToggleRow(
                    provider.title,
                    lambda pid=provider.id: pid not in registry.disabled(),
                    lambda enabled, pid=provider.id: _set_enabled(
                        context, registry, reload_catalog, pid, enabled
                    ),
                    detail=_describe(outcome),
                )
            )

        rows.append(
            ActionRow(
                "Developer providers",
                lambda: context.push(
                    _developer_providers_panel(context, registry, outcomes, reload_catalog)
                ),
                detail="Local Python extensions that run code on this computer",
                value="›",
            )
        )
        return rows

    return Panel(
        title="Providers",
        build=build,
        panel_id="providers",
        icon_name="application-x-addon-symbolic",
    )


def _developer_providers_panel(
    context: SettingsContext,
    registry: ProviderRegistry,
    outcomes: Callable[[], tuple[ProviderOutcome, ...]],
    reload_catalog: Callable[[], None],
) -> Panel:
    def build() -> list[SettingsRow]:
        by_id = {outcome.provider_id: outcome for outcome in outcomes()}
        rows: list[SettingsRow] = [
            InfoRow(
                "Local code",
                "Use trusted files only",
                detail="Provider files execute with the same access as Salon.",
            )
        ]
        external = [
            provider
            for provider in registry.all_providers()
            if provider.id not in registry.builtin_ids
        ]
        for provider in external:
            rows.append(
                ToggleRow(
                    provider.title,
                    lambda pid=provider.id: pid not in registry.disabled(),
                    lambda enabled, pid=provider.id: _set_enabled(
                        context, registry, reload_catalog, pid, enabled
                    ),
                    detail=_describe(by_id.get(provider.id)),
                )
            )
        known = {provider.id for provider in registry.all_providers()}
        for outcome in outcomes():
            if outcome.provider_id not in known:
                rows.append(InfoRow(outcome.title, "Failed", detail=outcome.failure or ""))
        rows.extend(
            [
                ActionRow(
                    "Reload developer providers",
                    lambda: _reload(context, registry, reload_catalog),
                    detail=f"Re-imports every .py in {provider_dir()}",
                ),
                ActionRow(
                    "Open provider folder",
                    lambda: _open_folder(context),
                    detail="Add only Python provider files you trust",
                ),
            ]
        )
        return rows

    return Panel(title="Developer providers", build=build)


def _set_row(
    context: SettingsContext,
    reload_catalog: Callable[[], None],
    settings: Gio.Settings,
    key: str,
    enabled: bool,
) -> None:
    settings.set_boolean(key, enabled)
    reload_catalog()
    context.rebuild()


def _describe(outcome: ProviderOutcome | None) -> str:
    if outcome is None:
        return "Hasn't run yet"
    if outcome.disabled:
        return "Turned off"
    if outcome.failure is not None:
        return outcome.failure
    if outcome.row_count == 0:
        return "Ran, contributed nothing"
    return f"{outcome.row_count} row{'s' if outcome.row_count != 1 else ''}"


def _set_enabled(
    context: SettingsContext,
    registry: ProviderRegistry,
    reload_catalog: Callable[[], None],
    provider_id: str,
    enabled: bool,
) -> None:
    registry.set_enabled(provider_id, enabled)
    reload_catalog()
    context.rebuild()


def _reload(
    context: SettingsContext, registry: ProviderRegistry, reload_catalog: Callable[[], None]
) -> None:
    registry.reload_external()
    reload_catalog()
    context.toast("Providers reloaded.")
    context.rebuild()


def _open_folder(context: SettingsContext) -> None:
    folder = provider_dir()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(str(folder)).get_uri(), None)
    except GLib.Error:
        context.toast(f"Provider folder: {folder}")

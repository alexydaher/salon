# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Home screen: which rows appear, and why one didn't (§6.10).

Two things were wrong with this as "Providers".

**The name.** A provider is an implementation detail — a thread with a
three-second deadline contributing rows to a catalogue. What the user is
choosing is what appears on the home screen, and the section is now called
that. The diagnostics that gave the panel its name ("Ran, contributed
nothing", import failures, the Python folder) are still here, one press
away, where somebody debugging a plugin will look for them.

**The same row was switched twice.** `show-games-row` and the `games`
provider were separate switches over one row, four lines apart, both
reading Off — and turning on the first while the second was off produced
nothing, with no explanation available anywhere. `_row_switch` makes one
row own both: reading it means "on only if nothing is holding it off", and
setting it clears whichever half was.

The panel is still accountable, which is the point of it: a plugin system
whose failure mode is "your row silently isn't there" is worse than no
plugin system, so every source is listed whether it worked or not.
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
    GroupRow,
    InfoRow,
    SettingsRow,
    ToggleRow,
    opens_panel,
)

# The two providers that also have a GSettings key of their own, and the
# key that gates each. Everything else is switched by the registry alone.
_GATED: dict[str, str] = {"games": "show-games-row", "apps": "show-apps-row"}

_DESCRIPTIONS: dict[str, str] = {
    "games": "Steam, Heroic, Lutris, and RetroArch",
    "apps": "",
    "recents": "",
    "favourites": "",
    "static": "Your custom rows",
}


def providers_panel(
    context: SettingsContext,
    settings: Gio.Settings,
    registry: ProviderRegistry,
    outcomes: Callable[[], tuple[ProviderOutcome, ...]],
    reload_catalog: Callable[[], None],
) -> Panel:
    def apply() -> None:
        reload_catalog()
        context.rebuild()

    def row_switch(provider_id: str, title: str, outcome: ProviderOutcome | None) -> ToggleRow:
        """One switch for one row, whatever is holding it off.

        The gate and the registry are separate storage — one is a boolean
        in GSettings that predates providers, the other is a list of
        disabled ids — but they are not separate *questions*, and the
        screen has no business asking both.
        """
        gate = _GATED.get(provider_id)

        def get() -> bool:
            if gate is not None and not settings.get_boolean(gate):
                return False
            return provider_id not in registry.disabled()

        def set_(enabled: bool) -> None:
            if gate is not None:
                settings.set_boolean(gate, enabled)
            registry.set_enabled(provider_id, enabled)
            apply()

        return ToggleRow(
            title,
            get,
            set_,
            detail=(
                _DESCRIPTIONS[provider_id]
                if provider_id in _DESCRIPTIONS
                else _describe(outcome)
            ),
        )

    def build() -> list[SettingsRow]:
        by_id = {outcome.provider_id: outcome for outcome in outcomes()}
        rows: list[SettingsRow] = [GroupRow("Rows on the home screen")]
        for provider in registry.all_providers():
            if provider.id not in registry.builtin_ids:
                continue
            rows.append(row_switch(provider.id, provider.title, by_id.get(provider.id)))
        rows.append(GroupRow("Advanced"))
        rows.append(
            opens_panel(
                "Developer providers",
                lambda: context.push(
                    _developer_providers_panel(context, registry, outcomes, reload_catalog)
                ),
            )
        )
        return rows

    return Panel(
        title="Home screen",
        build=build,
        panel_id="providers",
        icon_name="view-grid-symbolic",
    )


def _outcome_rows(
    registry: ProviderRegistry, by_id: dict[str, ProviderOutcome]
) -> list[SettingsRow]:
    """What each enabled source actually contributed on the last build.

    Only the ones that ran: an outcome line under a switch that is off says
    "Turned off", which the switch beside it already said.
    """
    rows: list[SettingsRow] = []
    for provider in registry.all_providers():
        outcome = by_id.get(provider.id)
        if outcome is None or outcome.disabled:
            continue
        rows.append(InfoRow(provider.title, _describe(outcome)))
    if not rows:
        rows.append(InfoRow("Nothing has run yet", "", detail="Open the home screen once"))
    return rows


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
            ),
            GroupRow("Diagnostics"),
            *_outcome_rows(registry, by_id),
            GroupRow("Local providers"),
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
                ),
                ActionRow(
                    "Open provider folder",
                    lambda: _open_folder(context),
                ),
            ]
        )
        return rows

    return Panel(title="Developer providers", build=build)


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

# SPDX-License-Identifier: GPL-3.0-or-later
"""Assembles the provider list and turns it into a catalogue.

One place decides what runs: the built-ins, plus whatever the user
dropped in `$XDG_DATA_HOME/salon/providers/`. `HomeView` asks for a
catalogue and gets one back with a list of what each provider did, which is
what Settings → Providers renders — a row that silently didn't appear is the
worst possible outcome of a plugin system, so every provider is accounted
for whether it worked or not.

Disabling is by id in `disabled-providers`, not by deleting the file: a
provider that misbehaves should be switchable off from the sofa.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core.config import Config  # noqa: E402
from salon.core.provider import (  # noqa: E402
    CatalogBuild,
    Provider,
    ProviderContext,
    ProviderOutcome,
    collect,
)
from salon.providers.apps import InstalledAppsProvider  # noqa: E402
from salon.providers.external import LoadError, load_all  # noqa: E402
from salon.providers.favourites import FavouritesProvider  # noqa: E402
from salon.providers.games import GamesProvider  # noqa: E402
from salon.providers.recents import RecentsProvider  # noqa: E402
from salon.providers.static import StaticProvider  # noqa: E402

_DISABLED_KEY = "disabled-providers"


class ProviderRegistry:
    def __init__(self, settings: Gio.Settings) -> None:
        self._settings = settings
        self._builtins: list[Provider] = [
            FavouritesProvider(settings),
            RecentsProvider(settings),
            StaticProvider(),
            GamesProvider(settings),
            InstalledAppsProvider(settings),
        ]
        self._external: list[Provider] = []
        self._load_errors: list[LoadError] = []
        self.reload_external()

    @property
    def builtin_ids(self) -> set[str]:
        return {provider.id for provider in self._builtins}

    def reload_external(self) -> None:
        """Re-scan the provider directory. Import happens here rather than
        per build, because importing a module twice per catalogue refresh
        would re-run its top-level code every time a tile is edited."""
        self._external, self._load_errors = load_all()

    def all_providers(self) -> list[Provider]:
        return [*self._builtins, *self._external]

    def disabled(self) -> set[str]:
        return set(self._settings.get_strv(_DISABLED_KEY))

    def set_enabled(self, provider_id: str, enabled: bool) -> None:
        disabled = self.disabled()
        if enabled:
            disabled.discard(provider_id)
        else:
            disabled.add(provider_id)
        self._settings.set_strv(_DISABLED_KEY, sorted(disabled))

    def build_async(self, config: Config, on_done: Callable[[CatalogBuild], None]) -> None:
        """Build off the main loop and deliver back on it.

        `collect()` waits up to three seconds, and doing that on the main
        thread means one misbehaving provider freezes the whole interface
        for three seconds every time a tile is launched or the config file
        changes (§10: no blocking work on the main loop). The wait belongs
        on a worker; the catalogue arrives a frame or two later, which for a
        healthy set of providers is imperceptible.
        """

        def worker() -> None:
            build = self.build(config)
            GLib.idle_add(lambda: _deliver(on_done, build))

        threading.Thread(target=worker, name="salon-providers", daemon=True).start()

    def build(self, config: Config) -> CatalogBuild:
        disabled = self.disabled()
        active = [p for p in self.all_providers() if p.id not in disabled]
        build = collect(active, ProviderContext(config=config))

        # A module that wouldn't even import never reaches collect(), so its
        # failure has to be folded in here or it would vanish from the list
        # entirely — which is exactly the "why did my row disappear" case
        # this whole layer exists to answer.
        broken = tuple(
            ProviderOutcome(error.provider_id, error.path.name, 0, error.reason)
            for error in self._load_errors
        )
        skipped = tuple(
            ProviderOutcome(p.id, p.title, 0, "Turned off", disabled=True)
            for p in self.all_providers()
            if p.id in disabled
        )
        return CatalogBuild(rows=build.rows, outcomes=(*build.outcomes, *skipped, *broken))


def _deliver(on_done: Callable[[CatalogBuild], None], build: CatalogBuild) -> bool:
    on_done(build)
    return bool(GLib.SOURCE_REMOVE)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Home screen: one switch per row, whatever holds it off.

`show-games-row` and the `games` provider were two independent switches
over one row of the home screen, sitting four lines apart in the same list
and both reading Off. Turning the first on while the second was off
produced nothing, with no explanation available anywhere in the interface.
"""

from __future__ import annotations

import os

# GSettings, in memory and nowhere else. A dconf *write* is a D-Bus call to
# the writer daemon, which resolves the user database from its own
# environment — so a harness that redirects the XDG directories still edits
# the live session while reading its own empty copy back. Assigned rather
# than `setdefault`, and before `gi.repository` is imported, which is when
# the backend is chosen. Enforced by tests/test_settings_isolation.py.
os.environ["GSETTINGS_BACKEND"] = "memory"

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from gi.repository import Gio, Gtk  # noqa: E402

from salon.core.provider import ProviderOutcome  # noqa: E402
from salon.ui.settings.action_rows import ToggleRow  # noqa: E402
from salon.ui.settings.providers import providers_panel  # noqa: E402


class _Provider:
    def __init__(self, provider_id: str, title: str) -> None:
        self.id = provider_id
        self.title = title


class _Registry:
    """Just the four methods the panel consults."""

    def __init__(self) -> None:
        self._providers = [_Provider("games", "Games"), _Provider("recents", "Recents")]
        self._disabled: set[str] = set()

    @property
    def builtin_ids(self) -> set[str]:
        return {p.id for p in self._providers}

    def all_providers(self) -> list[_Provider]:
        return list(self._providers)

    def disabled(self) -> set[str]:
        return set(self._disabled)

    def set_enabled(self, provider_id: str, enabled: bool) -> None:
        self._disabled.discard(provider_id) if enabled else self._disabled.add(provider_id)


def _context() -> object:
    class _Context:
        config = None
        toast = staticmethod(lambda _m: None)
        rebuild = staticmethod(lambda: None)
        push = staticmethod(lambda _p: None)

    return _Context()


def _settings() -> Gio.Settings:
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup("io.github.alexydaher.Salon", True) if source else None
    if schema is None:
        pytest.skip("Salon's compiled schema is not on GSETTINGS_SCHEMA_DIR")
    return Gio.Settings.new_full(schema, None, None)


def _games_row(rows: list[object]) -> ToggleRow:
    matches = [r for r in rows if isinstance(r, ToggleRow) and r.label_text == "Games"]
    assert len(matches) == 1, "one row of the home screen, one switch"
    return matches[0]


def _build() -> tuple[list[object], Gio.Settings, _Registry]:
    Gtk.init()
    settings = _settings()
    settings.reset("show-games-row")
    registry = _Registry()
    outcomes: tuple[ProviderOutcome, ...] = ()
    panel = providers_panel(
        _context(),  # type: ignore[arg-type]
        settings,
        registry,  # type: ignore[arg-type]
        lambda: outcomes,
        lambda: None,
    )
    return panel.build(), settings, registry


def test_a_gated_provider_has_exactly_one_switch() -> None:
    rows, _settings_, _registry = _build()
    assert _games_row(rows) is not None


def test_the_switch_reads_off_when_either_half_is_off() -> None:
    rows, settings, registry = _build()
    settings.set_boolean("show-games-row", True)
    registry.set_enabled("games", False)
    row = _games_row(rows)
    row.refresh()
    assert row.value_text == "Off"

    registry.set_enabled("games", True)
    settings.set_boolean("show-games-row", False)
    row.refresh()
    assert row.value_text == "Off"


def test_switching_it_on_clears_both_halves() -> None:
    """The bug this replaces: the user turns on the switch they can see and
    the row still does not appear, because the other one is still off."""
    rows, settings, registry = _build()
    settings.set_boolean("show-games-row", False)
    registry.set_enabled("games", False)

    _games_row(rows).activate_row()

    assert settings.get_boolean("show-games-row")
    assert "games" not in registry.disabled()
    settings.reset("show-games-row")


def test_an_ungated_provider_still_works_through_the_registry_alone() -> None:
    rows, _settings_, registry = _build()
    recents = next(r for r in rows if isinstance(r, ToggleRow) and r.label_text == "Recents")
    recents.activate_row()
    assert "recents" in registry.disabled()

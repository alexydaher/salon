# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for app handles that disappear before their windows."""

from __future__ import annotations

import pytest

from salon.core.model import LaunchKind, LaunchSpec, Tile
from salon.services import launcher_lifecycle
from salon.services.launcher import LauncherService


def _tile() -> Tile:
    return Tile(
        id="music.desktop",
        title="Music",
        subtitle=None,
        launch=LaunchSpec(LaunchKind.DESKTOP, "music.desktop"),
        artwork=None,
        icon_name=None,
        accent=None,
    )


def test_a_dead_desktop_wrapper_does_not_make_the_app_disappear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LauncherService(object())  # type: ignore[arg-type]
    tile = _tile()
    service._launching_tile = tile  # noqa: SLF001
    service._child_pid = 4242  # noqa: SLF001
    service._awaiting_return = True  # noqa: SLF001
    service._register_current(tile)  # noqa: SLF001

    def gone(_pid: int, _signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(launcher_lifecycle.os, "kill", gone)

    assert service.close_child() is False
    assert service.has_child is True
    assert service.front_child_id == tile.id
    assert [(app.id, app.closeable) for app in service.running_apps] == [(tile.id, False)]

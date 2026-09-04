# SPDX-License-Identifier: GPL-3.0-or-later
"""Every player command the interface names exists on the watcher.

`NowPlayingWatcher` is reached through `self._owner._now_playing`, so a
wrong method name is an attribute lookup that nothing checks: `mypy
--strict` covers `salon/core` and `salon/input` and not `salon/ui`, the
call sites are inside GTK callbacks where an `AttributeError` is printed
and swallowed rather than raised anywhere a test would see it, and the
press that reaches them needs a media key or a CEC remote.

That is exactly how `_skip_track` shipped calling `next()` and
`previous()` against a watcher whose methods are `next_track` and
`previous_track` — every gate green, and the whole Next/Previous feature
dead in both directions the day it was added.

Read out of the source rather than by driving the widgets: these modules
import `salon.config`, which Meson generates, so a test that imported them
would be a test that only runs against a build tree.
"""

from __future__ import annotations

import ast
from pathlib import Path

from salon.services.mpris import NowPlayingWatcher

UI = Path(__file__).resolve().parent.parent / "salon" / "ui"

_WATCHER = "_now_playing"


def _names_used(tree: ast.AST) -> set[str]:
    """Every attribute read off the watcher, directly or through a local.

    Three spellings are in use: `self._owner._now_playing.play_pause()`, a
    `watcher = self._owner._now_playing` bound first, and a bound method
    held before it is called (`skip = watcher.next_track`). The bug this
    guards against was in the second, and matching calls alone would miss
    the third — a name that does not exist fails at the lookup, whether or
    not the parentheses are on the same line.
    """
    aliases = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == _WATCHER
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    used: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        owner = node.value
        on_watcher = (isinstance(owner, ast.Attribute) and owner.attr == _WATCHER) or (
            isinstance(owner, ast.Name) and owner.id in aliases
        )
        if on_watcher:
            used.add(node.attr)
    return used


def test_every_player_command_the_interface_names_exists() -> None:
    available = {name for name in dir(NowPlayingWatcher) if not name.startswith("_")}
    missing: list[str] = []
    for source in sorted(UI.rglob("*.py")):
        for name in sorted(_names_used(ast.parse(source.read_text()))):
            if name not in available:
                missing.append(f"{source.name}: {name}()")
    assert not missing, f"not on NowPlayingWatcher: {', '.join(missing)}"


def test_the_scan_finds_the_calls_it_is_meant_to_guard() -> None:
    """A checker that matches nothing passes for the wrong reason."""
    tree = ast.parse((UI / "home_idle.py").read_text())
    assert {"play_pause", "next_track", "previous_track"} <= _names_used(tree)

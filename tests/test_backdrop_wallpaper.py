# SPDX-License-Identifier: GPL-3.0-or-later
"""Wallpaper policy that does not need a window or renderer."""

import ast
from pathlib import Path

from salon.ui import backdrop_wallpaper as wallpaper


def test_automatic_colours_the_bundled_background() -> None:
    assert wallpaper.resolve_treatment("", "automatic") == "focus"


def test_automatic_preserves_a_custom_pictures_colours() -> None:
    assert wallpaper.resolve_treatment("/Pictures/holiday.jpg", "automatic") == "original"
    assert wallpaper.resolve_treatment("/Pictures", "automatic") == "original"


def test_an_explicit_treatment_applies_to_every_background() -> None:
    for treatment in ("original", "focus", "accent"):
        assert wallpaper.resolve_treatment("", treatment) == treatment
        assert wallpaper.resolve_treatment("/Pictures/holiday.jpg", treatment) == treatment


def test_an_unknown_treatment_falls_back_safely() -> None:
    assert wallpaper.resolve_treatment("/Pictures/holiday.jpg", "sepia") == "original"


def test_the_reduced_resolution_cache_never_contains_the_wallpaper() -> None:
    """The cache is quarter-sized in both axes, so putting the photograph
    back into it would quietly restore the blur this feature removed."""
    path = Path(__file__).resolve().parent.parent / "salon" / "ui" / "backdrop.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def calls(method: str) -> set[str]:
        return {
            node.func.attr
            for node in ast.walk(methods[method])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

    assert "snapshot_ambient" in calls("_refresh_texture")
    assert "snapshot_wallpaper" not in calls("_refresh_texture")
    assert {"snapshot_wallpaper", "snapshot_ambient"} <= calls("do_snapshot")

# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep the crisp cursor tied to the chosen interface accent."""

from __future__ import annotations

import ast
from pathlib import Path


def test_focus_ring_uses_the_interface_accent() -> None:
    path = Path(__file__).resolve().parent.parent / "salon/ui/tile_surface_renderer.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    card_renderer = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_snapshot_edge"
    )
    ring_assignment = next(
        node
        for node in ast.walk(card_renderer)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "ring" for target in node.targets)
    )

    assert isinstance(ring_assignment.value, ast.Call)
    colour = ring_assignment.value.args[0]
    assert isinstance(colour, ast.Call)
    assert isinstance(colour.func, ast.Attribute)
    assert isinstance(colour.func.value, ast.Name)
    assert (colour.func.value.id, colour.func.attr) == ("theme", "accent")


def test_tile_shadow_has_no_accent_glow() -> None:
    path = Path(__file__).resolve().parent.parent / "salon/ui/tile_surface_renderer.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    shadow_renderer = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_snapshot_shadow"
    )

    accent_calls = [
        node
        for node in ast.walk(shadow_renderer)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and (node.func.value.id, node.func.attr) == ("theme", "accent")
    ]
    assert accent_calls == []

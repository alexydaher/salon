# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression checks for dependencies extracted from the former monolithic UI."""

import ast
from pathlib import Path


def test_home_rows_has_its_spring_dependency() -> None:
    path = Path(__file__).resolve().parent.parent / "salon/ui/home_rows.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "salon.ui.home_spring"
        and any(alias.name == "_AxisSpring" for alias in node.names)
        for node in tree.body
    )


def test_only_scale_computes_the_default_safe_area() -> None:
    ui = Path(__file__).resolve().parent.parent / "salon/ui"
    offenders = [
        path.relative_to(ui).as_posix()
        for path in ui.rglob("*.py")
        if path.name != "scale.py" and "SAFE_AREA_DEFAULT_PERCENT" in path.read_text()
    ]
    assert offenders == []


def test_top_bar_horizontal_edges_do_not_animate_an_app_row() -> None:
    path = Path(__file__).resolve().parent.parent / "salon/ui/home_navigation.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_handle_nav_action"
    )
    horizontal_branch = next(
        node
        for node in handler.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and any(
            isinstance(comparator, ast.Tuple)
            and {
                element.attr
                for element in comparator.elts
                if isinstance(element, ast.Attribute)
            }
            == {"LEFT", "RIGHT"}
            for comparator in node.test.comparators
        )
    )
    calls = [
        node.func.attr
        for node in ast.walk(horizontal_branch)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "move" in calls
    assert "_rubber_band" not in calls

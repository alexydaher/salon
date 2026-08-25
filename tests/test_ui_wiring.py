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

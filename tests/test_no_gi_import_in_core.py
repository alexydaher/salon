"""Quality gate: salon/core must stay importable without gi (headless-testable)."""

from __future__ import annotations

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "salon" / "core"


def _imported_top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_core_has_no_gi_imports() -> None:
    offenders = []
    for path in CORE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        if "gi" in _imported_top_level_names(tree):
            offenders.append(path)
    assert not offenders, f"gi imported under salon/core: {offenders}"

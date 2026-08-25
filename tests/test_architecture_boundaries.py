# SPDX-License-Identifier: GPL-3.0-or-later
"""Enforce dependency direction between Salon's architectural layers."""

from __future__ import annotations

import ast
from pathlib import Path

SALON_DIR = Path(__file__).resolve().parent.parent / "salon"


def _salon_imports(path: Path) -> set[str]:
    imports: set[str] = set()
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name.startswith("salon"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("salon"):
                imports.add(node.module)
    return imports


def _forbidden_imports(layer: str, allowed: set[str]) -> list[str]:
    offenders: list[str] = []
    for path in (SALON_DIR / layer).rglob("*.py"):
        for imported in _salon_imports(path):
            parts = imported.split(".")
            imported_layer = parts[1] if len(parts) > 1 else ""
            if imported_layer and imported_layer not in allowed:
                offenders.append(f"{path.relative_to(SALON_DIR)} -> {imported}")
    return offenders


def test_core_depends_only_on_core() -> None:
    assert not _forbidden_imports("core", {"core"})


def test_application_depends_only_on_core_and_application() -> None:
    assert not _forbidden_imports("application", {"core", "application"})


def test_runtime_adapters_do_not_import_ui() -> None:
    offenders: list[str] = []
    for layer in ("input", "providers", "services"):
        for path in (SALON_DIR / layer).rglob("*.py"):
            imports_ui = any(
                name == "salon.ui" or name.startswith("salon.ui.")
                for name in _salon_imports(path)
            )
            if imports_ui:
                offenders.append(str(path.relative_to(SALON_DIR)))
    assert not offenders, f"runtime adapters import UI: {offenders}"

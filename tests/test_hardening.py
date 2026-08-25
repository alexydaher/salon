# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

from salon.core import sandbox

ROOT = Path(__file__).resolve().parent.parent


def test_application_never_writes_the_global_screen_lock() -> None:
    for path in (ROOT / "salon").rglob("*.py"):
        text = path.read_text()
        assert "org.gnome.desktop.screensaver" not in text
        assert '"lock-enabled"' not in text


def test_flatpak_capabilities_are_honest() -> None:
    caps = sandbox.capabilities(sandboxed=True)
    assert caps.host_spawn is True
    assert not caps.control_center
    assert not caps.autostart
    assert not caps.network_configuration
    assert not caps.bluetooth_pairing
    assert not caps.cec
    assert not caps.mutter_injection
    assert not caps.shell_keyboard
    assert not caps.host_power


def test_native_capabilities_keep_native_integrations() -> None:
    caps = sandbox.capabilities(sandboxed=False)
    assert all(getattr(caps, field.name) for field in fields(caps) if field.name != "sandboxed")


def test_screen_lock_service_is_not_installed() -> None:
    installed = (ROOT / "salon" / "services" / "meson.build").read_text()
    assert "screenlock.py" not in installed


def test_no_screen_lock_import_survives() -> None:
    for path in (ROOT / "salon").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        assert all(
            not (isinstance(node, ast.ImportFrom) and node.module == "salon.services.screenlock")
            for node in ast.walk(tree)
        )


def test_source_has_no_wildcards_or_dynamic_component_delegation() -> None:
    """Keep every explicit-composition stage reviewable."""
    for path in (ROOT / "salon").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        assert not any(
            isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(tree)
        ), path
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__getattr__"
            for node in ast.walk(tree)
        ), path

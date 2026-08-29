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


def test_the_sandbox_withholds_exactly_two_capabilities() -> None:
    """Pin the list, because it is the security boundary.

    Everything else is reachable through the host-spawn grant Salon must
    hold to launch anything, or through a system-bus name narrower than it.
    These two are not: `mutter_injection` is input injection with no prompt
    and no revocation, and `autostart` writes a host file Salon should be
    asking the Background portal for. Adding a third entry here needs a
    reason written down, not a passing test.
    """
    caps = sandbox.capabilities(sandboxed=True)
    withheld = {
        field.name
        for field in fields(caps)
        if field.name != "sandboxed" and not getattr(caps, field.name)
    }
    assert withheld == {"mutter_injection", "autostart"}


def test_native_capabilities_keep_native_integrations() -> None:
    caps = sandbox.capabilities(sandboxed=False)
    assert all(getattr(caps, field.name) for field in fields(caps) if field.name != "sandboxed")


def test_the_manifest_never_asks_for_unprompted_input_injection() -> None:
    """The one name that must never appear in finish-args.

    `org.gnome.Mutter.RemoteDesktop` grants system-wide pointer and keyboard
    injection with no dialog and no way to revoke it. Outside the sandbox
    that is the right trade — it is the only route a television with no
    keyboard and no mouse can complete. Inside one it is the sandbox failing
    at its only job, and `input-injection=auto` falls through to the portal
    on its own when the name is absent. The absence *is* the configuration,
    so it is worth a test rather than a comment.
    """
    manifest = (ROOT / "io.github.alexydaher.Salon.yaml").read_text()
    for line in manifest.splitlines():
        stripped = line.strip()
        if stripped.startswith("- --") and "talk-name" in stripped:
            assert "Mutter" not in stripped, stripped


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

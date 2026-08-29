# SPDX-License-Identifier: GPL-3.0-or-later
"""GNOME's shell on-screen keyboard, turned on and off by Salon.

Salon deliberately doesn't render its own OSK overlay for *other* apps: it
can't force itself above another client's Wayland window, so a custom
overlay wouldn't reliably show up over Chrome or Netflix. GNOME's a11y
keyboard is a shell-level surface and isn't bound by that limit, and the
gamepad-driven cursor from `PointerInjector` can then click its keys like a
real mouse. So the whole feature is one boolean in one schema.

The catch is *whose* boolean. A native build sets it directly. The Flatpak
has no host dconf and is not getting any — mounting the user's dconf socket
into the sandbox hands it every desktop preference on the machine, to read
and to write, in exchange for this one key. It spawns `gsettings` on the
host instead, through the host-spawn grant Salon already holds, which
reaches exactly that key and nothing else.
"""

from __future__ import annotations

import subprocess

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio  # noqa: E402

from salon.core import sandbox  # noqa: E402

_A11Y_SCHEMA = "org.gnome.desktop.a11y.applications"
_OSK_KEY = "screen-keyboard-enabled"


def _a11y_settings() -> Gio.Settings | None:
    """GNOME's accessibility settings, or None where they aren't installed.

    Worth the detour, because `Gio.Settings.new` on a schema that is not
    there does not raise — it is a `g_error`, which aborts the process. So
    on a desktop without gsettings-desktop-schemas, Salon died on the first
    press of Y in pointer mode instead of doing nothing. Host settings
    guards its own host key the same way, for the same reason.
    """
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(_A11Y_SCHEMA, True) is None:
        return None
    return Gio.Settings.new(_A11Y_SCHEMA)


_GSETTINGS = "gsettings"
# One key read or written by a spawned process. Bounded because this runs on
# the main loop, from a button press.
_GSETTINGS_TIMEOUT_SECONDS = 5


def _host_gsettings(*args: str) -> str | None:
    """Run `gsettings` on the host, returning its stdout, or None.

    The Flatpak has no host dconf and is not getting any: mounting the
    user's dconf socket into the sandbox hands it every desktop preference
    on the machine to read and write, for one boolean. Spawning the
    command-line tool through the host-spawn grant Salon already holds
    reaches exactly that one key and nothing else.
    """
    try:
        completed = subprocess.run(
            [*sandbox.HOST_SPAWN, _GSETTINGS, *args],
            capture_output=True,
            text=True,
            timeout=_GSETTINGS_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def set_onscreen_keyboard_enabled(enabled: bool) -> None:
    """Toggle GNOME's built-in accessibility on-screen keyboard.

    We deliberately don't render our own OSK overlay: Salon can't force
    itself above another app's Wayland window, so a custom overlay
    wouldn't reliably show up over Chrome/Netflix/etc. GNOME's a11y
    keyboard is a shell-level surface and isn't bound by that limit — the
    gamepad-driven cursor from PointerInjector can then click its keys
    like a real mouse.

    Native builds set the key directly. The Flatpak sets the *host's* key
    with `gsettings`, because its own `Gio.Settings` writes into the
    sandbox's dconf, where the shell that would draw the keyboard is not
    looking. That distinction is the whole bug: the write appeared to
    succeed and nothing came up.
    """
    if sandbox.in_flatpak():
        if _host_gsettings("set", _A11Y_SCHEMA, _OSK_KEY, "true" if enabled else "false") is None:
            print("[pointer] Couldn't reach the host's on-screen keyboard setting.")
        return
    settings = _a11y_settings()
    if settings is None:
        print("[pointer] No GNOME a11y schema here; leaving the on-screen keyboard alone.")
        return
    settings.set_boolean(_OSK_KEY, enabled)


def onscreen_keyboard_enabled() -> bool:
    if sandbox.in_flatpak():
        # `gsettings get` prints the GVariant, so a bare "true\n".
        return (_host_gsettings("get", _A11Y_SCHEMA, _OSK_KEY) or "").strip() == "true"
    settings = _a11y_settings()
    return bool(settings.get_boolean(_OSK_KEY)) if settings is not None else False


def onscreen_keyboard_available(sandboxed: bool | None = None) -> bool:
    """Whether the Y-button shortcut can control GNOME's shell keyboard."""
    if not sandbox.host_settings_available(sandboxed):
        return False
    if sandbox.in_flatpak() if sandboxed is None else sandboxed:
        return sandbox.host_which(_GSETTINGS, sandboxed)
    return _a11y_settings() is not None

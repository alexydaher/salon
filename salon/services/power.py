# SPDX-License-Identifier: GPL-3.0-or-later
"""System power actions via logind (§8) — never `systemctl`.

Talks to org.freedesktop.login1.Manager on the *system* bus (not session).
Suspend/Reboot/PowerOff take an "interactive" flag that lets polkit show
its own auth prompt if the calling user isn't otherwise allowed; True is
the right default for a desktop app running as a normal logged-in user.

Every call reports its result. These used to be dispatched fire-and-forget
with a NULL callback, which meant a refusal — an inhibitor holding a block
lock, a polkit prompt the user can't see because Salon is fullscreen over
it, a missing authorisation — arrived as nothing at all: the menu closed and
the machine carried on running. On a device with no visible desktop
underneath, a power button that fails silently is indistinguishable from one
that isn't wired up.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

_BUS_NAME = "org.freedesktop.login1"
_OBJECT_PATH = "/org/freedesktop/login1"
_MANAGER_IFACE = "org.freedesktop.login1.Manager"


def _connection() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


def _call(
    method: str, *, on_error: Callable[[str], None] | None = None, interactive: bool = True
) -> None:
    """Ask logind to do it, and say so if it won't.

    Asynchronous because polkit may take seconds to answer (it can put an
    authentication dialog on screen), and blocking the main loop on that
    would freeze the interface mid-shutdown.
    """

    def finished(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as exc:
            if on_error is not None:
                on_error(exc.message)

    _connection().call(
        _BUS_NAME,
        _OBJECT_PATH,
        _MANAGER_IFACE,
        method,
        GLib.Variant("(b)", (interactive,)),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        finished,
    )


def _can(method: str) -> bool:
    """CanSuspend/CanReboot/CanPowerOff return "yes"/"no"/"challenge"/"na".
    Treat anything but an outright "no" as available — "challenge" means
    polkit will prompt, which is fine, not a reason to hide the option."""
    try:
        result = _connection().call_sync(
            _BUS_NAME,
            _OBJECT_PATH,
            _MANAGER_IFACE,
            method,
            None,
            GLib.VariantType("(s)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
    except GLib.Error:
        return False
    return bool(result.unpack()[0] != "no")


def can_suspend() -> bool:
    return _can("CanSuspend")


def can_reboot() -> bool:
    return _can("CanReboot")


def can_power_off() -> bool:
    return _can("CanPowerOff")


def suspend(on_error: Callable[[str], None] | None = None) -> None:
    _call("Suspend", on_error=on_error)


def reboot(on_error: Callable[[str], None] | None = None) -> None:
    _call("Reboot", on_error=on_error)


def power_off(on_error: Callable[[str], None] | None = None) -> None:
    _call("PowerOff", on_error=on_error)

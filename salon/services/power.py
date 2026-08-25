# SPDX-License-Identifier: GPL-3.0-or-later
"""System power actions (§8) — logind and gnome-session, never `systemctl`.

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

Logging out is the exception to "logind, always": see `log_out`.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

_BUS_NAME = "org.freedesktop.login1"
_OBJECT_PATH = "/org/freedesktop/login1"
_MANAGER_IFACE = "org.freedesktop.login1.Manager"

# Logging out is the one action here that is not logind's to do first.
# gnome-session owns the session's lifetime — it is what runs the Salon unit
# and what knows how to shut its components down in order — so the session
# manager is asked first and logind is the fallback for a session that has
# no gnome-session at all. Mode 1 is "no confirmation dialog": Salon is
# fullscreen over everything, so a GNOME confirmation prompt would be a
# dialog the user cannot see and cannot answer with a remote. The menu row
# is a deliberate press on a screen the user is looking at; that is the
# confirmation.
_SESSION_BUS_NAME = "org.gnome.SessionManager"
_SESSION_OBJECT_PATH = "/org/gnome/SessionManager"
_SESSION_IFACE = "org.gnome.SessionManager"
_LOGOUT_MODE_NO_CONFIRMATION = 1

# The current session, whichever it is, without having to look up an id.
_SELF_SESSION_PATH = "/org/freedesktop/login1/session/self"
_SESSION_OBJECT_IFACE = "org.freedesktop.login1.Session"


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


def _session_connection() -> Gio.DBusConnection | None:
    """None where there is no session bus at all. Salon under a bare Xvfb
    in CI is exactly that, and an exception out of a menu-building `can_*`
    call would take the whole menu with it."""
    try:
        return Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        return None


def can_log_out() -> bool:
    """True unless there is nothing to log out *of*.

    Deliberately permissive, like `_can` above: a session bus with no
    gnome-session on it still has a logind session to terminate, and the
    only case worth hiding the row for is a Salon started outside a session
    altogether — a bare Xvfb, a test harness — where both routes are
    missing.
    """
    session = _session_connection()
    if session is not None and _owns_name(session, _SESSION_BUS_NAME):
        return True
    try:
        _connection().call_sync(
            _BUS_NAME,
            _SELF_SESSION_PATH,
            "org.freedesktop.DBus.Properties",
            "Get",
            GLib.Variant("(ss)", (_SESSION_OBJECT_IFACE, "Id")),
            GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
    except GLib.Error:
        return False
    return True


def _owns_name(connection: Gio.DBusConnection, name: str) -> bool:
    try:
        result = connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", (name,)),
            GLib.VariantType("(b)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
    except GLib.Error:
        return False
    return bool(result.unpack()[0])


def log_out(on_error: Callable[[str], None] | None = None) -> None:
    """End the session and return to the login screen.

    gnome-session first, logind second. The fallback is not decoration: the
    Salon (Kiosk) session runs gnome-kiosk instead of the Shell, and a
    machine that is running Salon as a plain application under some other
    desktop may have no org.gnome.SessionManager on the bus at all.
    """

    def finished(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error:
            _terminate_session(on_error)

    session = _session_connection()
    if session is None or not _owns_name(session, _SESSION_BUS_NAME):
        _terminate_session(on_error)
        return

    session.call(
        _SESSION_BUS_NAME,
        _SESSION_OBJECT_PATH,
        _SESSION_IFACE,
        "Logout",
        GLib.Variant("(u)", (_LOGOUT_MODE_NO_CONFIRMATION,)),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        finished,
    )


def _terminate_session(on_error: Callable[[str], None] | None) -> None:
    """logind's own way out, for a session gnome-session isn't running."""

    def finished(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as exc:
            if on_error is not None:
                on_error(exc.message)

    _connection().call(
        _BUS_NAME,
        _SELF_SESSION_PATH,
        _SESSION_OBJECT_IFACE,
        "Terminate",
        None,
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        finished,
    )

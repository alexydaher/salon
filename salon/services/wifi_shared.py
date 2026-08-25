# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Joining a wireless network from the sofa, over NetworkManager.

Salon's Network panel could read the connection and could open
gnome-control-center, and that second half is a dead end on the machine
this is for: gnome-control-center is a mouse-and-keyboard application, its
Wi-Fi list is not focusable with a D-pad, and its password field cannot be
reached by a remote at all. A television that has just been moved to a new
room, or a fresh install, has no other way onto the network — and no way to
reach anything Salon is for.

So this is the list and the password box, in Salon's own language: scan,
show what is in range strongest first, take a password through the same
on-screen keyboard everything else uses, and say what happened.

Scope is deliberately one thing: **join a WPA-PSK network, or an open one.**
Enterprise authentication, hidden SSIDs, captive portals and static
addressing all remain gnome-control-center's job, and the panel still
offers it. Those need a keyboard and a person who knows what they are
doing; this needs a remote and someone who knows their own Wi-Fi password.

Everything is asynchronous, as §10 requires — a scan takes seconds and an
association can take tens of them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core.status import wifi_icon  # noqa: E402

_BUS = "org.freedesktop.NetworkManager"
_PATH = "/org/freedesktop/NetworkManager"
_NM = "org.freedesktop.NetworkManager"
_DEVICE = "org.freedesktop.NetworkManager.Device"
_WIRELESS = "org.freedesktop.NetworkManager.Device.Wireless"
_AP = "org.freedesktop.NetworkManager.AccessPoint"
_SETTINGS_PATH = "/org/freedesktop/NetworkManager/Settings"
_SETTINGS = "org.freedesktop.NetworkManager.Settings"
_CONNECTION = "org.freedesktop.NetworkManager.Settings.Connection"
_PROPS = "org.freedesktop.DBus.Properties"

_DEVICE_TYPE_WIFI = 2

# NM 802-11 security flag bits. Only two questions matter here: is the
# network open, and does it want a passphrase.
_AP_FLAGS_PRIVACY = 0x1

_TIMEOUT_MS = 25_000


@dataclass(frozen=True, slots=True)
class AccessPoint:
    ssid: str
    strength: int
    secured: bool
    path: str

    @property
    def icon_name(self) -> str:
        return wifi_icon(self.strength)

    @property
    def summary(self) -> str:
        return f"{self.strength}%" + (" · password" if self.secured else " · open")


def _decode_ssid(raw: object) -> str:
    """NM hands the SSID back as raw bytes, because that is what it is —
    the standard does not say it is text, and plenty of routers ship one
    that is not valid UTF-8."""
    if not isinstance(raw, (bytes, bytearray, list, tuple)):
        return ""
    return bytes(raw).decode("utf-8", errors="replace").strip()


def _readable(error: GLib.Error) -> str:
    """A D-Bus error as something worth putting on a television.

    §6.11: no Python reprs, no bus names, no interface paths. What is left
    is usually NetworkManager's own message, which is written for people.
    """
    message = (error.message or "").strip()
    _, _, tail = message.rpartition(": ")
    text = (tail or message).strip()
    if not text:
        return "The network refused the connection."
    if "secrets were required" in text.lower() or "no secrets" in text.lower():
        return "That password wasn't accepted."
    return text[:1].upper() + text[1:]


__all__ = [name for name in globals() if not name.startswith("__")]

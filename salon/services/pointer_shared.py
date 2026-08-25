# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Pointer, click and keyboard injection, by two routes.

Wayland forbids one app from injecting input into another app's window
directly (unlike X11's XTestFakeInput), so this goes through the
compositor. There are two ways to ask, and Salon tries them in this order:

1. **`org.gnome.Mutter.RemoteDesktop`** — mutter's own interface, on the
   session bus, owned by gnome-shell (or gnome-kiosk; both link the same
   libmutter, which is where the name lives). `CreateSession` + `Start` is
   two synchronous calls, about 4 ms, **and no consent dialog at all** —
   the dialog belongs to xdg-desktop-portal-gnome, which is a *client* of
   this interface rather than a layer beneath it. This is the same door
   gnome-remote-desktop goes through.
2. **`org.freedesktop.portal.RemoteDesktop`** — the sandboxed, public
   route, which asks the user for consent.

The order exists because of a deadlock, not a preference. Salon is a
ten-foot interface whose *first* input device is often the phone it has not
paired yet: fresh appliance, no controller, no keyboard, no mouse. The
phone's D-pad arrives over HTTP into Salon's own process and needs no
grant — but the trackpad and `/type` need input injection, so Salon asks
the portal, and the portal puts a two-button dialog on the television that
**can only be dismissed with the pointer the dialog is gating**. The one
device that could answer it is the one being asked about. No amount of
token persistence fixes that: `persist_mode` skips the second dialog and
every one after it, never the first.

So the mutter route is not an optimisation. It is the only route that a
machine with no input devices can complete unattended. The portal remains
the fallback for everything else — a non-mutter compositor, or the Flatpak
build, whose sandbox has no business holding a name that grants
system-wide input injection (see `input-injection` in the schema, which
forces the portal for anyone who wants that boundary back).

**The portal's consent dialog is shown once, ever.** RemoteDesktop portal version 2
added `persist_mode` and `restore_token` (the same mechanism screen-sharing
tools use so they don't re-prompt every call). Salon asks for
`PERSIST_EXPLICITLY_REVOKED`, keeps the token the portal hands back, and
passes it to `SelectDevices` next time; the portal then restores the grant
silently. Without this the dialog appears on *every* browser launch, landing
on top of whatever the user just opened.

The same session carries a keyboard, which is what lets the phone type into
a *launched* application (`type_text`). Salon's own on-screen keyboard fills
in Salon's own fields; the one text box that genuinely cannot be avoided on
a television is a search box inside a browser tile, and that belongs to
another process. The devices were always both requested in `SelectDevices`;
until now only the pointer half was used.

The token is deliberately stored by the caller (GSettings) rather than here:
this class holds no policy, and clearing that key is how the grant is given
back. A token the portal no longer honours is dropped on failure so the next
attempt starts clean rather than retrying a dead grant forever.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, GLib  # noqa: E402

from salon.core import sandbox  # noqa: E402

_BUS_NAME = "org.freedesktop.portal.Desktop"
_OBJECT_PATH = "/org/freedesktop/portal/desktop"
_RD_IFACE = "org.freedesktop.portal.RemoteDesktop"
_REQUEST_IFACE = "org.freedesktop.portal.Request"
_SESSION_IFACE = "org.freedesktop.portal.Session"

# mutter's own interface. Version 1, unchanged since it was introduced, and
# load-bearing for gnome-remote-desktop — but private, so it is tried and
# not assumed, and any failure falls through to the portal.
_MUTTER_BUS = "org.gnome.Mutter.RemoteDesktop"
_MUTTER_PATH = "/org/gnome/Mutter/RemoteDesktop"
_MUTTER_IFACE = "org.gnome.Mutter.RemoteDesktop"
_MUTTER_SESSION_IFACE = "org.gnome.Mutter.RemoteDesktop.Session"

# The handshake is two blocking calls on the main loop, so it needs a bound
# that is short enough not to be felt. gnome-shell answers in single-digit
# milliseconds when it is going to answer at all; a shell that is wedged is
# not going to become responsive within a second either.
_MUTTER_TIMEOUT_MS = 2000

# MetaRemoteDesktopSessionAxisFlags. The portal spells this as a `finish`
# option in an a{sv}; mutter spells it as a bit.
_AXIS_FINISH = 1 << 0

# Values of the `input-injection` GSettings key.
BACKEND_AUTO = "auto"
BACKEND_PORTAL = "portal"
BACKEND_MUTTER = "mutter"

_DEVICE_POINTER = 1
_DEVICE_KEYBOARD = 2

# org.freedesktop.portal.RemoteDesktop v2 persist modes.
_PERSIST_NONE = 0
_PERSIST_WHILE_RUNNING = 1
_PERSIST_EXPLICITLY_REVOKED = 2

# persist_mode/restore_token only exist from version 2 of the interface.
# On an older portal both are ignored and the dialog appears every time,
# which is the pre-existing behaviour rather than a failure.
_RD_VERSION_WITH_PERSIST = 2

BTN_LEFT = 0x110
# linux/input-event-codes.h again, and in that header's own order: RIGHT is
# 0x111 and MIDDLE is 0x112. The portal takes evdev button codes directly,
# so these are the same numbers a real mouse reports.
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112

BUTTONS = {"left": BTN_LEFT, "right": BTN_RIGHT, "middle": BTN_MIDDLE}

_PRESSED = 1
_RELEASED = 0

# X11 keysyms for the keys a phone keyboard sends that are not characters.
# Everything else goes through Gdk rather than a rule written out here.
# The rule looks simple — codepoint below U+0100, `0x01000000 + codepoint`
# above — and is wrong in the middle: plenty of characters above Latin-1
# have *legacy named* keysyms that the keymap is indexed by, so the arrow
# in a URL would have been typed as something else. Gdk owns that table and
# xkb agrees with it; restating it here would be a second copy to be wrong.
_KEYSYMS = {
    "\n": 0xFF0D,  # Return
    "\r": 0xFF0D,
    "\t": 0xFF09,  # Tab
    "\b": 0xFF08,  # BackSpace
    "\x7f": 0xFFFF,  # Delete
}

# Between the press and the release of one key, and between one key and the
# next. Zero works against a toolkit reading an event stream and does not
# work against a web page doing its own key handling with a debounce — and
# a search box in a browser is the whole reason this path exists.
_KEY_GAP_MS = 12


def keysym_for(character: str) -> int | None:
    """The X11 keysym for one character, or None if there isn't one."""
    if character in _KEYSYMS:
        return _KEYSYMS[character]
    codepoint = ord(character)
    if codepoint < 0x20:
        # A control character with no named key in the table above. Sending
        # it as a Unicode keysym would type an invisible glyph rather than
        # do nothing, which is worse.
        return None
    keyval = int(Gdk.unicode_to_keyval(codepoint))
    return keyval or None


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


def set_onscreen_keyboard_enabled(enabled: bool) -> None:
    """Toggle GNOME's built-in accessibility on-screen keyboard.

    We deliberately don't render our own OSK overlay: Salon can't force
    itself above another app's Wayland window, so a custom overlay
    wouldn't reliably show up over Chrome/Netflix/etc. GNOME's a11y
    keyboard is a shell-level surface and isn't bound by that limit — the
    gamepad-driven cursor from PointerInjector can then click its keys
    like a real mouse.

    Native Salon sessions use the host key. The Flatpak deliberately omits
    direct dconf access and offers phone typing instead.
    """
    if not sandbox.host_settings_available():
        print("[pointer] Host on-screen keyboard control is disabled in the Flatpak.")
        return
    settings = _a11y_settings()
    if settings is None:
        print("[pointer] No GNOME a11y schema here; leaving the on-screen keyboard alone.")
        return
    settings.set_boolean(_OSK_KEY, enabled)


def onscreen_keyboard_enabled() -> bool:
    if not sandbox.host_settings_available():
        return False
    settings = _a11y_settings()
    return bool(settings.get_boolean(_OSK_KEY)) if settings is not None else False


def onscreen_keyboard_available(sandboxed: bool | None = None) -> bool:
    """Whether the Y-button shortcut can control GNOME's shell keyboard."""
    if not sandbox.host_settings_available(sandboxed):
        return False
    return _a11y_settings() is not None


__all__ = [name for name in globals() if not name.startswith("__")]

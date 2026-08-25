# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
"""Pairing a controller or remote from the sofa, over BlueZ.

The chicken-and-egg problem at the centre of a console: a wireless
controller is how you drive Salon, and pairing one needs a pairing screen
you can drive — which, before this, meant gnome-control-center, which needs
a mouse. The first controller on a fresh machine could not be paired from
the television at all.

So: scan, list what is discoverable, and pair on OK. Three details make it
work for the devices that matter rather than merely exist:

* **An agent is registered, with no input and no output.** Pairing is a
  negotiation about how to confirm identity, and without an agent BlueZ has
  nobody to ask, so pairing a gamepad fails. `NoInputNoOutput` is the
  honest description of a television and it selects "just works" pairing,
  which is what every game controller and almost every remote uses. A
  device demanding a typed PIN is refused with a message saying so, rather
  than hanging on a prompt nobody can answer.
* **Pairing, trusting and connecting are one action.** Separately they are
  three concepts from the Bluetooth specification; together they are what
  "pair my controller" means. Trust in particular is what makes the
  controller reconnect by itself next time, which is the difference between
  a console and a science project.
* **Devices are shown with their class.** A room contains phones,
  headphones, watches and a television's own remote; a list of names with
  no indication which is which is a list you pair the wrong thing from.

Verified against a real adapter for the parts that can be checked without
changing somebody's setup: listing, naming and classifying — a DualSense in
the room comes back as "Gamepad", a pair of headphones as "Audio". The
*pairing* path has not been run, because exercising it means pairing and
unpairing hardware that belongs to someone, and a half-completed pairing is
worse than an untested code path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

_BUS = "org.bluez"
_ADAPTER = "org.bluez.Adapter1"
_DEVICE = "org.bluez.Device1"
_AGENT_MANAGER = "org.bluez.AgentManager1"
_OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"
_PROPS = "org.freedesktop.DBus.Properties"

_AGENT_PATH = "/io/github/alexydaher/Salon/bluez_agent"
_AGENT_IFACE = "org.bluez.Agent1"

_TIMEOUT_MS = 30_000

# Bluetooth "major device class" (bits 8-12 of the class of device), which
# is the only thing every device reports and the only thing needed to tell
# a gamepad from a pair of headphones.
_MAJOR_CLASS_NAMES = {
    0x01: "Computer",
    0x02: "Phone",
    0x04: "Audio",
    0x05: "Controller or remote",
    0x06: "Imaging",
    0x07: "Wearable",
}

# Bluetooth Low Energy devices have no class of device at all — the field
# is a Classic concept and BlueZ reports 0 for them. They carry an
# `Appearance` instead, which is a category and a subcategory in one 16-bit
# number. Without this, every BLE keyboard, mouse and remote in the room
# lists as the unhelpful "Device", which is what the first version did.
_APPEARANCE_CATEGORY = {
    0x001: "Phone",
    0x002: "Computer",
    0x005: "Display",
    0x00A: "Clock",
    0x00D: "Media player",
    0x00E: "Barcode scanner",
    0x031: "Audio",
}
_APPEARANCE_HID = {
    0x01: "Keyboard",
    0x02: "Pointer",
    0x03: "Joystick",
    0x04: "Gamepad",
    0x05: "Tablet",
    0x06: "Card reader",
    0x07: "Pen",
    0x08: "Barcode scanner",
}
_APPEARANCE_HID_CATEGORY = 0x00F

# The peripheral minor class splits in two: a four-bit device type, and two
# flag bits for "is a keyboard" / "is a pointing device". A DualSense
# reports class 0x002508, whose device-type nibble is 2 — gamepad. Reading
# the flag bits first calls it a pointer, which is how the first version of
# this table labelled every controller in the room "Pointer".
_PERIPHERAL_TYPE = {
    0x01: "Joystick",
    0x02: "Gamepad",
    0x03: "Remote control",
    0x04: "Sensor",
    0x05: "Tablet",
}

_AGENT_XML = """
<node>
  <interface name='org.bluez.Agent1'>
    <method name='Release'/>
    <method name='RequestPinCode'>
      <arg type='o' name='device' direction='in'/>
      <arg type='s' name='pincode' direction='out'/>
    </method>
    <method name='DisplayPinCode'>
      <arg type='o' name='device' direction='in'/>
      <arg type='s' name='pincode' direction='in'/>
    </method>
    <method name='RequestPasskey'>
      <arg type='o' name='device' direction='in'/>
      <arg type='u' name='passkey' direction='out'/>
    </method>
    <method name='DisplayPasskey'>
      <arg type='o' name='device' direction='in'/>
      <arg type='u' name='passkey' direction='in'/>
      <arg type='q' name='entered' direction='in'/>
    </method>
    <method name='RequestConfirmation'>
      <arg type='o' name='device' direction='in'/>
      <arg type='u' name='passkey' direction='in'/>
    </method>
    <method name='RequestAuthorization'>
      <arg type='o' name='device' direction='in'/>
    </method>
    <method name='AuthorizeService'>
      <arg type='o' name='device' direction='in'/>
      <arg type='s' name='uuid' direction='in'/>
    </method>
    <method name='Cancel'/>
  </interface>
</node>
"""


@dataclass(frozen=True, slots=True)
class Device:
    path: str
    name: str
    kind: str
    paired: bool
    connected: bool

    @property
    def summary(self) -> str:
        if self.connected:
            return "Connected"
        if self.paired:
            return "Paired"
        return self.kind


def _describe_class(value: int) -> str:
    """A Bluetooth class-of-device as something worth reading on a sofa.

    The layout is fixed by the specification: bits 8-12 are the major
    class, bits 2-7 the minor. For a peripheral the minor splits again into
    a device-type nibble and two flags, and the nibble is the one that
    knows a gamepad from a mouse.
    """
    major = (value >> 8) & 0x1F
    if major == 0x05:
        named = _PERIPHERAL_TYPE.get((value >> 2) & 0x0F)
        if named:
            return named
        flags = (value >> 6) & 0x03
        if flags & 0x01:
            return "Keyboard"
        if flags & 0x02:
            return "Pointer"
    return _MAJOR_CLASS_NAMES.get(major, "Device")


def _describe_appearance(value: int) -> str:
    """A BLE `Appearance` as a readable kind, or "" if it says nothing."""
    category = (value >> 6) & 0x3FF
    if category == _APPEARANCE_HID_CATEGORY:
        return _APPEARANCE_HID.get(value & 0x3F, "Input device")
    return _APPEARANCE_CATEGORY.get(category, "")


def describe_device(properties: dict[str, object]) -> str:
    """What kind of thing this is, from whichever field it has.

    Classic devices carry a class of device; Low Energy ones carry an
    appearance and a class of zero. A room contains both, and a list that
    calls half of them "Device" is a list you pair the wrong thing from.
    """
    class_of_device = int(properties.get("Class", 0) or 0)
    if class_of_device:
        return _describe_class(class_of_device)
    appearance = int(properties.get("Appearance", 0) or 0)
    if appearance:
        described = _describe_appearance(appearance)
        if described:
            return described
    # Last resort, and better than nothing: BlueZ knows an icon name for
    # most devices even when it knows no class.
    icon = str(properties.get("Icon") or "")
    if icon:
        return icon.replace("-", " ").replace("input ", "").strip().capitalize()
    return "Device"


def _ignore(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
    try:
        connection.call_finish(result)
    except GLib.Error:
        # An agent already registered by something else on the system is
        # the normal case on a full desktop, and is fine: that agent can
        # answer the prompts.
        pass


def _readable(error: GLib.Error) -> str:
    message = (error.message or "").strip()
    _, _, tail = message.rpartition(": ")
    text = (tail or message).strip()
    return (text[:1].upper() + text[1:]) if text else "The device refused to pair."


__all__ = [name for name in globals() if not name.startswith("__")]

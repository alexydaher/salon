# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused settings panel builder."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from salon.services import bluetooth  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    InfoRow,
    SettingsRow,
)


def _bluetooth_panel(context: SettingsContext) -> Panel:
    """Scan, list, pair.

    The chicken-and-egg screen: a wireless controller is how you drive
    Salon, and until this existed the only way to pair the first one was a
    mouse. Discovery starts when the panel opens and stops when it closes,
    because an adapter left scanning costs power and floods the list.
    """
    service = bluetooth.BluetoothService()
    state: dict[str, object] = {"devices": [], "error": "", "scanned": False, "asking": False}

    def on_listed(devices: list[bluetooth.Device], error: str) -> None:
        state.update(devices=devices, error=error, scanned=True, asking=False)
        context.rebuild()

    def request() -> None:
        # Guarded, and deliberately not calling context.rebuild(): `build`
        # runs on every rebuild, so a request that rebuilt would call build
        # again, which would request again. That recursion is not
        # theoretical — it was this panel's first version.
        if state["asking"]:
            return
        state["asking"] = True

        def listed(devices: list[bluetooth.Device], error: str) -> None:
            on_listed(devices, error)
            # Discovery can only start once an adapter has been found, so
            # it is chained behind the listing rather than run beside it.
            if not error:
                service.start_discovery(lambda ok, message: None)

        service.list_devices(listed)

    def rescan() -> None:
        state["scanned"] = False
        request()
        context.rebuild()

    def pair(device: bluetooth.Device) -> None:
        context.toast(f"Pairing {device.name}…")

        def paired(ok: bool, message: str) -> None:
            context.toast(message)
            state["scanned"] = False
            request()

        service.pair(device, paired)

    def reload() -> None:
        """Re-list after something changed the device, and redraw whichever
        panel is on top — this one, or a device's own panel above it."""
        state["scanned"] = False
        request()
        context.rebuild()

    def open_device(device: bluetooth.Device) -> None:
        context.push(_bluetooth_device_panel(context, service, device, reload))

    def choose(device: bluetooth.Device) -> None:
        # A device Salon has never seen has exactly one useful thing that
        # can be done to it, so OK does it rather than opening a menu with
        # one item on it. A paired one has three, including the one that
        # cannot be undone, so it gets a panel.
        if device.paired:
            open_device(device)
        else:
            pair(device)

    def leave() -> None:
        # The adapter is left scanning otherwise — this used to claim in
        # its own docstring that discovery "stops when the panel closes",
        # and nothing anywhere called stop_discovery. A television quietly
        # scanning for Bluetooth devices forever costs power and keeps the
        # radio busy while a paired controller is trying to use it.
        service.stop_discovery()

    def build() -> list[SettingsRow]:
        if not state["scanned"]:
            request()
            return [
                InfoRow(
                    "Looking for devices…",
                    "",
                    detail="Put the controller or remote into pairing mode now",
                )
            ]
        error = str(state["error"])
        if error:
            return [
                InfoRow("Couldn't look for devices", "", detail=error),
                ActionRow("Try again", rescan),
            ]
        devices = list(state["devices"])  # type: ignore[arg-type]
        rows: list[SettingsRow] = [
            ActionRow(
                device.name,
                lambda d=device: choose(d),
                value=device.summary,
                detail=device.kind,
                # A paired row leads somewhere, so RIGHT may open it; an
                # unpaired one *acts*, and a direction key must not be how
                # a television starts pairing with a stranger's phone.
                opens=device.paired,
            )
            for device in devices
        ]
        if not rows:
            rows.append(
                InfoRow(
                    "Nothing found yet",
                    "",
                    detail="Hold the controller's pairing button until its light flashes",
                )
            )
        rows.append(ActionRow("Look again", rescan, detail="Scan for another few seconds"))
        return rows

    return Panel(title="Pair a device", build=build, on_leave=leave)


def _bluetooth_device_panel(
    context: SettingsContext,
    service: bluetooth.BluetoothService,
    device: bluetooth.Device,
    reload: Callable[[], None],
) -> Panel:
    """One paired device: connect, disconnect, forget.

    Forgetting is the reason this panel exists. A controller that has been
    paired once is remembered forever, and a list that can only ever grow —
    a flatmate's headphones, a phone that visited, the same pad paired twice
    under two names — is a list the right device gets harder to find in
    every time. It is also the only repair for a pairing that has gone bad:
    BlueZ will not re-pair a device it thinks it already knows, so "forget,
    then pair again" is the fix, and until now it needed a mouse and
    gnome-control-center.
    """

    def done(message: str) -> None:
        context.toast(message)
        reload()

    def connect() -> None:
        context.toast(f"Connecting to {device.name}…")
        service.pair(device, lambda ok, message: done(message))

    def disconnect() -> None:
        service.disconnect(device, lambda ok, message: done(message))

    def forget() -> None:
        def forgotten(ok: bool, message: str) -> None:
            context.toast(message)
            if ok:
                # Back to the list: this panel is about a device that no
                # longer exists, and leaving it up would offer to connect
                # to something Salon has just been told to forget.
                context.pop()
            reload()

        service.forget(device, forgotten)

    def confirm_forget() -> None:
        context.push(confirm_panel(context, f"Forget {device.name}?", "Forget device", forget))

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = [InfoRow(device.kind, device.summary)]
        if device.connected:
            rows.append(
                ActionRow(
                    "Disconnect",
                    disconnect,
                    detail="Stays paired, and reconnects on its own next time",
                )
            )
        else:
            rows.append(ActionRow("Connect", connect, detail="Wake it up and connect to it now"))
        rows.append(
            ActionRow(
                "Forget this device",
                confirm_forget,
                danger=True,
                detail="Unpair it completely — you'll have to pair it again to use it",
            )
        )
        return rows

    return Panel(title=device.name, build=build)

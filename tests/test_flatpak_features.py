# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-wide features deliberately omitted from the Flatpak build."""

from __future__ import annotations

from salon.core import sandbox
from salon.input import cec_in
from salon.services import bluetooth, pointer_shared, power, wifi


def test_flatpak_never_probes_logind(monkeypatch) -> None:
    monkeypatch.setattr(power.sandbox, "host_power_available", lambda: False)

    def unexpected_probe(_method: str) -> bool:
        raise AssertionError("logind must not be contacted from Flatpak")

    monkeypatch.setattr(power, "_can", unexpected_probe)

    assert power.can_suspend() is False
    assert power.can_reboot() is False
    assert power.can_power_off() is False
    assert power.can_log_out() is False


def test_flatpak_power_calls_fail_without_touching_a_bus(monkeypatch) -> None:
    monkeypatch.setattr(power.sandbox, "host_power_available", lambda: False)
    errors: list[str] = []

    power.suspend(errors.append)
    power.reboot(errors.append)
    power.power_off(errors.append)
    power.log_out(errors.append)

    assert errors == ["Host power controls are unavailable in the Flatpak build."] * 4


def test_flatpak_never_probes_gnome_shell_keyboard_settings(monkeypatch) -> None:
    def unexpected_settings():
        raise AssertionError("host GSettings must not be contacted from Flatpak")

    monkeypatch.setattr(pointer_shared, "_a11y_settings", unexpected_settings)

    assert pointer_shared.onscreen_keyboard_available(sandboxed=True) is False


def test_flatpak_configuration_services_never_probe_the_system_bus(monkeypatch) -> None:
    monkeypatch.setattr(sandbox, "in_flatpak", lambda: True)

    def unexpected_bus(*_args):
        raise AssertionError("forbidden host system bus was probed")

    monkeypatch.setattr(wifi.Gio, "bus_get_sync", unexpected_bus)
    monkeypatch.setattr(bluetooth.Gio, "bus_get_sync", unexpected_bus)
    assert wifi.WifiService()._bus() is None
    assert bluetooth.BluetoothService()._bus() is None


def test_cec_is_never_probed_inside_flatpak(monkeypatch) -> None:
    monkeypatch.setattr(
        cec_in.shutil,
        "which",
        lambda _name: (_ for _ in ()).throw(AssertionError("cec-client was probed")),
    )
    assert not cec_in.available(sandboxed=True)

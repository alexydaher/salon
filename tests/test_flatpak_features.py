# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-wide features deliberately omitted from the Flatpak build."""

from __future__ import annotations

from salon.services import pointer_shared, power


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

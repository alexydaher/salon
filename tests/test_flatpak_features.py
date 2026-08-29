# SPDX-License-Identifier: GPL-3.0-or-later
"""What the Flatpak build may and may not reach.

Until 2026-08-29 this file asserted the opposite of most of what is below:
power, Wi-Fi, Bluetooth and CEC were all withheld from the sandbox. The
reasoning did not survive the grant it sat next to. A build holding
`--talk-name=org.freedesktop.Flatpak` can already run `systemctl poweroff`,
`nmcli` or `bluetoothctl` on the host through one of Salon's own command
tiles, so withholding `login1` bought no safety and cost four features.
The narrow system-bus names are now in the manifest, where
`flatpak info --show-permissions` can show them.

Two things stay behind: unprompted input injection, and writing the host's
autostart entry.
"""

from __future__ import annotations

from salon.core import sandbox
from salon.input import cec_in
from salon.services import onscreen_keyboard, power


def test_power_is_offered_in_both_builds(monkeypatch) -> None:
    """logind decides, not the packaging.

    `_can` is the real gate in both builds: it asks logind, logind asks
    polkit, and a "no" hides the row. What changed is that the Flatpak now
    gets to ask.
    """
    monkeypatch.setattr(power.sandbox, "host_power_available", lambda: True)
    monkeypatch.setattr(power, "_can", lambda _method: True)

    assert power.can_suspend() is True
    assert power.can_reboot() is True
    assert power.can_power_off() is True


def test_a_refused_power_action_is_reported_rather_than_swallowed(monkeypatch) -> None:
    monkeypatch.setattr(power.sandbox, "host_power_available", lambda: False)
    errors: list[str] = []

    power.suspend(errors.append)
    power.reboot(errors.append)
    power.power_off(errors.append)
    power.log_out(errors.append)

    assert errors == ["Host power controls are unavailable in the Flatpak build."] * 4


def test_the_shell_keyboard_is_reached_through_the_host_not_sandbox_dconf(monkeypatch) -> None:
    """The bug this guards: a write that succeeded into the wrong dconf.

    Inside Flatpak `Gio.Settings` resolves the runtime's copy of the schema
    and writes the sandbox's own database — no error, no keyboard, because
    the shell that would draw one is reading the host's. So the sandboxed
    path must not touch `Gio.Settings` at all.
    """
    monkeypatch.setattr(onscreen_keyboard.sandbox, "in_flatpak", lambda: True)

    def unexpected_settings():
        raise AssertionError("sandbox-local GSettings must not be used for a host preference")

    monkeypatch.setattr(onscreen_keyboard, "_a11y_settings", unexpected_settings)

    spawned: list[tuple[str, ...]] = []

    def fake_host_gsettings(*args: str) -> str:
        spawned.append(args)
        return "true\n"

    monkeypatch.setattr(onscreen_keyboard, "_host_gsettings", fake_host_gsettings)

    assert onscreen_keyboard.onscreen_keyboard_enabled() is True
    onscreen_keyboard.set_onscreen_keyboard_enabled(False)

    assert spawned == [
        ("get", "org.gnome.desktop.a11y.applications", "screen-keyboard-enabled"),
        ("set", "org.gnome.desktop.a11y.applications", "screen-keyboard-enabled", "false"),
    ]


def test_cec_probes_the_host_path_not_the_sandbox_path(monkeypatch) -> None:
    """`shutil.which` is the wrong question inside a sandbox.

    cec-client runs on the host and is never on the sandbox's PATH, so a
    bare `which` reported it missing on machines that have it — which is how
    HDMI-CEC came to be documented as a Flatpak limitation when nothing was
    actually withholding the adapter.
    """
    asked: list[str] = []

    def fake_host_which(binary: str, sandboxed: bool | None = None) -> bool:
        asked.append(binary)
        return True

    monkeypatch.setattr(cec_in.sandbox, "host_which", fake_host_which)
    assert cec_in.available(sandboxed=True) is True
    assert asked == ["cec-client"]


def test_host_which_asks_the_host_when_sandboxed(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Completed:
        returncode = 0

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return Completed()

    monkeypatch.setattr(sandbox.shutil, "which", lambda _name: "/usr/bin/flatpak-spawn")
    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)

    assert sandbox.host_which("cec-client", sandboxed=True) is True
    assert calls == [["flatpak-spawn", "--host", "which", "cec-client"]]


def test_host_which_stays_local_when_there_is_no_sandbox(monkeypatch) -> None:
    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("a native build must not spawn anything to answer `which`")

    monkeypatch.setattr(sandbox.subprocess, "run", unexpected_run)
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/x" if name == "x" else None)

    assert sandbox.host_which("x", sandboxed=False) is True
    assert sandbox.host_which("y", sandboxed=False) is False

# SPDX-License-Identifier: GPL-3.0-or-later
"""Launching from inside a Flatpak sandbox (§6.11).

Salon's job is starting other applications, which is the one thing a sandbox
stops. These cover the escape hatch: every launch kind has to pick up the
host-spawn prefix, and none of them may pick it up when there is no sandbox.
"""

from __future__ import annotations

from pathlib import Path

from salon.core import sandbox
from salon.core.launchspec import resolve
from salon.core.model import LaunchKind, LaunchSpec

HOST = sandbox.HOST_SPAWN


def test_no_prefix_outside_a_sandbox(tmp_path: Path) -> None:
    assert sandbox.host_prefix(sandboxed=False) == ()


def test_prefix_inside_a_sandbox() -> None:
    assert sandbox.host_prefix(sandboxed=True) == ("flatpak-spawn", "--host")


def test_in_flatpak_is_decided_by_the_marker_file(tmp_path: Path) -> None:
    marker = tmp_path / ".flatpak-info"
    assert sandbox.in_flatpak(marker) is False
    marker.write_text("[Application]\n")
    assert sandbox.in_flatpak(marker) is True


def test_host_integration_survives_the_sandbox() -> None:
    """Power and the shell keyboard work in both builds.

    They were withheld from the Flatpak until 2026-08-29 on the reasoning
    that a sandboxed app should not hold them — which does not survive the
    grant sitting above it. `--talk-name=org.freedesktop.Flatpak` can spawn
    `systemctl poweroff` on the host through one of Salon's own command
    tiles, so refusing it `login1` cost the user four features and cost an
    attacker nothing.
    """
    assert sandbox.host_settings_available(sandboxed=False) is True
    assert sandbox.host_settings_available(sandboxed=True) is True
    assert sandbox.host_power_available(sandboxed=False) is True
    assert sandbox.host_power_available(sandboxed=True) is True


def test_command_launch_goes_through_the_host() -> None:
    spec = LaunchSpec(kind=LaunchKind.COMMAND, target="steam", args=("-tenfoot",))
    assert resolve(spec, host_prefix=HOST) == [
        "flatpak-spawn",
        "--host",
        "steam",
        "-tenfoot",
    ]
    assert resolve(spec) == ["steam", "-tenfoot"]


def test_flatpak_launch_goes_through_the_host() -> None:
    """`flatpak run` inside a sandbox would look in the sandbox's own
    installation, which contains exactly one app."""
    spec = LaunchSpec(kind=LaunchKind.FLATPAK, target="com.valvesoftware.Steam")
    assert resolve(spec, host_prefix=HOST)[:3] == ["flatpak-spawn", "--host", "flatpak"]


def test_url_launch_keeps_every_browser_flag_behind_the_prefix() -> None:
    spec = LaunchSpec(kind=LaunchKind.URL, target="https://netflix.com")
    argv = resolve(spec, browser_command=("google-chrome",), host_prefix=HOST)
    assert argv[:3] == ["flatpak-spawn", "--host", "google-chrome"]
    assert "--app=https://netflix.com" in argv
    assert "--start-fullscreen" in argv


def test_desktop_launch_uses_gtk_launch_when_sandboxed() -> None:
    """The host's desktop entries aren't visible in the sandbox, so there is
    nothing to parse an Exec= line out of."""
    spec = LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.Nautilus.desktop")
    assert resolve(spec, host_prefix=HOST) == [
        "flatpak-spawn",
        "--host",
        "gtk-launch",
        "org.gnome.Nautilus",
    ]


def test_builtin_never_spawns_anything_even_sandboxed() -> None:
    spec = LaunchSpec(kind=LaunchKind.BUILTIN, target="settings")
    assert resolve(spec, host_prefix=HOST) is None

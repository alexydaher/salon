# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether Salon is running inside a Flatpak sandbox, and what that costs.

Pure — no gi — so `launchspec` can stay testable both ways.

Salon's entire job is starting *other* applications, which is precisely what
a sandbox exists to prevent. Inside Flatpak the only sanctioned route out is
`flatpak-spawn --host`, which needs `--talk-name=org.freedesktop.Flatpak` in
the manifest. That permission is, honestly, equivalent to unsandboxed access
to the session: a launcher cannot be meaningfully confined and still launch
things. The manifest says so in a comment rather than pretending otherwise.

Detection is the presence of `/.flatpak-info`, the file the runtime writes
into every sandbox. `FLATPAK_ID` is not enough on its own — it is also set
in the *host* environment of anything a Flatpak app spawns.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_FLATPAK_INFO = Path("/.flatpak-info")

HOST_SPAWN = ("flatpak-spawn", "--host")


@dataclass(frozen=True, slots=True)
class Capabilities:
    sandboxed: bool
    control_center: bool
    autostart: bool
    network_configuration: bool
    bluetooth_pairing: bool
    cec: bool
    mutter_injection: bool
    shell_keyboard: bool
    host_power: bool
    host_spawn: bool


def capabilities(sandboxed: bool | None = None) -> Capabilities:
    if sandboxed is None:
        sandboxed = in_flatpak()
    host = not sandboxed
    return Capabilities(
        sandboxed=sandboxed,
        control_center=host,
        autostart=host,
        network_configuration=host,
        bluetooth_pairing=host,
        cec=host,
        mutter_injection=host,
        shell_keyboard=host,
        host_power=host,
        host_spawn=True,
    )


def in_flatpak(marker: Path = _FLATPAK_INFO) -> bool:
    return marker.exists()


def host_prefix(sandboxed: bool | None = None) -> tuple[str, ...]:
    """The argv prefix that runs a command on the host, or () when there is
    no sandbox to escape."""
    if sandboxed is None:
        sandboxed = in_flatpak()
    return HOST_SPAWN if sandboxed else ()


def app_id() -> str:
    return os.environ.get("FLATPAK_ID", "")


def host_settings_available(sandboxed: bool | None = None) -> bool:
    """Whether Salon may change desktop-wide settings.

    The Flatpak deliberately has no direct host-dconf access. Native builds
    can still manage the GNOME shell keyboard when Salon is installed as
    the television session. Salon never changes the global screen lock.
    """
    if sandboxed is None:
        sandboxed = in_flatpak()
    return not sandboxed


def host_power_available(sandboxed: bool | None = None) -> bool:
    """Whether direct logind power and logout controls are enabled.

    The Flatpak omits the system-bus permission rather than asking Flathub
    for a broad host-power exception. Native installations retain the full
    kiosk power menu.
    """
    if sandboxed is None:
        sandboxed = in_flatpak()
    return not sandboxed

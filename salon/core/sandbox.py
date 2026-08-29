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

**Two things are withheld from the sandbox, and only two** (2026-08-29).
Everything else the Flatpak used to give up — power, Wi-Fi, Bluetooth,
CEC, GNOME Settings, the shell keyboard — is back, because withholding it
was never buying anything. A build that already holds
`org.freedesktop.Flatpak` can spawn `systemctl poweroff` on the host
through one of Salon's own command tiles; refusing it `login1` while
granting that is a lock on a door in an open field. The narrow grants are
strictly *less* than what the launcher already needs, so they are listed
in the manifest and the capability goes back to True.

The two that stay off are the two where the sandbox is still doing real
work: `mutter_injection`, which is system-wide input injection with no
prompt and no revocation, and `autostart`, which wants a host file Salon
has no business writing (the Background portal is the route, and nobody
has built it yet). Both fall back to something that works — the
RemoteDesktop portal, and the host desktop's own startup preferences.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_FLATPAK_INFO = Path("/.flatpak-info")

# A `which` on the host is a process spawn through the portal. Bounded so a
# wedged portal costs a settings panel a moment rather than the main loop.
_HOST_PROBE_SECONDS = 5

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
    """What this build may do. See the module docstring for why so little
    is withheld: `mutter_injection` and `autostart` are the whole list."""
    if sandboxed is None:
        sandboxed = in_flatpak()
    host = not sandboxed
    return Capabilities(
        sandboxed=sandboxed,
        # Reached by spawning gnome-control-center on the host, which the
        # host-spawn grant already covers.
        control_center=True,
        # The one host file Salon would have to write itself. Needs the
        # Background portal; until then the host desktop owns it.
        autostart=host,
        # --system-talk-name=org.freedesktop.NetworkManager
        network_configuration=True,
        # --system-talk-name=org.bluez
        bluetooth_pairing=True,
        # cec-client is a host binary, run through flatpak-spawn like wpctl.
        cec=True,
        # Withheld on purpose: injection with no prompt and no revocation.
        # `input-injection=auto` falls through to the portal by itself.
        mutter_injection=host,
        # Toggled with `gsettings` on the host rather than host dconf.
        shell_keyboard=True,
        # --system-talk-name=org.freedesktop.login1
        host_power=True,
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


def host_which(binary: str, sandboxed: bool | None = None) -> bool:
    """Whether `binary` is on the PATH the *launch* will actually use.

    `shutil.which` answers about the sandbox, which is the wrong question
    for anything Salon runs through `flatpak-spawn`: `cec-client` and
    `wpctl` live on the host and are never on the sandbox's PATH, so a bare
    `which` reports them missing on a machine that has them. That is how
    HDMI-CEC came to be listed as a sandbox limitation — nothing was
    withholding the adapter, the probe was simply asking the wrong PATH.

    Deliberately not cached: this is called when a settings panel is built,
    not in a loop, and a cache would outlive the user installing the thing
    it just told them was missing.
    """
    if sandboxed is None:
        sandboxed = in_flatpak()
    if not sandboxed:
        return shutil.which(binary) is not None
    if shutil.which("flatpak-spawn") is None:
        return False
    try:
        completed = subprocess.run(
            [*HOST_SPAWN, "which", binary],
            capture_output=True,
            timeout=_HOST_PROBE_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def app_id() -> str:
    return os.environ.get("FLATPAK_ID", "")


def host_settings_available(sandboxed: bool | None = None) -> bool:
    """Whether Salon may change the desktop's shell-keyboard preference.

    Both builds may. The Flatpak reaches it with `gsettings` on the host
    instead of host dconf, so no dconf grant is involved. Salon never
    changes the global screen lock in either build.
    """
    return capabilities(sandboxed).shell_keyboard


def host_power_available(sandboxed: bool | None = None) -> bool:
    """Whether logind power and logout controls are enabled.

    Both builds. The Flatpak names `org.freedesktop.login1` on the system
    bus, which is narrower than the host-spawn grant it already holds.
    logind's own polkit rules still decide each action, in both builds.
    """
    return capabilities(sandboxed).host_power

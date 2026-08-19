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
from pathlib import Path

_FLATPAK_INFO = Path("/.flatpak-info")

HOST_SPAWN = ("flatpak-spawn", "--host")


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

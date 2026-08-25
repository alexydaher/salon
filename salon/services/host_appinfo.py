# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the host's desktop-entry inventory from inside Flatpak."""

from __future__ import annotations

import json
import subprocess

from salon.core import sandbox

# Gio sees the Flatpak's desktop-entry database from inside the sandbox,
# normally only Salon and one or two runtime utilities. The host-spawn grant
# already required for launching apps can run this read-only inventory too.
# The helper needs only the standard library because Salon's modules and its
# runtime do not exist in the host process.
_TIMEOUT_SECONDS = 15
_SCRIPT = r'''
import configparser
import json
import locale
import os
import pwd
from pathlib import Path


def truth(value):
    return value.strip().lower() in ("1", "true", "yes")


def unescape(value):
    return (value.replace(r"\n", "\n").replace(r"\t", "\t")
            .replace(r"\r", "\r").replace(r"\s", " ").replace(r"\\", "\\"))


def localized(section, key):
    choices = []
    choices.extend(part for part in os.environ.get("LANGUAGE", "").split(":") if part)
    current = locale.getlocale()[0] or os.environ.get("LANG", "").split(".", 1)[0]
    if current:
        choices.append(current)
    expanded = []
    for choice in choices:
        choice = choice.split(".", 1)[0]
        expanded.append(choice)
        base = choice.split("@", 1)[0]
        expanded.append(base)
        if "_" in base:
            expanded.append(base.split("_", 1)[0])
    for choice in dict.fromkeys(expanded):
        localized_key = f"{key}[{choice}]"
        if localized_key in section:
            return unescape(section[localized_key])
    return unescape(section.get(key, ""))


home = Path(pwd.getpwuid(os.getuid()).pw_dir)
roots = [
    home / ".local/share/applications",
    home / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path("/var/lib/snapd/desktop/applications"),
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]
for data_dir in os.environ.get("XDG_DATA_DIRS", "").split(":"):
    path = Path(data_dir)
    # /app and /run paths belong to the container, not the host process.
    if path.is_absolute() and path.parts[:2] not in (("/", "app"), ("/", "run")):
        roots.append(path / "applications")

desktops = set(filter(None, os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")))
seen_roots = set()
seen_ids = set()
records = []
for root in roots:
    root_key = str(root)
    if root_key in seen_roots or not root.is_dir():
        continue
    seen_roots.add(root_key)
    try:
        paths = sorted(root.rglob("*.desktop"))
    except OSError:
        continue
    for path in paths:
        try:
            desktop_id = str(path.relative_to(root)).replace(os.sep, "-")
        except ValueError:
            continue
        if desktop_id in seen_ids:
            continue
        seen_ids.add(desktop_id)
        parser = configparser.RawConfigParser(interpolation=None, strict=False)
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                parser.read_file(stream)
        except (OSError, configparser.Error):
            continue
        if not parser.has_section("Desktop Entry"):
            continue
        entry = parser["Desktop Entry"]
        # Hidden masks a lower-priority entry with the same desktop id.
        if truth(entry.get("Hidden", "false")):
            continue
        if entry.get("Type", "Application") != "Application":
            continue
        if truth(entry.get("NoDisplay", "false")):
            continue
        only = set(filter(None, entry.get("OnlyShowIn", "").split(";")))
        excluded = set(filter(None, entry.get("NotShowIn", "").split(";")))
        if only and desktops.isdisjoint(only):
            continue
        if desktops.intersection(excluded):
            continue
        name = localized(entry, "Name")
        if not name:
            continue
        records.append({
            "id": desktop_id,
            "name": name,
            "description": localized(entry, "Comment") or None,
            "icon": entry.get("Icon") or None,
        })

print(json.dumps(records, ensure_ascii=False))
'''


class HostScanError(Exception):
    """The host inventory could not be obtained or decoded."""


def scan() -> list[object]:
    try:
        completed = subprocess.run(
            [*sandbox.HOST_SPAWN, "python3", "-c", _SCRIPT],
            check=True,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
        records = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise HostScanError from exc
    if not isinstance(records, list):
        raise HostScanError
    return records

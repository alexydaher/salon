# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed application discovery across the Flatpak boundary."""

from __future__ import annotations

import json
import subprocess

from salon.core.model import LaunchKind
from salon.services import appinfo, host_appinfo


def test_flatpak_scans_host_desktop_entries(monkeypatch) -> None:
    records = [
        {
            "id": "org.gnome.Nautilus.desktop",
            "name": "Files",
            "description": "Access and organize files",
            "icon": "org.gnome.Nautilus",
        },
        {
            "id": "org.gnome.Calculator.desktop",
            "name": "Calculator",
            "description": None,
            "icon": "org.gnome.Calculator",
        },
    ]
    calls: list[list[str]] = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return subprocess.CompletedProcess(argv, 0, json.dumps(records), "")

    monkeypatch.setattr(appinfo.sandbox, "in_flatpak", lambda: True)
    monkeypatch.setattr(host_appinfo.subprocess, "run", run)

    tiles = appinfo.scan_installed()

    assert calls[0][:3] == ["flatpak-spawn", "--host", "python3"]
    assert [tile.title for tile in tiles] == ["Calculator", "Files"]
    files = tiles[1]
    assert files.id == "app:org.gnome.Nautilus.desktop"
    assert files.subtitle == "Access and organize files"
    assert files.icon_name == "org.gnome.Nautilus"
    assert files.launch.kind is LaunchKind.DESKTOP
    assert files.launch.target == "org.gnome.Nautilus.desktop"


def test_flatpak_falls_back_to_gio_when_host_scan_fails(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr(appinfo.sandbox, "in_flatpak", lambda: True)
    monkeypatch.setattr(
        host_appinfo.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("flatpak-spawn missing")),
    )
    monkeypatch.setattr(appinfo, "_scan_local", lambda: sentinel)

    assert appinfo._scan() is sentinel


def test_native_scan_does_not_spawn_a_host_helper(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr(appinfo.sandbox, "in_flatpak", lambda: False)
    monkeypatch.setattr(appinfo, "_scan_local", lambda: sentinel)
    monkeypatch.setattr(
        host_appinfo.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("host helper ran")),
    )

    assert appinfo._scan() is sentinel

# SPDX-License-Identifier: GPL-3.0-or-later
"""Synchronous host-health probe. Call only from a worker thread."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from salon.core import sandbox
from salon.core.health import StorageReading, TemperatureReading

_HOST_SCRIPT = r'''
import glob, json, os, shutil
def number(path):
    try:
        return float(open(path, encoding="ascii").read().strip()) / 1000
    except (OSError, ValueError):
        return None
def text(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read().strip()
    except OSError:
        return ""
readings = []
for path in glob.glob("/sys/class/hwmon/hwmon*/temp*_input"):
    stem = path[:-6]
    temp = number(path)
    if temp is None or not -20 <= temp <= 150: continue
    source = text(stem + "label") or text(path.rsplit("/", 1)[0] + "/name") or "System"
    warning = number(stem + "max") or 85
    critical = number(stem + "crit") or max(warning + 10, 95)
    if not 30 <= warning <= 150: warning = 85
    if not 30 <= critical <= 150: critical = 95
    if warning >= critical: warning = critical - 10
    readings.append((temp, warning, critical, source))
for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
    root = path.rsplit("/", 1)[0]
    temp = number(path)
    if temp is None or not -20 <= temp <= 150: continue
    source = text(root + "/type") or "System"
    trips = [(number(p), text(p.replace("_temp", "_type")))
             for p in glob.glob(root + "/trip_point_*_temp")]
    passive = [v for v, kind in trips if v is not None and 30 <= v <= 150
               and kind in ("passive", "hot")]
    criticals = [v for v, kind in trips if v is not None and 30 <= v <= 150
                 and kind == "critical"]
    critical = min(criticals) if criticals else 95
    warning = min(passive) if passive else critical - 10
    if warning >= critical: warning = critical - 10
    readings.append((temp, warning, critical, source))
paths = ["/", os.path.expanduser("~")]
storages = []
devices = set()
for path in paths:
    try:
        device = os.stat(path).st_dev
        if device in devices: continue
        devices.add(device)
        usage = shutil.disk_usage(path)
        storages.append([usage.total, usage.free])
    except OSError:
        pass
print(json.dumps({"storages": storages, "temperatures": readings}))
'''


def _number(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="ascii").strip()) / 1000.0
    except (OSError, ValueError):
        return None


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _native_temperatures() -> list[TemperatureReading]:
    readings: list[TemperatureReading] = []
    for path in Path("/sys/class/hwmon").glob("hwmon*/temp*_input"):
        temperature = _number(path)
        if temperature is None or not -20 <= temperature <= 150:
            continue
        prefix = path.name.removesuffix("input")
        source = _text(path.with_name(prefix + "label")) or _text(path.parent / "name") or "System"
        warning = _number(path.with_name(prefix + "max")) or 85.0
        critical = _number(path.with_name(prefix + "crit")) or max(warning + 10.0, 95.0)
        warning = warning if 30 <= warning <= 150 else 85.0
        critical = critical if 30 <= critical <= 150 else 95.0
        if warning >= critical:
            warning = critical - 10.0
        readings.append(TemperatureReading(temperature, warning, critical, source))
    for temp_path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        temperature = _number(temp_path)
        if temperature is None or not -20 <= temperature <= 150:
            continue
        root = temp_path.parent
        trips = [
            (_number(path), _text(path.with_name(path.name.replace("_temp", "_type"))))
            for path in root.glob("trip_point_*_temp")
        ]
        passive = [value for value, kind in trips if value is not None
                   and 30 <= value <= 150 and kind in ("passive", "hot")]
        criticals = [value for value, kind in trips if value is not None
                     and 30 <= value <= 150 and kind == "critical"]
        critical = min(criticals) if criticals else 95.0
        warning = min(passive) if passive else critical - 10.0
        if warning >= critical:
            warning = critical - 10.0
        readings.append(
            TemperatureReading(temperature, warning, critical, _text(root / "type") or "System")
        )
    return readings


def _select_temperature(readings: list[TemperatureReading]) -> TemperatureReading | None:
    concerning = [reading for reading in readings if reading.severity != "normal"]
    if not concerning:
        return None
    rank = {"normal": 0, "warning": 1, "critical": 2}
    return max(concerning, key=lambda reading: (rank[reading.severity], reading.celsius))


def _select_storage(readings: list[StorageReading]) -> StorageReading | None:
    if not readings:
        return None
    rank = {"normal": 0, "warning": 1, "critical": 2}
    return max(
        readings,
        key=lambda reading: (
            rank[reading.severity],
            -(reading.free_bytes / reading.total_bytes) if reading.total_bytes else 0,
        ),
    )


def _host_probe() -> tuple[StorageReading | None, TemperatureReading | None]:
    try:
        result = subprocess.run(
            [*sandbox.HOST_SPAWN, "python3", "-c", _HOST_SCRIPT],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
        payload = json.loads(result.stdout)
        storages = [StorageReading(int(total), int(free)) for total, free in payload["storages"]]
        temperatures = [TemperatureReading(*reading) for reading in payload["temperatures"]]
        return _select_storage(storages), _select_temperature(temperatures)
    except (
        OSError, subprocess.SubprocessError, ValueError, TypeError,
        KeyError, json.JSONDecodeError,
    ):
        return None, None


def probe() -> tuple[StorageReading | None, TemperatureReading | None]:
    if sandbox.in_flatpak():
        return _host_probe()
    storages: list[StorageReading] = []
    devices: set[int] = set()
    for path in (Path("/"), Path.home()):
        try:
            device = path.stat().st_dev
            if device in devices:
                continue
            devices.add(device)
            usage = shutil.disk_usage(path)
            storages.append(StorageReading(usage.total, usage.free))
        except OSError:
            continue
    return _select_storage(storages), _select_temperature(_native_temperatures())

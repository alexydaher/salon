# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn live system readings into the compact facts drawn in the rail."""

from __future__ import annotations

from salon.core import sink_names
from salon.core.health import StorageReading, TemperatureReading
from salon.core.status_card import StatusItem, battery_priority, network_value
from salon.services.audio_status import AudioStatus
from salon.services.battery import BatteryStatus
from salon.services.device_battery import DeviceBatteryStatus
from salon.services.netinfo import NetworkStatus


def network_item(status: NetworkStatus) -> StatusItem | None:
    if not status.available:
        return None
    value, priority, tone = network_value(status.strength, status.state)
    return StatusItem(
        "network", status.icon_name, status.name or status.kind or "Network",
        value, status.phrase, priority, tone,
    )


def battery_item(status: BatteryStatus) -> StatusItem | None:
    if not status.present:
        return None
    priority, tone = battery_priority(status.percent, charging=status.charging)
    return StatusItem(
        "battery", status.icon_name, "Battery", f"{round(status.percent)}%",
        status.phrase, priority, tone,
    )


def audio_item(status: AudioStatus) -> StatusItem | None:
    if not status.available:
        return None
    if status.no_outputs:
        return StatusItem(
            "audio", "audio-volume-muted-symbolic", "Audio", "No output",
            "No audio output is available", 95, "danger",
        )
    output = sink_names.short_name(status.description)
    value = "Muted" if status.muted else output
    phrase = f"Sound is muted; output: {output}" if status.muted else f"Sound output: {output}"
    return StatusItem(
        "audio", "audio-volume-muted-symbolic" if status.muted else "audio-volume-high-symbolic",
        "Audio", value, phrase, 84 if status.muted else 58,
        "warning" if status.muted else "normal",
    )


def device_battery_item(statuses: tuple[DeviceBatteryStatus, ...]) -> StatusItem | None:
    if not statuses:
        return None
    status = statuses[0]
    priority, tone = battery_priority(status.percent, charging=False)
    phrase = f"{status.name} battery {status.percent}%"
    if len(statuses) > 1:
        phrase += f"; lowest of {len(statuses)} connected devices"
    return StatusItem(
        "device-battery", status.icon_name, status.name, f"{status.percent}%",
        phrase, priority, tone,
    )


def storage_item(reading: StorageReading | None) -> StatusItem | None:
    if reading is None or reading.severity == "normal":
        return None
    critical = reading.severity == "critical"
    return StatusItem(
        "storage", "drive-harddisk-symbolic", "Storage", reading.value,
        f"Storage is low: {reading.value}", 98 if critical else 86,
        "danger" if critical else "warning",
    )


def temperature_item(reading: TemperatureReading | None) -> StatusItem | None:
    if reading is None or reading.severity == "normal":
        return None
    critical = reading.severity == "critical"
    return StatusItem(
        "temperature", "dialog-warning-symbolic", "Temperature",
        f"{'Critical' if critical else 'Hot'} {reading.value}",
        f"{reading.source} is at {reading.value}; performance may be reduced",
        99 if critical else 87, "danger" if critical else "warning",
    )


def running_item(count: int) -> StatusItem | None:
    count = max(0, count)
    if not count:
        return None
    return StatusItem(
        "applications", "view-grid-symbolic", "Apps still running", str(count),
        f"{count} applications still running", 42,
    )


def controls_item(
    controllers: int, phone: bool, *, controller_battery_visible: bool
) -> StatusItem | None:
    if not phone and (not controllers or controller_battery_visible):
        return None
    if phone and controllers:
        value, phrase = "Pad + phone", "Controller and phone connected"
    elif phone:
        value, phrase = "Phone", "Phone remote connected"
    else:
        value = "2 controllers" if controllers > 1 else "Controller"
        phrase = "Controller connected"
    return StatusItem(
        "controls", "phone-symbolic" if phone else "input-gaming-symbolic",
        "Controls", value, phrase, 48 if phone else 36,
    )

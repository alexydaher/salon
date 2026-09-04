# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

pytest.importorskip("gi")

from salon.services import device_battery  # noqa: E402


def test_only_connected_controllers_and_audio_devices_are_status_candidates() -> None:
    objects = {
        "/pad": {
            "org.bluez.Device1": {
                "Alias": "DualSense",
                "Class": 0x002508,
                "Connected": True,
            },
            "org.bluez.Battery1": {"Percentage": 18},
        },
        "/phone": {
            "org.bluez.Device1": {
                "Alias": "A phone",
                "Class": 0x000200,
                "Connected": True,
            },
            "org.bluez.Battery1": {"Percentage": 3},
        },
        "/headphones": {
            "org.bluez.Device1": {
                "Alias": "Living Room Headphones",
                "Class": 0x000400,
                "Connected": False,
            },
            "org.bluez.Battery1": {"Percentage": 9},
        },
    }
    assert device_battery.statuses_from_objects(objects) == (
        device_battery.DeviceBatteryStatus("DualSense", "Gamepad", 18),
    )


def test_lowest_connected_device_is_first_and_audio_gets_a_headphone_icon() -> None:
    objects = {
        "/pad": {
            "org.bluez.Device1": {"Alias": "Pad", "Class": 0x002508, "Connected": True},
            "org.bluez.Battery1": {"Percentage": 60},
        },
        "/audio": {
            "org.bluez.Device1": {"Alias": "Buds", "Class": 0x000400, "Connected": True},
            "org.bluez.Battery1": {"Percentage": 35},
        },
    }
    statuses = device_battery.statuses_from_objects(objects)
    assert statuses[0].name == "Buds"
    assert statuses[0].icon_name == "audio-headphones-symbolic"

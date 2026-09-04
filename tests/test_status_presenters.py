# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

pytest.importorskip("gi")

from salon.core import status as network_state  # noqa: E402
from salon.core.health import GIB, StorageReading, TemperatureReading  # noqa: E402
from salon.services.audio_status import AudioStatus  # noqa: E402
from salon.services.device_battery import DeviceBatteryStatus  # noqa: E402
from salon.services.network_status import NetworkStatus  # noqa: E402
from salon.ui import status_presenters  # noqa: E402


def test_limited_internet_never_hides_behind_strong_wifi_wording() -> None:
    item = status_presenters.network_item(
        NetworkStatus(
            "Sofa", "Wi-Fi", "Connected, but limited",
            state=network_state.CONNECTIVITY_LIMITED, strength=95,
        )
    )
    assert item is not None
    assert (item.value, item.tone) == ("No internet", "warning")


def test_muted_audio_keeps_the_real_output_in_its_explanation() -> None:
    item = status_presenters.audio_item(
        AudioStatus(True, "Audio Controller HDMI / DisplayPort 2 Output", muted=True)
    )
    assert item is not None
    assert item.value == "Muted"
    assert "HDMI 2" in item.phrase


def test_health_rows_exist_only_when_there_is_something_to_act_on() -> None:
    assert status_presenters.storage_item(StorageReading(100 * GIB, 30 * GIB)) is None
    assert status_presenters.temperature_item(TemperatureReading(65)) is None
    assert status_presenters.storage_item(StorageReading(100 * GIB, 5 * GIB)).tone == "warning"
    assert status_presenters.temperature_item(TemperatureReading(96)).tone == "danger"


def test_a_device_battery_replaces_redundant_controller_connection_text() -> None:
    battery = (DeviceBatteryStatus("DualSense", "Gamepad", 72),)
    assert status_presenters.device_battery_item(battery) is not None
    assert status_presenters.controls_item(1, False, controller_battery_visible=True) is None
    assert status_presenters.controls_item(1, True, controller_battery_visible=True) is not None

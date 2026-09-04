# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from salon.core.health import GIB, StorageReading, TemperatureReading


def test_storage_requires_both_a_small_share_and_a_small_absolute_amount() -> None:
    assert StorageReading(2_000 * GIB, 20 * GIB).severity == "normal"
    assert StorageReading(32 * GIB, 5 * GIB).severity == "normal"
    assert StorageReading(100 * GIB, 9 * GIB).severity == "warning"
    assert StorageReading(100 * GIB, 2 * GIB).severity == "critical"


def test_storage_wording_keeps_useful_precision_only_below_ten_gib() -> None:
    assert StorageReading(100 * GIB, int(6.25 * GIB)).value == "6.2 GB free"
    assert StorageReading(500 * GIB, 42 * GIB).value == "42 GB free"


def test_sensor_thresholds_win_over_one_global_temperature_guess() -> None:
    assert TemperatureReading(79, warning_c=80, critical_c=95).severity == "normal"
    assert TemperatureReading(80, warning_c=80, critical_c=95).severity == "warning"
    assert TemperatureReading(95, warning_c=80, critical_c=95).severity == "critical"

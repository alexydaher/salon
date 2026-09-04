# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from salon.core import status
from salon.core.status_card import StatusItem, battery_priority, choose, network_value


def _item(key: str, priority: int) -> StatusItem:
    return StatusItem(key, "dialog-information-symbolic", key, "value", key, priority)


def test_only_four_highest_priority_facts_are_kept_in_stable_order() -> None:
    items = (
        _item("network", 60), _item("audio", 58), _item("battery", 52),
        _item("applications", 42), _item("hot", 87),
    )
    assert [item.key for item in choose(items)] == ["network", "audio", "battery", "hot"]


def test_network_failure_outranks_signal_strength() -> None:
    assert network_value(95, status.CONNECTIVITY_PORTAL) == ("Sign in", 90, "warning")
    assert network_value(95, status.CONNECTIVITY_LIMITED) == ("No internet", 90, "warning")
    assert network_value(95, status.CONNECTIVITY_NONE) == ("Offline", 96, "danger")


def test_weak_wifi_is_visible_without_being_called_an_outage() -> None:
    assert network_value(20, status.CONNECTIVITY_FULL) == ("Weak", 72, "warning")


def test_device_battery_becomes_more_important_as_it_runs_down() -> None:
    assert battery_priority(80, charging=False) == (52, "normal")
    assert battery_priority(40, charging=False) == (76, "warning")
    assert battery_priority(10, charging=False) == (94, "danger")
    assert battery_priority(10, charging=True) == (46, "normal")

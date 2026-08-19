# SPDX-License-Identifier: GPL-3.0-or-later
"""The top bar's glyph table (§6.9).

Two halves. The first is the mapping itself — pure, no display needed. The
second checks that every name the mapping can return is a real icon in the
current theme, which is the failure this table exists to prevent: a name
with a typo in it renders as a broken-image square in the corner of a
television, and nothing logs a word about it.
"""

from __future__ import annotations

import pytest

from salon.core import status


def test_wifi_bars_step_at_the_documented_strengths() -> None:
    assert status.wifi_icon(0) == "network-wireless-signal-none-symbolic"
    assert status.wifi_icon(5) == "network-wireless-signal-none-symbolic"
    assert status.wifi_icon(6) == "network-wireless-signal-weak-symbolic"
    assert status.wifi_icon(25) == "network-wireless-signal-weak-symbolic"
    assert status.wifi_icon(26) == "network-wireless-signal-ok-symbolic"
    assert status.wifi_icon(50) == "network-wireless-signal-ok-symbolic"
    assert status.wifi_icon(51) == "network-wireless-signal-good-symbolic"
    assert status.wifi_icon(75) == "network-wireless-signal-good-symbolic"
    assert status.wifi_icon(100) == "network-wireless-signal-excellent-symbolic"


def test_unknown_strength_is_not_a_weak_signal() -> None:
    """The access point can decline to answer. Claiming no bars would say
    the connection is failing when nothing of the sort has been observed."""
    assert status.wifi_icon(-1) == "network-wireless-signal-good-symbolic"


def test_no_primary_connection_is_offline() -> None:
    assert (
        status.network_glyph("", -1, status.CONNECTIVITY_NONE) == "network-offline-symbolic"
    )


def test_no_network_manager_draws_nothing_at_all() -> None:
    """An empty name hides the glyph. Salon doesn't know the state, and an
    icon that guesses is worse than a gap in the bar."""
    assert status.network_glyph("Wi-Fi", 80, status.CONNECTIVITY_FULL, available=False) == ""


def test_wired_and_vpn_have_their_own_glyphs() -> None:
    assert (
        status.network_glyph("Ethernet", -1, status.CONNECTIVITY_FULL)
        == "network-wired-symbolic"
    )
    assert status.network_glyph("VPN", -1, status.CONNECTIVITY_FULL) == "network-vpn-symbolic"
    assert (
        status.network_glyph("Mobile broadband", -1, status.CONNECTIVITY_FULL)
        == "network-wired-symbolic"
    )


@pytest.mark.parametrize(
    "state", [status.CONNECTIVITY_PORTAL, status.CONNECTIVITY_LIMITED]
)
def test_a_connection_with_no_route_says_so(state: int) -> None:
    """Associated but not online is the state that actually explains why a
    tile won't load, so it must not look like a healthy connection."""
    assert status.network_glyph("Wi-Fi", 90, state) == "network-wireless-no-route-symbolic"
    assert status.network_glyph("Ethernet", -1, state) == "network-wired-no-route-symbolic"
    assert status.network_glyph("VPN", -1, state) == "network-vpn-no-route-symbolic"


def test_battery_levels_round_to_the_icons_that_exist() -> None:
    assert status.battery_glyph(0, charging=False) == "battery-level-0-symbolic"
    assert status.battery_glyph(4, charging=False) == "battery-level-0-symbolic"
    assert status.battery_glyph(5, charging=False) == "battery-level-10-symbolic"
    assert status.battery_glyph(67, charging=False) == "battery-level-70-symbolic"
    assert status.battery_glyph(100, charging=False) == "battery-level-100-symbolic"


def test_battery_charging_and_full_are_distinct() -> None:
    assert status.battery_glyph(40, charging=True) == "battery-level-40-charging-symbolic"
    assert status.battery_glyph(100, charging=True) == "battery-level-100-charged-symbolic"
    assert status.battery_glyph(96, charging=False, full=True) == (
        "battery-level-100-charged-symbolic"
    )


def test_phrases_lead_with_the_thing_being_looked_for() -> None:
    assert status.battery_phrase(42, charging=False) == "Battery 42%"
    assert status.battery_phrase(42, charging=True) == "Battery 42%, charging"
    assert status.battery_phrase(100, charging=True, full=True) == "Battery full"
    assert status.network_phrase("Sofa", "Wi-Fi", status.CONNECTIVITY_FULL) == "Wi-Fi: Sofa"
    assert (
        status.network_phrase("", "", status.CONNECTIVITY_NONE)
        == "Not connected to a network"
    )
    assert "no route" in status.network_phrase("Sofa", "Wi-Fi", status.CONNECTIVITY_PORTAL)


_EVERY_NAME = sorted(
    {status.wifi_icon(strength) for strength in (-1, 0, 10, 40, 60, 100)}
    | {
        status.network_glyph(kind, 50, state)
        for kind in ("", "Wi-Fi", "Ethernet", "VPN", "Mobile broadband")
        for state in (
            status.CONNECTIVITY_NONE,
            status.CONNECTIVITY_PORTAL,
            status.CONNECTIVITY_LIMITED,
            status.CONNECTIVITY_FULL,
        )
    }
    | {
        status.battery_glyph(percent, charging=charging)
        for percent in range(0, 101, 5)
        for charging in (False, True)
    }
    | {status.battery_glyph(100, charging=False, full=True)}
)


@pytest.mark.parametrize("icon_name", [name for name in _EVERY_NAME if name])
def test_every_glyph_exists_in_the_icon_theme(icon_name: str) -> None:
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gtk

    if not Gtk.init_check():
        pytest.skip("no display; the icon theme can't be resolved headlessly")
    display = Gdk.Display.get_default()
    if display is None:
        pytest.skip("no display; the icon theme can't be resolved headlessly")
    theme = Gtk.IconTheme.get_for_display(display)
    assert theme.has_icon(icon_name), f"{icon_name} is not in the icon theme"

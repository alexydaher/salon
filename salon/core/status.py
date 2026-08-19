# SPDX-License-Identifier: GPL-3.0-or-later
"""What the top bar's network and battery glyphs are, in pure functions.

§6.9 asks for network and battery indicators beside the clock. The reading
itself is D-Bus work that belongs in `services/` (NetworkManager, UPower),
but *which glyph and which words a reading means* is a table — and a table
is worth testing, because the failure mode is an icon name that doesn't
exist in the theme, which renders as a broken-image square on a screen
nobody is sitting close enough to interrogate.

Every name returned here is a stock symbolic icon that ships with Adwaita;
`tests/test_status.py` asserts the mapping and the icon test asserts the
names resolve. No `gi` here, like everything else under `core/`.
"""

from __future__ import annotations

# NMConnectivityState, the values `Connectivity` reports.
CONNECTIVITY_UNKNOWN = 0
CONNECTIVITY_NONE = 1
CONNECTIVITY_PORTAL = 2
CONNECTIVITY_LIMITED = 3
CONNECTIVITY_FULL = 4

# Where the four Wi-Fi bars change, in NetworkManager's 0-100 strength.
_WIFI_STEPS = ((5, "none"), (25, "weak"), (50, "ok"), (75, "good"))

# Below this, on battery, the glyph turns the danger colour. GNOME warns at
# 20%; a television that is running off a battery at all is already unusual,
# so this only has to be loud enough to explain an imminent shutdown.
BATTERY_LOW_PERCENT = 15.0


def wifi_icon(strength: int) -> str:
    """Strength is NetworkManager's 0-100. A negative value means the AP
    didn't answer, which is not the same as a weak signal — treat it as a
    plain wireless connection rather than claiming zero bars."""
    if strength < 0:
        return "network-wireless-signal-good-symbolic"
    for ceiling, name in _WIFI_STEPS:
        if strength <= ceiling:
            return f"network-wireless-signal-{name}-symbolic"
    return "network-wireless-signal-excellent-symbolic"


def network_glyph(kind: str, strength: int, connectivity: int, *, available: bool = True) -> str:
    """The icon for one primary connection. `kind` is netinfo's human name
    ("Wi-Fi", "Ethernet", "VPN", …); an empty one means nothing is up."""
    if not available:
        return ""
    if not kind:
        return "network-offline-symbolic"
    limited = connectivity in (CONNECTIVITY_PORTAL, CONNECTIVITY_LIMITED)
    if kind == "Wi-Fi":
        return "network-wireless-no-route-symbolic" if limited else wifi_icon(strength)
    if kind == "VPN":
        return "network-vpn-no-route-symbolic" if limited else "network-vpn-symbolic"
    return "network-wired-no-route-symbolic" if limited else "network-wired-symbolic"


def battery_glyph(percent: float, *, charging: bool, full: bool = False) -> str:
    """Adwaita's battery icons come in ten-percent steps, plus a dedicated
    one for charged-and-plugged-in."""
    # Half-up, not Python's round(): round(0.5) is 0 there, so a battery at
    # 5% would draw the same glyph as one at 0%.
    level = max(0, min(100, int(percent / 10.0 + 0.5) * 10))
    if full or (charging and level >= 100):
        return "battery-level-100-charged-symbolic"
    return f"battery-level-{level}{'-charging' if charging else ''}-symbolic"


def battery_phrase(percent: float, *, charging: bool, full: bool = False) -> str:
    """The tooltip, and what a screen reader says. Percent first, because
    that's the number being looked for."""
    if full:
        return "Battery full"
    if charging:
        return f"Battery {percent:.0f}%, charging"
    return f"Battery {percent:.0f}%"


def network_phrase(name: str, kind: str, connectivity: int, *, available: bool = True) -> str:
    if not available:
        return "Network status unavailable"
    if not kind:
        return "Not connected to a network"
    where = f"{kind}: {name}" if name else kind
    if connectivity in (CONNECTIVITY_PORTAL, CONNECTIVITY_LIMITED):
        return f"{where} — connected, but there's no route to the internet"
    return where

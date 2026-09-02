# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused settings panel builder."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from salon.services import netinfo, wifi  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    GroupRow,
    InfoRow,
    SettingsRow,
    opens_gnome,
    opens_panel,
)


def network_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    """Status Salon reads itself, configuration it hands to GNOME.

    The status arrives asynchronously (NetworkManager is on the system bus),
    so the panel builds with a placeholder and rebuilds once when the answer
    lands — guarded against rebuilding on an unchanged value, because
    context.rebuild() reconstructs every row and an unconditional callback
    would loop.
    """
    status: list[netinfo.NetworkStatus] = []

    def on_status(found: netinfo.NetworkStatus) -> None:
        if status and status[0] == found:
            return
        status[:] = [found]
        context.rebuild()

    def build() -> list[SettingsRow]:
        netinfo.status_async(on_status)
        current = status[0] if status else None
        return [
            GroupRow("Status"),
            InfoRow(
                "Connection",
                current.summary if current else "Checking…",
                detail=current.connectivity if current else "",
                # The same glyph the top bar is showing, so the row and the
                # bar can never disagree about what the connection is.
                icon_name=(current.icon_name if current else "") or "network-wireless-symbolic",
            ),
            GroupRow("Wi-Fi"),
            opens_panel(
                "Choose a network",
                lambda: context.push(_wifi_panel(context)),
            ),
            opens_gnome(
                "Wi-Fi, in detail",
                lambda: context.open_control_center("wifi"),
                detail="Hidden and enterprise networks",
            ),
            GroupRow("Everything else"),
            opens_gnome(
                "Wired and VPN",
                lambda: context.open_control_center("network"),
            ),
        ]

    def summary() -> str:
        return status[0].summary if status else ""

    return Panel(
        title="Network",
        build=build,
        summary=summary,
        panel_id="network",
        icon_name="network-wireless-symbolic",
    )


def _wifi_panel(context: SettingsContext) -> Panel:
    """The list of networks in range.

    Rebuilt from a cached scan rather than rescanning on every rebuild: the
    panel rebuilds whenever anything changes, a scan takes seconds, and a
    list that reshuffles itself under the cursor as signal strengths drift
    is unusable with a D-pad.
    """
    service = wifi.WifiService()
    state: dict[str, object] = {"points": [], "error": "", "scanned": False, "asking": False}

    def on_scanned(points: list[wifi.AccessPoint], error: str) -> None:
        state.update(points=points, error=error, scanned=True, asking=False)
        context.rebuild()

    def request() -> None:
        # Guarded: `build` runs on every rebuild, and a rebuild that starts
        # another scan which finishes and rebuilds again is a loop.
        if state["asking"]:
            return
        state["asking"] = True
        service.list_networks(on_scanned)

    def rescan() -> None:
        state["scanned"] = False
        request()
        context.rebuild()

    def build() -> list[SettingsRow]:
        if not state["scanned"]:
            request()
            return [InfoRow("Looking for networks…", "", detail="This takes a few seconds")]
        error = str(state["error"])
        if error:
            return [
                InfoRow("Couldn't look for networks", "", detail=error),
                ActionRow("Try again", rescan),
            ]
        points = list(state["points"])  # type: ignore[arg-type]
        if not points:
            return [
                InfoRow("Nothing in range", "", detail="No wireless networks were found"),
                ActionRow("Look again", rescan),
            ]
        rows: list[SettingsRow] = [
            ActionRow(
                point.ssid,
                lambda p=point: _join(context, service, p),
                value=point.summary,
                icon_name=point.icon_name,
            )
            for point in points
        ]
        rows.append(ActionRow("Look again", rescan))
        return rows

    return Panel(title="Wi-Fi", build=build)


def _join(context: SettingsContext, service: wifi.WifiService, point: wifi.AccessPoint) -> None:
    """Join one network, asking for the password only if it wants one."""

    def attempt(password: str) -> None:
        context.toast(f"Connecting to {point.ssid}…")
        service.connect(point, password, on_result)

    def on_result(ok: bool, message: str) -> None:
        context.toast(message if ok else f"Couldn't join {point.ssid}: {message}")

    if not point.secured:
        attempt("")
        return

    def got_password(value: str | None) -> None:
        if value is None:
            return
        attempt(value)

    context.edit_text(f"Password for {point.ssid}", "", got_password)

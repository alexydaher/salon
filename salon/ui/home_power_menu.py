# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow: the second level of the MENU menu.

Everything that ends the session lives here, one row deeper than the menu
MENU opens. It was a flat list before: Settings, the phone, Suspend, Log
Out, Restart, Shut Down, About and Exit, walked with an accelerating
auto-repeat. Two rows of that list are what anyone opens MENU for and four
of them turn the machine off, which is a poor thing to put under a held
direction key.
"""

from salon.core import session
from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    Callable,
    MenuFrame,
    SystemMenuItem,
    power,
)


class HomePowerMenuController(ServiceComponent):
    def _power_menu_items(self) -> list[SystemMenuItem]:
        """Everything that ends the session, behind one row of its own.

        Each is offered only if logind says this account may do it, which is
        why the list is built rather than declared — and why "Power…" is
        absent entirely on a machine that permits none of them.
        """
        # Name logind refusals instead of closing the menu with no result.
        def fail(what: str) -> Callable[[str], None]:
            return lambda message: self._owner._toast(f"{what} didn't happen: {message}")

        items: list[SystemMenuItem] = []
        if power.can_suspend():
            items.append(
                SystemMenuItem(
                    "Suspend",
                    lambda: power.suspend(fail("Suspend")),
                    icon_name="media-playback-pause-symbolic",
                )
            )
        # the way to get from Salon to another session — the desktop, a
        # different user — without powering the machine down. "Exit to
        # Desktop" below leaves the process; this leaves the session, which
        # under the Salon unit's Restart=always is the only one of the two
        # that actually ends up somewhere else.
        if power.can_log_out():
            items.append(
                SystemMenuItem(
                    "Log Out",
                    icon_name="system-log-out-symbolic",
                    detail="End this session and return to the login screen",
                    submenu=lambda: self._confirmation_frame(
                        "Log Out", lambda: power.log_out(fail("Log out"))
                    ),
                )
            )
        if power.can_reboot():
            items.append(
                SystemMenuItem(
                    "Restart",
                    danger=True,
                    icon_name="system-reboot-symbolic",
                    submenu=lambda: self._confirmation_frame(
                        "Restart", lambda: power.reboot(fail("Restart"))
                    ),
                )
            )
        if power.can_power_off():
            items.append(
                SystemMenuItem(
                    "Shut Down",
                    danger=True,
                    icon_name="system-shutdown-symbolic",
                    submenu=lambda: self._confirmation_frame(
                        "Shut Down", lambda: power.power_off(fail("Shut down"))
                    ),
                )
            )
        if not session.is_session():
            items.append(
                SystemMenuItem(
                    "Exit Salon",
                    danger=True,
                    icon_name="application-exit-symbolic",
                    detail="Close Salon and return to the desktop",
                    submenu=lambda: self._confirmation_frame(
                        "Exit Salon", self._owner._application.quit
                    ),
                )
            )
        return items

    def _show_power_menu(self) -> None:
        """The second level, titled, with BACK returning to the first.

        Titled because a card of five words with no heading, arrived at by
        pressing OK, is a card that could be anything.
        """
        menu = self._owner._system_menu
        if menu.get_visible() and menu.current_frame_id == "root":
            menu.push_frame(MenuFrame("power", "Power", self._power_menu_items()))
            return
        root = self._owner._build_system_menu_items()
        power_index = next((i for i, item in enumerate(root) if item.submenu is not None), 0)
        menu.set_items(root, title="Salon", selected=power_index)
        menu.push_frame(MenuFrame("power", "Power", self._power_menu_items()))
        self._owner._system_menu.show()
        self._owner._tile_menu.hide()

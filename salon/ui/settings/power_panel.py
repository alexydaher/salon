# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → System → Power: the five presses that end the session.

Behind one row rather than loose at the bottom of System, which is the same
shape MENU's own menu took on 2026-08-25 and for the same reason. They were
five rows below the fold, typographically identical to "Date and time", and
DOWN from "Keep screen awake after launching" landed on Suspend.

Every one of them is filtered on what logind will actually permit, so a
machine that cannot reboot does not offer to.
"""

from __future__ import annotations

from collections.abc import Callable

from salon.core import session
from salon.ui.settings.context import Panel, SettingsContext, confirm_panel
from salon.ui.settings.widgets import ActionRow, InfoRow, SettingsRow


def power_panel(context: SettingsContext) -> Panel:
    from salon.services import power

    def fail(what: str) -> Callable[[str], None]:
        """Named in the failure message, because logind refusing to suspend
        and Salon never having asked look identical from the sofa."""
        return lambda message: context.toast(f"{what} didn't happen: {message}")

    def confirmed(question: str, label: str, run: Callable[[], None]) -> Callable[[], None]:
        return lambda: context.push(confirm_panel(context, question, label, run))

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = []
        if power.can_suspend():
            rows.append(
                ActionRow(
                    "Suspend",
                    lambda: power.suspend(fail("Suspend")),
                    detail="Sleeps now; a button press wakes it",
                )
            )
        if power.can_log_out():
            rows.append(
                ActionRow(
                    "Log out",
                    confirmed(
                        "Log out and end this session?",
                        "Log out",
                        lambda: power.log_out(fail("Log out")),
                    ),
                    detail="Ends the session and returns to the login screen",
                    danger=True,
                )
            )
        if power.can_reboot():
            rows.append(
                ActionRow(
                    "Restart",
                    confirmed(
                        "Restart the computer?", "Restart", lambda: power.reboot(fail("Restart"))
                    ),
                    danger=True,
                )
            )
        if power.can_power_off():
            rows.append(
                ActionRow(
                    "Shut down",
                    confirmed(
                        "Shut down the computer?",
                        "Shut Down",
                        lambda: power.power_off(fail("Shut down")),
                    ),
                    danger=True,
                )
            )
        if not session.is_session():
            rows.append(
                ActionRow(
                    "Exit Salon",
                    confirmed(
                        "Exit Salon and return to the desktop?", "Exit Salon", context.quit_app
                    ),
                    # Different in kind from Log out, and the distinction is
                    # invisible unless it is written down: under the session
                    # unit's Restart=always, exiting gets you Salon again.
                    detail="Leaves the launcher; the desktop stays logged in",
                    danger=True,
                )
            )
        if not rows:
            rows.append(
                InfoRow(
                    "Nothing available",
                    "",
                    detail="This account isn't permitted to suspend or power off the computer",
                )
            )
        return rows

    return Panel(title="Power", build=build)

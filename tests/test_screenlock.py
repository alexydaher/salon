# SPDX-License-Identifier: GPL-3.0-or-later
"""The screen lock is only ever touched when Salon *is* the session.

Driven against a stand-in for Gio.Settings rather than the real schema: the
assertion is about the policy's decisions, and writing the live
org.gnome.desktop.screensaver key from a test would reconfigure the machine
running it.
"""

from __future__ import annotations

from salon.services.screenlock import ScreenLockPolicy


class FakeSettings:
    """The two-method slice of Gio.Settings the policy uses."""

    def __init__(self, lock_enabled: bool = True) -> None:
        self.values = {"lock-enabled": lock_enabled}
        self.writes: list[bool] = []

    def get_boolean(self, key: str) -> bool:
        return self.values[key]

    def set_boolean(self, key: str, value: bool) -> None:
        self.values[key] = value
        self.writes.append(value)


def test_a_guest_in_someone_elses_desktop_changes_nothing() -> None:
    settings = FakeSettings(lock_enabled=True)
    policy = ScreenLockPolicy(settings, active=False)

    policy.apply()

    assert settings.writes == []
    assert settings.values["lock-enabled"] is True


def test_a_flatpak_never_changes_the_host_screen_lock() -> None:
    settings = FakeSettings(lock_enabled=True)
    policy = ScreenLockPolicy(settings, active=True, sandboxed=True)

    policy.apply()

    assert settings.writes == []
    assert settings.values["lock-enabled"] is True


def test_the_session_suppresses_the_lock_and_puts_it_back() -> None:
    settings = FakeSettings(lock_enabled=True)
    policy = ScreenLockPolicy(settings, active=True)

    policy.apply()
    assert settings.values["lock-enabled"] is False

    policy.restore()
    assert settings.values["lock-enabled"] is True


def test_a_lock_that_was_already_off_is_not_restored_to_on() -> None:
    """Nothing was taken, so nothing is given back — otherwise Salon would
    switch on a lock the user had deliberately switched off."""
    settings = FakeSettings(lock_enabled=False)
    policy = ScreenLockPolicy(settings, active=True)

    policy.apply()
    policy.restore()

    assert settings.writes == []
    assert settings.values["lock-enabled"] is False


def test_restore_without_apply_does_nothing() -> None:
    settings = FakeSettings(lock_enabled=True)
    policy = ScreenLockPolicy(settings, active=True)

    policy.restore()

    assert settings.writes == []


def test_restore_is_idempotent() -> None:
    """do_shutdown can run more than once in a GApplication's life; the
    second restore must not re-apply a stale remembered value."""
    settings = FakeSettings(lock_enabled=True)
    policy = ScreenLockPolicy(settings, active=True)

    policy.apply()
    policy.restore()
    settings.values["lock-enabled"] = False
    policy.restore()

    assert settings.values["lock-enabled"] is False

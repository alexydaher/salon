#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture interaction states used by the end-to-end UX verification pass."""

from __future__ import annotations

import os
import runpy
import shutil
import tempfile
from pathlib import Path

os.environ.setdefault("SALON_CAPTURE_MODE", "1")
os.environ.setdefault("SALON_CAPTURE_CLOCK", "2026-08-25T20:15:00")
# GSettings, in memory and nowhere else. Every harness here points the XDG
# directories at a temporary tree and it is not enough: a dconf write goes
# over D-Bus to the writer daemon, which resolves the user database from
# *its own* environment, so the value lands in the real session while the
# read comes back out of the empty temp copy. That is how a screenshot run
# turned the corner pairing card off on a live machine and left no trace of
# having done it. Assigned rather than `setdefault`, so an inherited
# GSETTINGS_BACKEND cannot put dconf back underneath us, and set before
# `gi.repository` is imported, which is when the backend is chosen.
os.environ["GSETTINGS_BACKEND"] = "memory"

import gi  # noqa: E402

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib  # noqa: E402

from salon import config  # noqa: E402
from salon.app import SalonApplication  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.ui.search_models import Pane  # noqa: E402
from salon.ui.settings.input_panel import _advanced_input_panel  # noqa: E402
from salon.ui.settings.reorder_panels import reorder_rows_panel  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "build-sdk" / "ux-audit"
CAPTURE = runpy.run_path(str(ROOT / "scripts" / "capture-release-screenshots.py"))["capture"]


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Orca needs time to consume each AT-SPI transition.  Keep normal visual
    # captures quick, while allowing the same real-window journey to be
    # slowed down for a screen-reader audit.
    delay_factor = max(1.0, float(os.environ.get("SALON_CAPTURE_DELAY_FACTOR", "1")))
    with tempfile.TemporaryDirectory(prefix="salon-ux-audit-") as temporary:
        state = Path(temporary)
        for name in ("CONFIG", "CACHE", "DATA", "STATE"):
            os.environ[f"XDG_{name}_HOME"] = str(state / name.lower())
        tile_path = state / "config" / "salon" / "tiles.json"
        tile_path.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "tests" / "fixtures" / "release-tiles.json", tile_path)

        settings = Gio.Settings.new(config.APP_ID)
        settings.set_boolean("onboarding-complete", True)
        settings.set_boolean("fetch-site-icons", False)
        settings.set_boolean("remote-hint", False)
        settings.set_strv("disabled-providers", ["apps", "favourites", "games", "recents"])
        settings.set_double("animation-scale", 0.0)

        app = SalonApplication()
        failures: list[Exception] = []

        def finish(error: Exception | None = None) -> bool:
            if error is not None:
                failures.append(error)
            app.quit()
            return GLib.SOURCE_REMOVE

        def prepare() -> bool:
            window = app.get_active_window()
            if window is None:
                return finish(RuntimeError("Salon did not create a window"))
            window.unfullscreen()
            window.set_default_size(1280, 720)
            home = window.get_content()

            def shot(name: str) -> None:
                CAPTURE(window, OUTPUT / f"{name}.png")

            def settings_reorder() -> None:
                screen = home._settings_screen
                screen.open_at("tiles")
                screen._push(reorder_rows_panel(screen._context))

            def settings_advanced_input() -> None:
                screen = home._settings_screen
                screen._push(_advanced_input_panel(screen._context, home._settings))

            def search_options() -> None:
                home._search._pane = Pane.RESULTS
                home._search._update_selection(animate=False)
                home._search.handle_action(Action.OPTIONS)

            def type_search() -> None:
                home._open_search()
                for key in (Gdk.KEY_m, Gdk.KEY_o, Gdk.KEY_v, Gdk.KEY_i, Gdk.KEY_e):
                    home._search.handle_keyval(key, Gdk.ModifierType(0))

            steps = [
                ("onboarding", lambda: home._onboarding.start(), 350),
                ("system-menu", lambda: (home._onboarding.finish(), home._show_system_menu()), 350),
                ("power-menu", lambda: home._show_power_menu(), 350),
                (
                    "system-confirm",
                    lambda: home._confirm_system_action("Shut Down", lambda: None),
                    350,
                ),
                ("typed-search", lambda: (home._system_menu.hide(), type_search()), 700),
                ("search-options", search_options, 350),
                (
                    "all-apps",
                    lambda: (home._tile_menu.hide(), home._search.close(), home._open_apps()),
                    1200,
                ),
                (
                    "advanced-input",
                    lambda: (
                        home._apps_grid.close(),
                        home._open_settings("input"),
                        settings_advanced_input(),
                    ),
                    450,
                ),
                ("reorder-rows", settings_reorder, 350),
                (
                    "phone-pairing",
                    lambda: (home._settings_screen.close(), home._open_phone_pairing()),
                    500,
                ),
                ("phone-stop-confirm", lambda: home._phone_pairing._request_stop(), 350),
                (
                    "now-playing-detail",
                    lambda: (
                        home._phone_pairing.close(),
                        home._now_playing_status.set_track(
                            "Blue Monday", "New Order", playing=True
                        ),
                    ),
                    1800,
                ),
            ]

            def run_step(index: int) -> bool:
                try:
                    if index:
                        shot(steps[index - 1][0])
                    if index >= len(steps):
                        return finish()
                    _name, action, delay = steps[index]
                    action()
                    GLib.timeout_add(round(delay * delay_factor), run_step, index + 1)
                except Exception as error:  # noqa: BLE001
                    return finish(error)
                return GLib.SOURCE_REMOVE

            return run_step(0)

        GLib.timeout_add_seconds(3, prepare)
        app.run([])
        if failures:
            raise failures[0]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

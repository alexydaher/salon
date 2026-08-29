#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture the four release scenarios from a real mapped Salon window."""
from __future__ import annotations

import argparse
import os
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

gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gio, GLib, Graphene, Gsk, Gtk  # noqa: E402

from salon import config  # noqa: E402
from salon.app import SalonApplication  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "release-tiles.json"


def capture(window: Gtk.Window, destination: Path) -> None:
    width, height = window.get_width(), window.get_height()
    paintable = Gtk.WidgetPaintable.new(window)
    image = paintable.get_current_image()
    snapshot = Gtk.Snapshot()
    image.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    surface = window.get_surface()
    if node is None or surface is None:
        raise RuntimeError("window has no rendered surface")
    renderer = Gsk.Renderer.new_for_surface(surface)
    rect = Graphene.Rect()
    rect.init(0, 0, width, height)
    texture = renderer.render_texture(node, rect)
    saved = texture.save_to_png(str(destination))
    renderer.unrealize()
    if not saved:
        raise RuntimeError(f"could not save {destination}")


def main() -> int:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "screenshots")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="salon-release-capture-") as temporary:
        root = Path(temporary)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        os.environ["XDG_CACHE_HOME"] = str(root / "cache")
        os.environ["XDG_DATA_HOME"] = str(root / "data")
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        tile_path = root / "config" / "salon" / "tiles.json"
        tile_path.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURE, tile_path)

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

        def capture_editor(window, home) -> bool:
            try:
                capture(window, args.output / "tile-editor.png")
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return finish()

        def capture_settings(window, home) -> bool:
            try:
                capture(window, args.output / "settings.png")
                home._settings_screen.open_tile("entertainment", "movies")  # noqa: SLF001
                GLib.timeout_add(1200, capture_editor, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def capture_search(window, home) -> bool:
            try:
                capture(window, args.output / "search.png")
                home._search.close()  # noqa: SLF001
                home._open_settings("appearance")  # noqa: SLF001
                GLib.timeout_add(400, capture_settings, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def capture_home(window, home) -> bool:
            try:
                capture(window, args.output / "home.png")
                home._open_search()  # noqa: SLF001 - release harness
                home._search._keyboard.reset("movie")  # noqa: SLF001
                home._search._refresh_results()  # noqa: SLF001
                GLib.timeout_add(400, capture_search, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def prepare() -> bool:
            window = app.get_active_window()
            if window is None:
                return finish(RuntimeError("Salon did not create a window"))
            window.unfullscreen()
            window.set_default_size(1280, 720)
            GLib.timeout_add(700, capture_home, window, window.get_content())
            return GLib.SOURCE_REMOVE

        GLib.timeout_add_seconds(3, prepare)
        app.run([])
        if failures:
            raise failures[0]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

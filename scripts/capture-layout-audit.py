#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture the six final-design comparison states at 1920x1080."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

os.environ["GSETTINGS_BACKEND"] = "memory"
os.environ["SALON_CAPTURE_MODE"] = "1"
os.environ["SALON_CAPTURE_CLOCK"] = "2026-08-30T07:51:00"

import gi  # noqa: E402

gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Graphene, Gsk, Gtk  # noqa: E402

from salon import config  # noqa: E402
from salon.app import SalonApplication  # noqa: E402
from salon.core import status as network_state  # noqa: E402
from salon.core import tokens  # noqa: E402
from salon.services.audio_status import AudioStatus  # noqa: E402
from salon.services.network_status import NetworkStatus  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "build" / "layout-audit"


def capture(window: Gtk.Window, name: str) -> None:
    width, height = window.get_width(), window.get_height()
    if (width, height) != (1920, 1080):
        raise RuntimeError(f"expected 1920x1080, got {width}x{height}")
    image = Gtk.WidgetPaintable.new(window).get_current_image()
    snapshot = Gtk.Snapshot()
    image.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    surface = window.get_surface()
    if node is None or surface is None:
        raise RuntimeError("window has no rendered surface")
    renderer = Gsk.Renderer.new_for_surface(surface)
    bounds = Graphene.Rect()
    bounds.init(0, 0, width, height)
    destination = OUTPUT / f"{name}.png"
    if not renderer.render_texture(node, bounds).save_to_png(str(destination)):
        raise RuntimeError(f"could not save {destination}")
    renderer.unrealize()


def row_index(home, label: str) -> int:
    return next(
        index
        for index, row in enumerate(home._settings_screen._panel_list.rows)  # noqa: SLF001
        if row.label_text == label
    )


def assert_bounds(widget: Gtk.Widget, window: Gtk.Window, expected: tuple[int, ...]) -> None:
    ok, bounds = widget.compute_bounds(window)
    if not ok:
        raise RuntimeError(f"{type(widget).__name__} has no window bounds")
    actual = tuple(
        round(value)
        for value in (
            bounds.get_x(),
            bounds.get_y(),
            bounds.get_width(),
            bounds.get_height(),
        )
    )
    if any(abs(got - want) > 2 for got, want in zip(actual, expected, strict=True)):
        raise RuntimeError(f"expected bounds {expected}, got {actual}")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="salon-layout-audit-") as temporary:
        root = Path(temporary)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        os.environ["XDG_CACHE_HOME"] = str(root / "cache")
        os.environ["XDG_DATA_HOME"] = str(root / "data")
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        tiles = root / "config" / "salon" / "tiles.json"
        tiles.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "tests" / "fixtures" / "release-tiles.json", tiles)

        settings = Gio.Settings.new(config.APP_ID)
        settings.set_boolean("onboarding-complete", True)
        settings.set_boolean("fetch-site-icons", False)
        settings.set_boolean("remote-hint", True)
        settings.set_double("animation-scale", 0.0)

        app = SalonApplication()
        failures: list[Exception] = []

        def finish(error: Exception | None = None) -> bool:
            if error is not None:
                failures.append(error)
            app.quit()
            return GLib.SOURCE_REMOVE

        def preview(window, home) -> bool:
            try:
                settings_screen = home._settings_screen  # noqa: SLF001
                settings_screen._popup.close()  # noqa: SLF001
                settings_screen.open_at("appearance")
                index = row_index(home, "Accent colour")
                settings_screen._panel_list.select(index)  # noqa: SLF001
                settings_screen._open_values(  # noqa: SLF001
                    settings_screen._panel_list.rows[index]  # noqa: SLF001
                )
                GLib.timeout_add(350, capture_preview, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def capture_preview(window, home) -> bool:
            try:
                bar = home._settings_screen._preview_bar  # noqa: SLF001
                assert_bounds(
                    bar,
                    window,
                    (
                        round(tokens.CONSOLE_WIDTH_DU),
                        874,
                        round(1920 - tokens.CONSOLE_WIDTH_DU),
                        206,
                    ),
                )
                capture(window, "settings-preview")
                return finish()
            except Exception as error:  # noqa: BLE001
                return finish(error)

        def value(window, home) -> bool:
            try:
                capture(window, "settings")
                screen = home._settings_screen  # noqa: SLF001
                screen.open_at("audio")
                index = row_index(home, "Volume step")
                screen._panel_list.select(index)  # noqa: SLF001
                GLib.timeout_add(250, open_value, window, home, index)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def open_value(window, home, index: int) -> bool:
            try:
                screen = home._settings_screen  # noqa: SLF001
                screen._open_values(screen._panel_list.rows[index])  # noqa: SLF001
                GLib.timeout_add(250, value_open, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def value_open(window, home) -> bool:
            try:
                capture(window, "settings-value")
                GLib.timeout_add(250, preview, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def options(window, home) -> bool:
            try:
                capture(window, "all-apps-options")
                home._tile_menu.hide()  # noqa: SLF001
                home._open_settings("appearance")  # noqa: SLF001
                GLib.timeout_add(350, value, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def apps(window, home) -> bool:
            try:
                ok, rail = home._apps_grid._rail.compute_bounds(window)  # noqa: SLF001
                toolbar_ok, toolbar = home._status_bar.compute_bounds(window)  # noqa: SLF001
                if not ok or rail.get_width() > home._scale.px(54.0):  # noqa: SLF001
                    raise RuntimeError("All Apps A-Z rail is wider than its design strip")
                if not toolbar_ok or rail.get_y() < toolbar.get_y() + toolbar.get_height():
                    raise RuntimeError("All Apps A-Z rail overlaps the top toolbar")
                capture(window, "all-apps")
                home._open_tile_menu(home._apps_grid.focused_tile, from_grid=True)  # noqa: SLF001
                GLib.timeout_add(250, options, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        def prepare() -> bool:
            try:
                window = app.get_active_window()
                if window is None:
                    raise RuntimeError("Salon did not create a window")
                home = window.get_content()
                # Capture mode suppresses machine-dependent watchers. Seed the
                # quiet everyday state whose layout this audit is responsible for.
                home._status_info.set_network(  # noqa: SLF001
                    NetworkStatus(
                        "Sofa Wi-Fi",
                        "Wi-Fi",
                        "Connected",
                        state=network_state.CONNECTIVITY_FULL,
                        strength=86,
                    )
                )
                home._status_info.set_audio(  # noqa: SLF001
                    AudioStatus(True, "HDMI / DisplayPort 3 Output")
                )
                home._status_info.set_connections(1, True)  # noqa: SLF001
                sidebar_ok, sidebar = home._console_sidebar.compute_bounds(window)  # noqa: SLF001
                content_ok, content = home._viewport_host.compute_bounds(window)  # noqa: SLF001
                if not sidebar_ok or not content_ok:
                    raise RuntimeError("Home column bounds are unavailable")
                if sidebar.get_x() + sidebar.get_width() > content.get_x() + 1:
                    raise RuntimeError("Home console overlaps the content viewport")
                hint_ok, hint = home._remote_hint.compute_bounds(window)  # noqa: SLF001
                if not hint_ok or hint.get_x() + hint.get_width() > content.get_x() + 1:
                    raise RuntimeError("Phone pairing card leaves the console rail")
                capture(window, "home")
                home._open_apps()  # noqa: SLF001
                GLib.timeout_add(1200, apps, window, home)
            except Exception as error:  # noqa: BLE001
                return finish(error)
            return GLib.SOURCE_REMOVE

        GLib.timeout_add_seconds(3, prepare)
        GLib.timeout_add_seconds(12, lambda: finish(RuntimeError("capture timed out")))
        app.run([])
        if failures:
            raise failures[0]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

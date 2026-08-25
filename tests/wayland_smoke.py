#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a rendered navigation check against a real Wayland compositor."""
from __future__ import annotations

import os
from pathlib import Path

if os.environ.get("GDK_BACKEND") != "wayland":
    raise SystemExit("GDK_BACKEND must be wayland")

import gi  # noqa: E402

gi.require_version("GdkWayland", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import GdkWayland, Gio, GLib, Graphene, Gsk, Gtk  # noqa: E402

from salon import config  # noqa: E402
from salon.app import SalonApplication  # noqa: E402
from salon.input.actions import Action  # noqa: E402


def capture_frame(window: Gtk.Window) -> None:
    paintable = Gtk.WidgetPaintable.new(window).get_current_image()
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, window.get_width(), window.get_height())
    node = snapshot.to_node()
    surface = window.get_surface()
    if node is None or surface is None:
        raise AssertionError("rendered frame could not be captured")
    renderer = Gsk.Renderer.new_for_surface(surface)
    bounds = Graphene.Rect()
    bounds.init(0, 0, window.get_width(), window.get_height())
    destination = Path(os.environ.get("SALON_SMOKE_FRAME", "build/meson-logs/wayland-smoke.png"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not renderer.render_texture(node, bounds).save_to_png(str(destination)):
        raise AssertionError("rendered frame could not be saved")
    renderer.unrealize()


def main() -> int:
    settings = Gio.Settings.new(config.APP_ID)
    settings.set_boolean("onboarding-complete", True)
    app = SalonApplication()
    failures: list[str] = []

    def capture_settings(window: Gtk.Window) -> bool:
        try:
            capture_frame(window)
        except Exception as error:  # noqa: BLE001 - report through process status
            failures.append(str(error))
        app.quit()
        return GLib.SOURCE_REMOVE

    def inspect() -> bool:
        try:
            window = app.get_active_window()
            if window is None or not window.get_mapped():
                raise AssertionError("Salon did not map a window")
            display = window.get_display()
            if not isinstance(display, GdkWayland.WaylandDisplay):
                raise AssertionError("Salon did not use the Wayland backend")
            home = window.get_content()
            paintable = Gtk.WidgetPaintable.new(window)
            current = paintable.get_current_image()
            if current.get_intrinsic_width() <= 0 or current.get_intrinsic_height() <= 0:
                raise AssertionError("mapped window did not produce a rendered frame")
            home._handle_action(Action.MENU)  # noqa: SLF001 - integration boundary
            if not home._system_menu.get_visible():  # noqa: SLF001
                raise AssertionError("MENU did not open the system menu")
            home._handle_action(Action.MENU)  # noqa: SLF001
            home._open_search()  # noqa: SLF001 - integration boundary
            if not home._search.get_visible():  # noqa: SLF001
                raise AssertionError("search did not open")
            home._search.handle_action(Action.RIGHT)  # noqa: SLF001
            home._search.close()  # noqa: SLF001
            home._open_settings("appearance")  # noqa: SLF001
            if not home._settings_screen.get_visible():  # noqa: SLF001
                raise AssertionError("Settings did not open")
            home._settings_screen.handle_action(Action.DOWN)  # noqa: SLF001
            GLib.timeout_add(300, capture_settings, window)
        except Exception as error:  # noqa: BLE001 - report through process status
            failures.append(str(error))
            app.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add_seconds(2, inspect)

    def timeout() -> bool:
        failures.append("smoke test timed out")
        app.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add_seconds(10, timeout)
    app.run([])
    if failures:
        raise SystemExit("; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a rendered navigation check against a real Wayland compositor."""
from __future__ import annotations

import os
import time
from pathlib import Path

if os.environ.get("GDK_BACKEND") != "wayland":
    raise SystemExit("GDK_BACKEND must be wayland")
os.environ.setdefault("SALON_CAPTURE_MODE", "1")

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

gi.require_version("GdkWayland", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import GdkWayland, Gio, GLib, Graphene, Gsk, Gtk  # noqa: E402

from salon import config  # noqa: E402
from salon.app import SalonApplication  # noqa: E402
from salon.core import status as network_state  # noqa: E402
from salon.core.health import GIB, StorageReading, TemperatureReading  # noqa: E402
from salon.core.nowplaying import PAUSED, PLAYING, Player  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services.audio_status import AudioStatus  # noqa: E402
from salon.services.device_battery import DeviceBatteryStatus  # noqa: E402
from salon.services.network_status import NetworkStatus  # noqa: E402


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

    def media_players() -> tuple[Player, ...]:
        """Three sources, which is one more than the rail can draw in full."""
        now = time.monotonic()
        return (
            Player(
                "org.mpris.MediaPlayer2.first", "Spotify", PLAYING,
                title="Bright Horses (Live at Alexandra Palace)",
                artist="Nick Cave & The Bad Seeds", changed_at=now,
                can_go_next=True, can_go_previous=True,
                position_us=74_000_000, length_us=248_000_000, position_at=now,
            ),
            Player(
                "org.mpris.MediaPlayer2.second", "Chromium", PAUSED,
                title="The Bear S03E04 — Violet", artist="Disney+",
                changed_at=now - 30, position_us=1_820_000_000,
                length_us=2_400_000_000, position_at=now,
            ),
            Player(
                "org.mpris.MediaPlayer2.third", "VLC", PAUSED,
                title="Radio Paradise — Mellow Mix", changed_at=now - 90,
            ),
        )

    def bounds(widget: Gtk.Widget, window: Gtk.Window) -> tuple[float, float]:
        found, rectangle = widget.compute_bounds(window)
        if not found:
            raise AssertionError(f"{widget} is not in the window")
        return (rectangle.origin.y, rectangle.origin.y + rectangle.size.height)

    def fill_the_rail() -> bool:
        """Put media in the rail a beat before it is measured.

        A turn of the loop between the players arriving and the geometry
        being read: the rail is an overlay child and its allocation is not
        settled in the same frame the card is filled in.
        """
        window = app.get_active_window()
        if window is not None:
            window.get_content()._now_playing_status.set_players(  # noqa: SLF001
                media_players(), current_source="org.mpris.MediaPlayer2.first"
            )
        GLib.timeout_add(400, inspect)
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
            # The now-playing card and the pairing card share the rail and
            # are separate overlay children, so neither can see the other.
            # The card used to stack its media sources and three of them
            # overran it by 80px, with the third row drawn behind the QR
            # code; it draws one source at a time now, which is what makes
            # its height independent of what happens to be playing.
            card = home._now_playing_status  # noqa: SLF001
            if not card.get_visible():
                raise AssertionError("three media sources did not put a card in the rail")
            _card_top, card_bottom = bounds(card, window)
            if home._remote_hint.get_visible():  # noqa: SLF001
                hint_top, _hint_bottom = bounds(home._remote_hint, window)  # noqa: SLF001
                if card_bottom > hint_top:
                    raise AssertionError(
                        f"the now-playing card ran {card_bottom - hint_top:.0f}px "
                        "into the pairing card"
                    )
            if card_bottom > window.get_height():
                raise AssertionError("the now-playing card ran past the bottom of the rail")
            # And it has to be pressable: the rail refused pointer events as
            # a whole, which made the card's own click-to-toggle and every
            # secondary source button dead.
            found, area = card.compute_bounds(window)
            picked = window.pick(
                area.origin.x + area.size.width / 2,
                area.origin.y + area.size.height / 2,
                Gtk.PickFlags.DEFAULT,
            )
            if not found or picked is None or not picked.is_ancestor(card) and picked is not card:
                raise AssertionError(f"a press in the now-playing card reached {picked}")
            home._status_info.set_network(  # noqa: SLF001
                NetworkStatus(
                    "Sofa Wi-Fi", "Wi-Fi", "Connected",
                    state=network_state.CONNECTIVITY_FULL, strength=86,
                )
            )
            home._status_info.set_audio(  # noqa: SLF001
                AudioStatus(True, "HDMI / DisplayPort 3 Output")
            )
            home._status_info.set_connections(1, True)  # noqa: SLF001
            status_rows = [  # noqa: SLF001
                slot for slot in home._status_info._slots if slot[0].get_visible()
            ]
            status_text = [(row[2].get_label(), row[3].get_label()) for row in status_rows]
            if status_text != [
                ("Sofa Wi-Fi", "Strong"),
                ("Audio", "HDMI 3"),
                ("Controls", "Pad + phone"),
            ]:
                raise AssertionError(f"the adaptive status card rendered {status_text!r}")
            home._status_info.set_device_batteries(  # noqa: SLF001
                (DeviceBatteryStatus("DualSense", "Gamepad", 12),)
            )
            if not any(row[2].get_label() == "DualSense" for row in home._status_info._slots):
                raise AssertionError("controller battery did not enter the status card")
            home._status_info.set_device_batteries(())  # noqa: SLF001
            home._status_info.set_network(  # noqa: SLF001
                NetworkStatus(
                    "Sofa Wi-Fi", "Wi-Fi", "Connected, but limited",
                    state=network_state.CONNECTIVITY_LIMITED, strength=95,
                )
            )
            home._status_info.set_health(  # noqa: SLF001
                StorageReading(100 * GIB, 6 * GIB),
                TemperatureReading(88, 85, 95, "CPU"),
            )
            warning_rows = [  # noqa: SLF001
                slot for slot in home._status_info._slots if slot[0].get_visible()
            ]
            warning_text = [(row[2].get_label(), row[3].get_label()) for row in warning_rows]
            if warning_text != [
                ("Temperature", "Hot 88°C"),
                ("Storage", "6.0 GB free"),
                ("Sofa Wi-Fi", "No internet"),
                ("Audio", "HDMI 3"),
            ] or not all(row[0].has_css_class("warning") for row in warning_rows[:3]):
                raise AssertionError(f"status warnings rendered {warning_text!r}")
            home._open_apps()  # noqa: SLF001 - integration boundary
            grid = home._apps_grid  # noqa: SLF001
            first_tile = next(  # noqa: SLF001
                tile for row in home._catalog.rows for tile in row.tiles
            )
            # Make the focus path deterministic instead of waiting for the
            # asynchronous desktop-file scan a second time.
            grid._on_scanned([first_tile])  # noqa: SLF001
            home._handle_action(Action.UP)  # noqa: SLF001
            if not home._nav_focused or grid._widgets[0]._focused:  # noqa: SLF001
                raise AssertionError("UP did not move All Apps focus into the top toolbar")
            home._handle_action(Action.RIGHT)  # noqa: SLF001 - Connect a phone
            home._handle_action(Action.RIGHT)  # noqa: SLF001 - Settings
            selected = home._status_bar.selected_button  # noqa: SLF001
            if selected is None or selected.get_tooltip_text() != "Settings":
                raise AssertionError("hidden All Apps shortcut blocked navigation to Settings")
            home._handle_action(Action.OK)  # noqa: SLF001
            if not home._settings_screen.get_visible() or grid.get_visible():  # noqa: SLF001
                raise AssertionError("Settings was not reachable from All Apps")
            home._settings_screen.close()  # noqa: SLF001
            home._handle_action(Action.MENU)  # noqa: SLF001 - integration boundary
            if not home._system_menu.get_visible():  # noqa: SLF001
                raise AssertionError("MENU did not open the system menu")
            if home._system_menu.get_accessible_role() != Gtk.AccessibleRole.MENU:  # noqa: SLF001
                raise AssertionError("system menu did not expose a menu role")
            for _ in range(4):
                home._handle_action(Action.DOWN)  # noqa: SLF001
            if home._system_menu.selected_item.label != "Power":  # noqa: SLF001
                raise AssertionError("root menu did not select Power")
            home._handle_action(Action.RIGHT)  # noqa: SLF001
            if home._system_menu.current_frame_id != "power":  # noqa: SLF001
                raise AssertionError("RIGHT did not enter Power")
            home._handle_action(Action.LEFT)  # noqa: SLF001
            if home._system_menu.selected_item.label != "Power":  # noqa: SLF001
                raise AssertionError("LEFT did not restore the root selection")
            home._handle_action(Action.MENU)  # noqa: SLF001
            home._open_settings("appearance")  # noqa: SLF001
            home._handle_action(Action.MENU)  # noqa: SLF001
            if not home._system_menu.get_visible():  # noqa: SLF001
                raise AssertionError("MENU was not authoritative inside Settings")
            home._system_menu.activate_selected()  # noqa: SLF001 - Search
            if not home._search.get_visible() or home._settings_screen.get_visible():  # noqa: SLF001
                raise AssertionError("global Search did not replace Settings")
            home._search.close()  # noqa: SLF001
            home._handle_action(Action.POWER)  # noqa: SLF001
            if home._system_menu.current_frame_id != "power":  # noqa: SLF001
                raise AssertionError("POWER did not open the Power frame")
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

    GLib.timeout_add_seconds(2, fill_the_rail)

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

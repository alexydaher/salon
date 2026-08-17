"""Proof-of-concept home screen.

Stands in for the full row/anchoring/backdrop system (M4) and provider
plugin architecture (M9): a hardcoded catalog, simple keyboard navigation,
and real launching. Enough to click through end to end; not the final UI.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from salon.core.model import LaunchKind, LaunchSpec, Row, Tile  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.input.gamepad import GamepadSource  # noqa: E402
from salon.input.keyboard import action_for_keyval  # noqa: E402
from salon.services.launcher import LauncherService  # noqa: E402
from salon.services.pointer_injector import (  # noqa: E402
    PointerInjector,
    onscreen_keyboard_enabled,
    set_onscreen_keyboard_enabled,
)
from salon.ui.tile import TileWidget  # noqa: E402

# Pixels of cursor motion per poll tick at full stick deflection (~60 ticks/s).
_POINTER_SPEED = 22.0


def _is_browser_launch(tile: Tile) -> bool:
    """Whether launching this tile hands control to a browser window we
    can't reach directly — the case where the gamepad should drive the
    system pointer instead of tile navigation."""
    if tile.launch.kind is LaunchKind.URL:
        return True
    return tile.launch.kind is LaunchKind.DESKTOP and tile.launch.target == "com.google.Chrome"


def _demo_rows() -> list[Row]:
    return [
        Row(
            id="apps",
            title="Apps",
            provider_id="static",
            tiles=[
                Tile(
                    id="files",
                    title="Files",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.Nautilus"),
                    artwork=None,
                    icon_name="org.gnome.Nautilus",
                    accent=None,
                ),
                Tile(
                    id="text-editor",
                    title="Text Editor",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.TextEditor"),
                    artwork=None,
                    icon_name="org.gnome.TextEditor",
                    accent=None,
                ),
                Tile(
                    id="calculator",
                    title="Calculator",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="org.gnome.Calculator"),
                    artwork=None,
                    icon_name="org.gnome.Calculator",
                    accent=None,
                ),
                Tile(
                    id="chrome",
                    title="Chrome",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.DESKTOP, target="com.google.Chrome"),
                    artwork=None,
                    icon_name="com.google.Chrome",
                    accent=None,
                ),
            ],
        ),
        Row(
            id="streaming",
            title="Streaming",
            provider_id="static",
            tiles=[
                Tile(
                    id="netflix",
                    title="Netflix",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.netflix.com",
                        browser_profile="netflix",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent="#E50914",
                ),
                Tile(
                    id="prime-video",
                    title="Prime Video",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.primevideo.com",
                        browser_profile="prime-video",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent="#00A8E1",
                ),
                Tile(
                    id="geforce-now",
                    title="GeForce NOW",
                    subtitle=None,
                    launch=LaunchSpec(kind=LaunchKind.FLATPAK, target="com.nvidia.geforcenow"),
                    artwork=None,
                    icon_name="com.nvidia.geforcenow",
                    accent="#76B900",
                ),
            ],
        ),
        Row(
            id="web",
            title="Web",
            provider_id="static",
            tiles=[
                Tile(
                    id="gnome-org",
                    title="GNOME.org",
                    subtitle=None,
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://www.gnome.org",
                        browser_profile="gnome-org",
                    ),
                    artwork=None,
                    icon_name="web-browser-symbolic",
                    accent=None,
                ),
            ],
        ),
    ]


class HomeView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=32)
        self.set_margin_top(48)
        self.set_margin_bottom(48)
        self.set_margin_start(48)
        self.set_margin_end(48)

        self._rows = _demo_rows()
        self._row_widgets: list[list[TileWidget]] = []
        self._launcher = LauncherService()
        self._focus_row = 0
        self._focus_col = 0
        self._toast_overlay = Adw.ToastOverlay()

        rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=32)
        for row in self._rows:
            heading = Gtk.Label(label=row.title or "")
            heading.set_halign(Gtk.Align.START)
            heading.add_css_class("salon-row-heading")
            rows_box.append(heading)

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
            widgets: list[TileWidget] = []
            for tile in row.tiles:
                widget = TileWidget(tile)
                row_box.append(widget)
                widgets.append(widget)
            self._row_widgets.append(widgets)
            rows_box.append(row_box)

        self._toast_overlay.set_child(rows_box)
        self.append(self._toast_overlay)
        self._update_focus()

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)
        self.set_can_focus(True)
        self.set_focusable(True)

        self._pointer_mode = False
        self._child_active = False
        self._pointer = PointerInjector(on_ready=self._on_pointer_ready)

        # Keep a reference alive — GamepadSource holds the only strong ref
        # to the Manette.Monitor/Device connections that keep signals firing.
        self._gamepad = GamepadSource(self._handle_action, on_right_stick=self._on_right_stick)

    def _update_focus(self) -> None:
        for r, widgets in enumerate(self._row_widgets):
            for c, widget in enumerate(widgets):
                widget.set_focused(r == self._focus_row and c == self._focus_col)

    def _on_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: object,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            # Dev-only quit shortcut, deliberately outside the Action
            # pipeline — a real TV launcher shouldn't be closeable by a
            # single button, and this must never be reachable from the
            # gamepad (B already means BACK, not quit).
            root = self.get_root()
            if isinstance(root, Gtk.Window):
                root.close()
            return True
        action = action_for_keyval(keyval)
        if action is None:
            return False
        self._handle_action(action)
        return True

    def _handle_action(self, action: Action) -> None:
        if action is Action.SEARCH:
            # Global regardless of mode: harmless accessibility toggle, not
            # a Salon navigation action, so it's never worth swallowing.
            set_onscreen_keyboard_enabled(not onscreen_keyboard_enabled())
            return

        if self._pointer_mode:
            if action is Action.OK:
                self._pointer.click()
            elif action is Action.BACK:
                self._pointer_mode = False
                self._toast_overlay.add_toast(Adw.Toast(title="Back to tiles"))
            return

        if self._child_active:
            # A native app (e.g. a game client) reads the same raw gamepad
            # device directly — that input bypasses window focus entirely,
            # unlike keyboard/mouse, so Salon has to deliberately go quiet
            # rather than fight it for button presses. Resumes on exit.
            return

        if action is Action.RIGHT:
            self._move(0, 1)
        elif action is Action.LEFT:
            self._move(0, -1)
        elif action is Action.DOWN:
            self._move(1, 0)
        elif action is Action.UP:
            self._move(-1, 0)
        elif action is Action.OK:
            self._launch_focused()
        # BACK is intentionally a no-op here: there's no parent screen at
        # the top level yet (no search/settings overlay stack built), and
        # it must never quit Salon outright — see _on_key_pressed for the
        # dev-only Escape shortcut that actually does that.

    def _on_right_stick(self, x: float, y: float) -> None:
        if self._pointer_mode and self._pointer.ready:
            self._pointer.move(x * _POINTER_SPEED, y * _POINTER_SPEED)

    def _on_pointer_ready(self, ok: bool) -> None:
        if not ok:
            self._pointer_mode = False
            self._toast_overlay.add_toast(
                Adw.Toast(title="Pointer control wasn't granted — check the permission prompt.")
            )

    def _move(self, d_row: int, d_col: int) -> None:
        new_row = self._focus_row + d_row
        if 0 <= new_row < len(self._row_widgets):
            self._focus_row = new_row
            self._focus_col = min(self._focus_col, len(self._row_widgets[new_row]) - 1)
        new_col = self._focus_col + d_col
        if 0 <= new_col < len(self._row_widgets[self._focus_row]):
            self._focus_col = new_col
        self._update_focus()

    def _launch_focused(self) -> None:
        tile = self._rows[self._focus_row].tiles[self._focus_col]
        subprocess, error = self._launcher.launch(tile.launch)
        if error is not None:
            self._toast_overlay.add_toast(Adw.Toast(title=error))
            return
        if subprocess is None:
            return  # BUILTIN: nothing spawned, nothing to track

        is_browser = _is_browser_launch(tile)
        if is_browser:
            self._pointer_mode = True
            self._pointer.start()
            self._toast_overlay.add_toast(
                Adw.Toast(title="Right stick = cursor, A = click, Y = keyboard, B = back")
            )
        else:
            self._child_active = True
            self._toast_overlay.add_toast(
                Adw.Toast(title=f"{tile.title} has the controller — Salon resumes when it closes")
            )

        def on_exited(proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
            try:
                proc.wait_finish(result)
            except GLib.Error:
                pass
            if is_browser:
                self._pointer_mode = False
            else:
                self._child_active = False
                self._toast_overlay.add_toast(Adw.Toast(title="Welcome back to Salon"))

        subprocess.wait_async(None, on_exited)

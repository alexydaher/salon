"""Proof-of-concept home screen.

Stands in for the full row/anchoring/backdrop system (M4) and provider
plugin architecture (M9): a hardcoded catalog, simple keyboard navigation,
and real launching. Enough to click through end to end; not the final UI.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from salon.core.model import LaunchKind, LaunchSpec, Row, Tile  # noqa: E402
from salon.services.launcher import LauncherService  # noqa: E402
from salon.ui.tile import TileWidget  # noqa: E402


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
                    launch=LaunchSpec(
                        kind=LaunchKind.URL,
                        target="https://play.geforcenow.com",
                        browser_profile="geforce-now",
                    ),
                    artwork=None,
                    icon_name="applications-games-symbolic",
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

    def _update_focus(self) -> None:
        for r, widgets in enumerate(self._row_widgets):
            for c, widget in enumerate(widgets):
                widget.set_focused(r == self._focus_row and c == self._focus_col)

    def _on_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Right:
            self._move(0, 1)
        elif keyval == Gdk.KEY_Left:
            self._move(0, -1)
        elif keyval == Gdk.KEY_Down:
            self._move(1, 0)
        elif keyval == Gdk.KEY_Up:
            self._move(-1, 0)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._launch_focused()
        elif keyval == Gdk.KEY_Escape:
            root = self.get_root()
            if isinstance(root, Gtk.Window):
                root.close()
        else:
            return False
        return True

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
        error = self._launcher.launch(tile.launch)
        if error is not None:
            self._toast_overlay.add_toast(Adw.Toast(title=error))

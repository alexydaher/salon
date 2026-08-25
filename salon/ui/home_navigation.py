# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    _POINTER_SPEED,
    Action,
    Bump,
    GdkWayland,
    Gtk,
)


class HomeNavigationController(ServiceComponent):
    def _set_nav_focused(self, focused: bool) -> None:
        self._owner._nav_focused = focused
        self._owner._status_bar.set_nav_focused(focused, index=0 if focused else None)
        widget = self._owner._focused_widget()
        if widget is not None:
            self._owner._publish_active_descendant(widget)
        # Only one thing on screen may carry the strong highlight at a time,
        # so the tile under the cursor drops its ring while the bar has it.
        self._owner._update_focus()

    def _handle_nav_action(self, action: Action) -> None:
        if action is Action.DOWN or action is Action.BACK:
            self._set_nav_focused(False)
            return
        if action is Action.UP:
            self._owner._rubber_band(Bump.UP)
            return
        if action in (Action.LEFT, Action.RIGHT):
            if not self._owner._status_bar.move(-1 if action is Action.LEFT else 1):
                self._owner._rubber_band(Bump.LEFT if action is Action.LEFT else Bump.RIGHT)
            return
        if action is Action.OK:
            # Whatever it opens covers the home screen, so hand focus back
            # to the tiles now — closing that screen must not drop the user
            # back onto a highlighted power button.
            self._set_nav_focused(False)
            self._owner._status_bar.activate()

    def _on_right_stick(self, x: float, y: float) -> None:
        if self._owner._pointer_mode and self._owner._pointer.ready:
            self._owner._pointer.move(x * _POINTER_SPEED, y * _POINTER_SPEED)

    def _on_pointer_ready(self, ok: bool) -> None:
        # The phone shows whether its trackpad and keyboard can reach other
        # applications, so the grant arriving (or being refused) is a change
        # it needs to hear about.
        self._owner._publish_remote_state()
        if not ok:
            self._owner._pointer_mode = False
            self._owner._toast(
                "Salon wasn't allowed to move the pointer. You can grant it "
                "again from Settings, under Input."
            )

    def _start_pointer_session(self) -> None:
        # Export our window handle so the portal's consent dialog is
        # properly anchored to Salon instead of appearing unparented —
        # without this, xdg-desktop-portal logs "Failed to associate portal
        # window with parent window" and the dialog isn't reliably visible.
        root = self._owner.get_root()
        surface = root.get_surface() if isinstance(root, Gtk.Window) else None
        if isinstance(surface, GdkWayland.WaylandToplevel):
            exported = surface.export_handle(self._on_handle_exported)
            if exported:
                return
        self._owner._pointer.start()

    def _on_handle_exported(
        self, toplevel: GdkWayland.WaylandToplevel, handle: str, user_data: object = None
    ) -> None:
        self._owner._pointer.start(parent_window=f"wayland:{handle}")

    def on_window_active_changed(self, is_active: bool) -> None:
        """Called by SalonWindow's notify::is-active handler — half of the
        dual return-detection signal in §6.4 (the other half is the child
        process actually exiting, handled inside LauncherService)."""
        self._owner._launcher.notify_window_active(is_active)

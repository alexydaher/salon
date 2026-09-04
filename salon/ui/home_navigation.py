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
        # The rail's card, the top bar and the tiles share one cursor, so
        # entering the bar — or dismissing it on the way into a full-screen
        # surface — is also leaving the card. Written here rather than at
        # the dozen call sites, because "the ring is in two places" is
        # exactly the bug this is guarding against.
        self._drop_card_focus()
        self._owner._nav_focused = focused
        self._owner._status_bar.set_nav_focused(focused)
        self._owner._apps_grid.set_top_bar_focused(
            focused and self._owner._apps_grid.get_visible()
        )
        self._publish_nav_detail()
        widget = self._owner._focused_widget()
        if widget is not None:
            self._owner._publish_active_descendant(widget)
        # Only one thing on screen may carry the strong highlight at a time,
        # so the tile under the cursor drops its ring while the bar has it.
        self._owner._update_focus()

    def _visible_menu(self):
        for name in ("_system_menu", "_tile_menu"):
            menu = getattr(self._owner, name, None)
            if menu is None:
                continue
            if menu.get_visible():
                return menu
        return None

    def _on_menu_changed(self) -> None:
        """Make a visible menu the sole interaction and accessibility owner."""
        menu = self._visible_menu()
        if menu is not None:
            if not self._owner._menu_focus_owned:
                self._owner._menu_focus_owned = True
                self._owner._menu_origin_nav_focused = self._owner._nav_focused
                self._owner._menu_origin_card_focused = self._owner._card_focused
            self._owner._nav_focused = False
            self._drop_card_focus()
            self._owner._status_bar.set_nav_focused(False)
            self._owner._detail_bar.clear_nav_target()
            self._owner._update_focus()
            self._on_menu_selection_changed()
        elif self._owner._menu_focus_owned:
            restore_nav = self._owner._menu_origin_nav_focused
            restore_card = self._owner._menu_origin_card_focused and self._card.has_media
            self._owner._menu_focus_owned = False
            self._owner.grab_focus()
            self._owner._nav_focused = restore_nav
            self._owner._status_bar.set_nav_focused(restore_nav)
            self._owner._card_focused = restore_card
            self._card.set_card_focused(restore_card)
            if restore_nav:
                self._publish_nav_detail()
            elif restore_card:
                self._publish_card_detail()
            else:
                self._owner._detail_bar.clear_nav_target()
            self._owner._update_focus()
        self._owner._update_legend()
        self._owner._publish_remote_state()

    def _on_menu_selection_changed(self) -> None:
        menu = self._visible_menu()
        if menu is None or menu.selected_row is None:
            return
        self._owner.update_relation(
            [Gtk.AccessibleRelation.ACTIVE_DESCENDANT], [menu.selected_row]
        )
        # Entering or leaving a submenu changes BACK from "Close" to
        # "Back a step" even though the menu itself never changes visibility.
        self._owner._update_legend()

    def _publish_nav_detail(self) -> None:
        """Point the detail strip at whatever the ring is actually on."""
        if not self._owner._nav_focused:
            self._owner._detail_bar.clear_nav_target()
            return
        title, detail = self._owner._status_bar.selected_hint
        self._owner._detail_bar.set_nav_target(title, detail)

    def _handle_nav_action(self, action: Action) -> None:
        if action is Action.DOWN or action is Action.BACK:
            self._set_nav_focused(False)
            return
        if action is Action.UP:
            self._owner._rubber_band(Bump.UP)
            return
        if action in (Action.LEFT, Action.RIGHT):
            # The toolbar has no scrolling surface of its own.  At either
            # end, leave it still: rubber-banding here moves the remembered
            # app row underneath even though that row does not own focus.
            self._owner._status_bar.move(-1 if action is Action.LEFT else 1)
            self._publish_nav_detail()
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

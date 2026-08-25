# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.core import sandbox
from salon.services.component import ServiceComponent
from salon.ui.settings.navigation_policy import is_settings_back, section_target
from salon.ui.settings.screen_shared import (
    _BUMP_DISTANCE_DU,
    _MAX_NOTES,
    Action,
    Gio,
    GLib,
    Pane,
    SettingsRow,
)


class SettingsActionController(ServiceComponent):
    def handle_action(self, action: Action) -> None:
        # MENU is the one button that always means the same thing, so from
        # inside Settings it means "put me back on the home screen" — no
        # matter how many levels of the tile editor are on the stack.
        if action is Action.MENU:
            self._owner.close()
            return

        if self._owner._preview_row is not None:
            self._handle_preview(action)
            return

        # An open value list owns every button, including BACK, so it is
        # checked before the pane dispatch below rather than inside it.
        if self._owner._popup.is_open:
            self._owner._popup.handle_action(action)
            self._owner._update_legend()
            return

        if action in (Action.PREV_GROUP, Action.NEXT_GROUP):
            self._step_section(action)
            return

        if action is Action.OPTIONS and self._owner._pane is Pane.PANEL:
            row = self._owner._panel_list.selected_row
            if row is not None and row.previewable:
                self._owner._enter_preview(row)
            elif row is not None:
                row.flash_denied()
            return

        if is_settings_back(action):
            if self._owner._pane is Pane.PANEL:
                self._owner._pop()
            else:
                self._owner.close()
            return

        if self._owner._pane is Pane.SECTIONS:
            self._handle_sections(action)
        else:
            self._handle_panel(action)

    def _handle_preview(self, action: Action) -> None:
        if action in (Action.BACK, Action.OK):
            self._owner._leave_preview()
            return
        if action in (Action.LEFT, Action.RIGHT):
            row = self._owner._preview_row
            if row is not None and row.adjust(-1 if action is Action.LEFT else 1):
                self._owner._refresh_preview()
            return
        if action in (Action.UP, Action.DOWN):
            self._owner._step_preview(-1 if action is Action.UP else 1)

    def _handle_sections(self, action: Action) -> None:
        if action in (Action.UP, Action.DOWN):
            if self._owner._sections.move(-1 if action is Action.UP else 1):
                self._owner._set_stack(
                    [self._owner._section_panels[self._owner._sections.selected_index]]
                )
                self._owner._rebuild_panel()
            else:
                self._owner._sections.bump(
                    self._owner._scale.du(_BUMP_DISTANCE_DU) * (1 if action is Action.UP else -1)
                )
        elif action in (Action.RIGHT, Action.OK):
            self._owner._enter_section(self._owner._sections.selected_index)
        elif action is Action.LEFT:
            # BACK owns navigation history. A horizontal direction should
            # never unexpectedly close a full-screen surface.
            row = self._owner._sections.selected_row
            if row is not None:
                row.flash_denied()

    def _handle_panel(self, action: Action) -> None:
        if action is Action.OK:
            row = self._owner._panel_list.selected_row
            if row is not None and row.choices:
                self._open_values(row)
                return
            self._owner._panel_list.activate()
            return
        if action in (Action.UP, Action.DOWN):
            delta = -1 if action is Action.UP else 1
            if not self._owner._panel_list.move(delta):
                self._owner._panel_list.bump(self._owner._scale.du(_BUMP_DISTANCE_DU) * -delta)
            self._owner._update_legend()
            return
        if action is Action.RIGHT:
            self._enter_row()
            return
        if action is Action.LEFT:
            # LEFT is deliberately not a second BACK button. Values are
            # chosen from a visible list, so there is no hidden edit for it
            # to perform here either.
            row = self._owner._panel_list.selected_row
            if row is not None:
                row.flash_denied()

    def _step_section(self, action: Action) -> None:
        """LB/RB (or the equivalent group actions) change category.

        Keep whichever pane currently owns the cursor: from the section
        list this previews the neighbouring category, and from a panel it
        opens that category's root. A deep editor is left cleanly through
        `_set_stack`, so discovery and other temporary work is stopped.
        """
        target = section_target(
            self._owner._sections.selected_index, len(self._owner._section_panels), action
        )
        if target is None:
            active = (
                self._owner._sections
                if self._owner._pane is Pane.SECTIONS
                else self._owner._panel_list
            )
            row = active.selected_row
            if row is not None:
                row.flash_denied()
            return
        self._owner._sections.select(target)
        self._owner._set_stack([self._owner._section_panels[target]])
        self._owner._rebuild_panel()

    def _activate_panel_row(self, index: int) -> None:
        """A click. Deliberately not the preview strip: entering preview
        hides the whole screen, which is a fine answer to a deliberate OK
        from a remote and a startling one to a mouse click."""
        row = self._owner._panel_list.rows[index]
        if row.choices:
            self._open_values(row)
        else:
            row.activate_row()

    def _enter_row(self) -> None:
        """RIGHT on the selected row: go in, whatever "in" means for it."""
        row = self._owner._panel_list.selected_row
        if row is None:
            return
        if row.choices:
            self._open_values(row)
        elif row.enterable:
            self._owner._panel_list.activate()
        else:
            # A plain action row, or a read-only one. RIGHT deliberately
            # does not run it — see ActionRow.
            row.flash_denied()

    def _open_values(self, row: SettingsRow) -> None:
        if self._owner._popup.open_for(row):
            self._owner._update_legend()

    def _on_value_chosen(self) -> None:
        """A value was picked. The row has already written it; everything
        else on the panel may now be describing the old one — a tile's kind
        decides which rows exist below it — so rebuild rather than guess."""
        self._owner._rebuild_panel()

    def note_action(self, action: Action) -> None:
        """Feed the controller test panel. Only recorded while Settings is
        open, so this costs nothing the rest of the time."""
        if not self._owner.get_visible():
            return
        self._owner._context.notes.insert(0, action.value)
        del self._owner._context.notes[_MAX_NOTES:]
        if self._owner._stack and self._owner._stack[-1].title == "Controller test":
            self._owner._rebuild_panel()

    def _open_control_center(self, panel: str) -> None:
        """§1: Salon is not a settings panel — system configuration
        delegates to gnome-control-center."""
        if not sandbox.capabilities().control_center:
            self._owner._context.toast("GNOME Settings is unavailable in the Flatpak build.")
            return
        try:
            Gio.Subprocess.new(
                ["gnome-control-center", panel],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error:
            self._owner._context.toast(
                "GNOME Settings isn't installed, so this can't be opened from here."
            )

# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings.screen_shared import *


class SettingsActionController(ServiceComponent):
    def handle_action(self, action: Action) -> None:
        # MENU is the one button that always means the same thing, so from
        # inside Settings it means "put me back on the home screen" — no
        # matter how many levels of the tile editor are on the stack.
        if action is Action.MENU:
            self.close()
            return

        if self._preview_row is not None:
            self._handle_preview(action)
            return

        # An open value list owns every button, including BACK, so it is
        # checked before the pane dispatch below rather than inside it.
        if self._popup.is_open:
            self._popup.handle_action(action)
            self._update_legend()
            return

        if action is Action.BACK:
            if self._pane is Pane.PANEL:
                self._pop()
            else:
                self.close()
            return

        if self._pane is Pane.SECTIONS:
            self._handle_sections(action)
        else:
            self._handle_panel(action)

    def _handle_preview(self, action: Action) -> None:
        if action in (Action.BACK, Action.OK):
            self._leave_preview()
            return
        if action in (Action.LEFT, Action.RIGHT):
            row = self._preview_row
            if row is not None and row.adjust(-1 if action is Action.LEFT else 1):
                self._refresh_preview()
            return
        if action in (Action.UP, Action.DOWN):
            self._step_preview(-1 if action is Action.UP else 1)

    def _handle_sections(self, action: Action) -> None:
        if action in (Action.UP, Action.DOWN):
            if self._sections.move(-1 if action is Action.UP else 1):
                self._set_stack([self._section_panels[self._sections.selected_index]])
                self._rebuild_panel()
            else:
                self._sections.bump(
                    self._scale.du(_BUMP_DISTANCE_DU) * (1 if action is Action.UP else -1)
                )
        elif action in (Action.RIGHT, Action.OK):
            self._enter_section(self._sections.selected_index)
        elif action is Action.LEFT:
            # The section list is the left edge of the screen; there is
            # nothing further left but the home screen it was opened from.
            # Symmetrical with LEFT leaving a panel, and it means the way
            # out is the same gesture at every depth.
            self.close()

    def _handle_panel(self, action: Action) -> None:
        if action is Action.OK:
            row = self._panel_list.selected_row
            if row is not None and row.previewable:
                self._enter_preview(row)
                return
            if row is not None and row.choices:
                self._open_values(row)
                return
            self._panel_list.activate()
            return
        if action in (Action.UP, Action.DOWN):
            delta = -1 if action is Action.UP else 1
            if not self._panel_list.move(delta):
                self._panel_list.bump(self._scale.du(_BUMP_DISTANCE_DU) * -delta)
            self._update_legend()
            return
        if action is Action.RIGHT:
            self._enter_row()
            return
        if action is Action.LEFT:
            # LEFT is how you leave — the same gesture that crosses panes in
            # search, and now the same one at every depth of this screen.
            # It never edits a row: values are chosen from a list.
            self._pop()

    def _activate_panel_row(self, index: int) -> None:
        """A click. Deliberately not the preview strip: entering preview
        hides the whole screen, which is a fine answer to a deliberate OK
        from a remote and a startling one to a mouse click."""
        row = self._panel_list.rows[index]
        if row.choices:
            self._open_values(row)
        else:
            row.activate_row()

    def _enter_row(self) -> None:
        """RIGHT on the selected row: go in, whatever "in" means for it."""
        row = self._panel_list.selected_row
        if row is None:
            return
        if row.choices:
            self._open_values(row)
        elif row.enterable:
            self._panel_list.activate()
        else:
            # A plain action row, or a read-only one. RIGHT deliberately
            # does not run it — see ActionRow.
            row.flash_denied()

    def _open_values(self, row: SettingsRow) -> None:
        if self._popup.open_for(row):
            self._update_legend()

    def _on_value_chosen(self) -> None:
        """A value was picked. The row has already written it; everything
        else on the panel may now be describing the old one — a tile's kind
        decides which rows exist below it — so rebuild rather than guess."""
        self._rebuild_panel()

    def note_action(self, action: Action) -> None:
        """Feed the controller test panel. Only recorded while Settings is
        open, so this costs nothing the rest of the time."""
        if not self.get_visible():
            return
        self._context.notes.insert(0, action.value)
        del self._context.notes[_MAX_NOTES:]
        if self._stack and self._stack[-1].title == "Controller test":
            self._rebuild_panel()

    def _open_control_center(self, panel: str) -> None:
        """§1: Salon is not a settings panel — system configuration
        delegates to gnome-control-center."""
        try:
            Gio.Subprocess.new(
                ["gnome-control-center", panel],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error:
            self._context.toast(
                "GNOME Settings isn't installed, so this can't be opened from here."
            )

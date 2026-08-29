# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings import control_center
from salon.ui.settings.navigation_policy import is_settings_back, section_target
from salon.ui.settings.screen_shared import (
    _BUMP_DISTANCE_DU,
    _MAX_NOTES,
    Action,
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
            self._handle_options()
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

    def _handle_options(self) -> None:
        """OPTIONS on a panel row: preview it, or put it back.

        Two jobs on one press, and they never collide — a previewable row
        is one whose effect is visible on the home screen, and the strip is
        how you judge it. Everything else gets the other thing OPTIONS
        means everywhere in Salon: the menu for the item under the cursor,
        which here has exactly one entry worth having.
        """
        row = self._owner._panel_list.selected_row
        if row is None:
            return
        if row.previewable:
            self._owner._enter_preview(row)
            return
        self._restore_row(row)

    def _restore_row(self, row: SettingsRow) -> None:
        """Put one row back to what Salon shipped, and say so either way.

        A row that is already at its default used to answer with the denial
        flash alone, which is the same red blink LEFT gives — two different
        refusals spelled identically, and neither of them says the row is
        *already* right.
        """
        if not row.has_default:
            row.flash_denied()
            return
        if not row.modified:
            row.flash_denied()
            self._owner._context.toast(f"{row.label_text} is already at its default.")
            return
        if row.reset_to_default():
            self._owner._context.toast(f"{row.label_text} is back to its default.")
            self._owner._rebuild_panel()

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
            return
        if action is Action.OPTIONS:
            # The one place a previewable row can be put back: OPTIONS on
            # it *enters* this strip, so the restore that every other row
            # gets from that press had nowhere to live. Here it is better
            # than elsewhere — the home screen behind shows the default
            # arriving.
            row = self._owner._preview_row
            if row is None:
                return
            identity = row.identity
            self._restore_row(row)
            # A restore rebuilds the panel, which replaces every row widget
            # — including the one this strip is holding. Find it again by
            # name, or `_step_preview` looks for a row that is no longer in
            # the list it indexes.
            replacement = next(
                (
                    candidate
                    for candidate in self._owner._panel_list.rows
                    if candidate.identity == identity
                ),
                None,
            )
            if replacement is None:
                # Nothing left to steer with; leave while the strip still
                # holds a row, because that is what tears it down.
                self._owner._leave_preview()
                return
            self._owner._preview_row = replacement
            self._owner._refresh_preview()

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
        control_center.open_panel(panel, self._owner._context.toast)

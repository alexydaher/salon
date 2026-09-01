# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings import preview_policy
from salon.ui.settings.screen_shared import Action, Pane, Panel


def _panel_name(panel: Panel) -> str:
    """What to call a panel on screen.

    The tile editor's title was the word "Tile" and its breadcrumb read
    `Tiles › Row › Tile` — three levels of navigation naming nothing you
    had navigated to. A panel whose subject has a name supplies it through
    `live_title`, read now rather than when the panel was built, because
    renaming a tile is one of the things its own editor does.
    """
    if panel.live_title is not None:
        try:
            live = panel.live_title()
        except Exception:  # noqa: BLE001 - a summary may not be answerable yet
            live = ""
        if live:
            return live
    return panel.title


class SettingsNavigationController(ServiceComponent):
    def _enter_section(self, index: int) -> None:
        self._owner._popup.close()
        self._owner._sections.select(index)
        self._set_stack([self._owner._section_panels[index]])
        self._owner._pane = Pane.PANEL
        self._rebuild_panel()

    def _push(self, panel: Panel) -> None:
        self._owner._popup.close()
        self._owner._stack.append(panel)
        self._owner._pane = Pane.PANEL
        self._rebuild_panel()

    def _pop(self) -> None:
        self._owner._popup.close()
        if len(self._owner._stack) > 1:
            self._leave_panels([self._owner._stack.pop()])
            self._rebuild_panel()
        else:
            self._owner._pane = Pane.SECTIONS
            self._update_pane_style()

    def _set_stack(self, panels: list[Panel]) -> None:
        """Replace the whole stack, telling whatever was on it that it is
        gone. Jumping straight to another section is a way of leaving every
        panel currently open, and a panel that switched something on while
        it was up (Bluetooth discovery) has to hear about it."""
        leaving = [panel for panel in self._owner._stack if panel not in panels]
        self._owner._stack = panels
        self._leave_panels(leaving)

    @staticmethod
    def _leave_panels(panels: list[Panel]) -> None:
        for panel in panels:
            if panel.on_leave is not None:
                panel.on_leave()

    def _rebuild_panel(self) -> None:
        if not self._owner._stack:
            return
        panel = self._owner._stack[-1]
        # Keep the cursor only when this is the *same* panel being rebuilt.
        # `_rebuild_panel` serves both "a value changed, redraw the rows"
        # and "we are now looking at a different panel", and treating the
        # second as the first is why the first-actionable-row rule never
        # fired: About and Setup both opened on a read-only row with the
        # legend reading "Nothing to change on this row", which is the bug
        # `_first_stop` exists to prevent.
        same = panel is self._owner._built_panel
        self._owner._built_panel = panel
        self._owner._panel_list.set_rows(panel.build(), keep_selection=same)
        trail = " › ".join(_panel_name(p) for p in self._owner._stack)
        self._owner._breadcrumb.set_label(trail if len(self._owner._stack) > 1 else "")
        self._update_pane_style()

    def _update_pane_style(self) -> None:
        sections = self._owner._pane is Pane.SECTIONS
        self._owner._sections.set_active(sections)
        self._owner._panel_list.set_active(not sections)
        self._owner._title.set_label(
            "Settings" if sections else _panel_name(self._owner._stack[-1])
        )
        panel = self._owner._stack[-1]
        self._owner._summary.set_label(panel.subtitle)
        # The section list is orientation, and three levels into the tile
        # editor it is orienting you to somewhere you left: it kept saying
        # "Tiles" while the panel beside it was one tile's artwork. Past
        # the first level the breadcrumb is the thing that knows where you
        # are, and the column steps back to being a place, not a cursor.
        self._owner._sections_host.set_visible(len(self._owner._stack) <= 1)
        self._update_legend()

    def _update_legend(self) -> None:
        """The legend is per-row, because what the buttons do is per-row.

        A fixed line would have to describe every kind of row at once,
        which is how "LEFT/RIGHT adjusts" ended up printed under rows that
        adjust nothing.
        """
        if self._owner._pane is Pane.SECTIONS:
            self._owner._legend.set_label(
                "OK or RIGHT opens · BACK returns home · GROUP changes section"
            )
            self._owner._legend.set_hints(((Action.OK, "Open"), (Action.BACK, "Home")))
            return
        row = self._owner._panel_list.selected_row
        if self._owner._popup.is_open and row is not None:
            direction = "LEFT/RIGHT" if row.previewable else "UP/DOWN"
            self._owner._legend.set_label(
                f"{direction} picks · OK sets · BACK cancels · MENU goes home"
            )
            self._owner._legend.set_hints(
                ((Action.OK, "Set"), (Action.BACK, "Cancel"), (Action.MENU, "Home"))
            )
            return
        parts = [
            preview_policy.choosing_hint(row.hint, row.previewable)
            if row is not None
            else "OK selects"
        ]
        if row is not None and row.previewable:
            # OK on these opens the list over the live home screen, so the
            # hint above already differs. OPTIONS is the same strip without
            # the list: LEFT/RIGHT walks the value with nothing covering
            # the screen at all, which is the better way to judge a safe
            # area or a tile size once you know what you are looking for.
            parts.append("OPTIONS adjusts it there")
        elif row is not None and row.modified:
            # The only other thing OPTIONS has to offer on a settings row,
            # and it is worth naming: without it, "you have changed this"
            # is a dot with no way to act on it.
            parts.append("OPTIONS restores the default")
        parts.append(
            "BACK goes back" if len(self._owner._stack) > 1 else "BACK returns to sections"
        )
        parts.append("MENU goes home")
        self._owner._legend.set_label("  ·  ".join(parts))
        hints = [(Action.OK, "Choose")]
        if row is not None and row.previewable:
            hints.append((Action.OPTIONS, "Preview"))
        elif row is not None and row.modified:
            hints.append((Action.OPTIONS, "Restore"))
        hints.append(
            (Action.BACK, "Back" if len(self._owner._stack) > 1 else "Sections")
        )
        hints.append((Action.MENU, "Home"))
        self._owner._legend.set_hints(tuple(hints))

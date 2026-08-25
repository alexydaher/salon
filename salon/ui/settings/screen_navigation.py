# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings.screen_shared import Pane, Panel


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
        self._owner._panel_list.set_rows(panel.build(), keep_selection=True)
        self._owner._title.set_label(panel.title)
        trail = " › ".join(p.title for p in self._owner._stack)
        self._owner._breadcrumb.set_label(trail if len(self._owner._stack) > 1 else "")
        self._update_pane_style()

    def _update_pane_style(self) -> None:
        sections = self._owner._pane is Pane.SECTIONS
        self._owner._sections.set_active(sections)
        self._owner._panel_list.set_active(not sections)
        self._owner._title.set_label("Settings" if sections else self._owner._stack[-1].title)
        self._update_legend()

    def _update_legend(self) -> None:
        """The legend is per-row, because what the buttons do is per-row.

        A fixed line would have to describe every kind of row at once,
        which is how "LEFT/RIGHT adjusts" ended up printed under rows that
        adjust nothing.
        """
        if self._owner._pane is Pane.SECTIONS:
            self._owner._legend.set_label(
                "A/OK or RIGHT opens  ·  B/BACK returns home  ·  LB/RB changes section"
            )
            return
        row = self._owner._panel_list.selected_row
        if self._owner._popup.is_open and row is not None:
            self._owner._legend.set_label(
                "UP/DOWN picks  ·  A/OK sets  ·  B/BACK cancels  ·  START goes home"
            )
            return
        parts = [row.hint if row is not None else "A/OK selects"]
        if row is not None and row.previewable:
            # OK is spoken for on these: it collapses to the preview strip,
            # which is the only way to judge an accent or a tile size. The
            # list is still there on RIGHT for anyone who knows the value
            # they want.
            parts.append("A/OK previews")
            parts[0] = "RIGHT lists values" if row.choices else "RIGHT changes it"
        parts.append(
            "B/BACK goes back" if len(self._owner._stack) > 1 else "B/BACK returns to sections"
        )
        parts.append("START goes home")
        self._owner._legend.set_label("  ·  ".join(parts))

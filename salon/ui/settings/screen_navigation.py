# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings.screen_shared import *


class SettingsNavigationController(ServiceComponent):
    def _enter_section(self, index: int) -> None:
        self._popup.close()
        self._sections.select(index)
        self._set_stack([self._section_panels[index]])
        self._pane = Pane.PANEL
        self._rebuild_panel()

    def _push(self, panel: Panel) -> None:
        self._popup.close()
        self._stack.append(panel)
        self._pane = Pane.PANEL
        self._rebuild_panel()

    def _pop(self) -> None:
        self._popup.close()
        if len(self._stack) > 1:
            self._leave_panels([self._stack.pop()])
            self._rebuild_panel()
        else:
            self._pane = Pane.SECTIONS
            self._update_pane_style()

    def _set_stack(self, panels: list[Panel]) -> None:
        """Replace the whole stack, telling whatever was on it that it is
        gone. Jumping straight to another section is a way of leaving every
        panel currently open, and a panel that switched something on while
        it was up (Bluetooth discovery) has to hear about it."""
        leaving = [panel for panel in self._stack if panel not in panels]
        self._stack = panels
        self._leave_panels(leaving)

    @staticmethod
    def _leave_panels(panels: list[Panel]) -> None:
        for panel in panels:
            if panel.on_leave is not None:
                panel.on_leave()

    def _rebuild_panel(self) -> None:
        if not self._stack:
            return
        panel = self._stack[-1]
        self._panel_list.set_rows(panel.build(), keep_selection=True)
        self._title.set_label(panel.title)
        trail = " › ".join(p.title for p in self._stack)
        self._breadcrumb.set_label(trail if len(self._stack) > 1 else "")
        self._update_pane_style()

    def _update_pane_style(self) -> None:
        sections = self._pane is Pane.SECTIONS
        self._sections.set_active(sections)
        self._panel_list.set_active(not sections)
        self._update_legend()

    def _update_legend(self) -> None:
        """The legend is per-row, because what the buttons do is per-row.

        A fixed line would have to describe every kind of row at once,
        which is how "LEFT/RIGHT adjusts" ended up printed under rows that
        adjust nothing.
        """
        if self._pane is Pane.SECTIONS:
            self._legend.set_label(
                "OK or RIGHT opens a section  ·  LEFT or BACK returns to the home screen"
            )
            return
        row = self._panel_list.selected_row
        if self._popup.is_open and row is not None:
            self._legend.set_label(
                f"UP and DOWN pick a value for {row.label_text}"
                "  ·  OK sets it  ·  BACK or LEFT leaves it as it was"
            )
            return
        parts = [row.hint if row is not None else "OK selects"]
        if row is not None and row.previewable:
            # OK is spoken for on these: it collapses to the preview strip,
            # which is the only way to judge an accent or a tile size. The
            # list is still there on RIGHT for anyone who knows the value
            # they want.
            parts.append("OK previews it on the home screen")
            parts[0] = "RIGHT opens the list" if row.choices else "RIGHT changes it here"
        parts.append(
            "LEFT or BACK goes up a level"
            if len(self._stack) > 1
            else "LEFT or BACK returns to the sections"
        )
        self._legend.set_label("  ·  ".join(parts))

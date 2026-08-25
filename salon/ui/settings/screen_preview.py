# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings.screen_shared import SettingsRow


class SettingsPreviewController(ServiceComponent):
    def _enter_preview(self, row: SettingsRow) -> None:
        """Collapse to a strip on the bottom edge and let the home screen
        render behind it.

        Nothing is duplicated or mocked up here: the thing behind the strip
        *is* the home screen, still bound to the same GSettings keys these
        rows write, so what the user sees while adjusting is exactly what
        they get when they leave. That's the whole reason this exists —
        "Row density 85%" is not a claim anyone can evaluate.
        """
        self._owner._preview_row = row
        self._owner._content.set_visible(False)
        self._owner._preview_bar.set_visible(True)
        self._owner.add_css_class("preview")
        self._refresh_preview()

    def _leave_preview(self) -> None:
        if self._owner._preview_row is None:
            return
        self._owner._preview_row = None
        self._owner._preview_bar.set_visible(False)
        self._owner._content.set_visible(True)
        self._owner.remove_css_class("preview")
        # The row's own value label is stale by now: the strip has been
        # writing straight through to GSettings while the list was hidden.
        self._owner._panel_list.refresh_values()

    def _refresh_preview(self) -> None:
        row = self._owner._preview_row
        if row is None:
            return
        row.refresh()
        self._owner._preview_label.set_label(row.label_text)
        self._owner._preview_value.set_label(f"‹  {row.value_text}  ›")
        self._owner._preview_hint.set_label(
            "LEFT/RIGHT adjusts · UP/DOWN changes setting · OK/BACK returns · MENU home"
        )

    def _previewable_indices(self) -> list[int]:
        return [i for i, row in enumerate(self._owner._panel_list.rows) if row.previewable]

    def _step_preview(self, delta: int) -> None:
        """UP/DOWN inside the strip walks the *previewable* rows only.

        Stepping through every row would put "Browser command" in a bar that
        has no keyboard and nothing to show behind it; these four are the
        ones the home screen answers for.
        """
        indices = self._previewable_indices()
        if not indices or self._owner._preview_row is None:
            return
        current = self._owner._panel_list.rows.index(self._owner._preview_row)
        position = indices.index(current)
        target = position + delta
        if not (0 <= target < len(indices)):
            return
        self._owner._panel_list.select(indices[target])
        self._owner._preview_row = self._owner._panel_list.rows[indices[target]]
        self._refresh_preview()

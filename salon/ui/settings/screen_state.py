# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings.screen_shared import *


class SettingsStateController(ServiceComponent):
    def _build_sections(self) -> None:
        context = self._context
        settings = self._settings
        self._section_panels = [
            tile_panels.rows_panel(context),
            provider_panels.providers_panel(
                context,
                settings,
                self._provider_registry,
                self._provider_outcomes,
                self._reload_catalog,
            ),
            panel_builders.network_panel(context, settings),
            panel_builders.appearance_panel(context, settings),
            panel_builders.input_panel(context, settings),
            panel_builders.browser_panel(context, settings),
            panel_builders.audio_panel(context, settings),
            panel_builders.system_panel(context, settings),
            panel_builders.about_panel(context, settings),
        ]
        rows: list[SettingsRow] = [
            ActionRow(
                panel.title,
                lambda i=index: self._enter_section(i),
                value="›",
                icon_name=panel.icon_name,
            )
            for index, panel in enumerate(self._section_panels)
        ]
        self._sections.set_rows(rows)

    def _save(self) -> None:
        """Write the catalogue, then rebuild: every editing call site does
        `edit(); save_config()`, and a panel that still showed the old row
        order after a move would be the first thing anyone noticed."""
        self._host_save()
        self._rebuild_panel()

    def set_config(self, config: Config) -> None:
        """Repoint at a freshly loaded catalogue. Our own save comes back
        through the file monitor as a *new* Config object, so without this
        the next edit would be applied to a detached copy."""
        self._context.config = config
        if self.get_visible():
            self._rebuild_panel()

    def open(self) -> None:
        self._popup.close()
        self._pane = Pane.SECTIONS
        self._set_stack([self._section_panels[self._sections.selected_index]])
        self._leave_preview()
        self.set_visible(True)
        self._begin_fade()
        self._rebuild_panel()

    def open_at(self, panel_id: str, deeper: list[Panel] | None = None) -> None:
        """Open Settings already inside a section, optionally deeper still.

        Exists because a menu item named "About Salon" that lands on the
        section list is indistinguishable from one named "Settings", and
        "Edit tiles…" pressed over Netflix should arrive at *Netflix* — not
        four navigations away from it.
        """
        index = next(
            (i for i, panel in enumerate(self._section_panels) if panel.panel_id == panel_id),
            None,
        )
        if index is None:
            self.open()
            return
        self._popup.close()
        self._sections.select(index)
        self._set_stack([self._section_panels[index], *(deeper or [])])
        self._pane = Pane.PANEL
        self._leave_preview()
        self.set_visible(True)
        self._begin_fade()
        self._rebuild_panel()

    def open_tile(self, row_id: str, tile_id: str) -> None:
        """Straight to one tile's editor, three panels deep."""
        self.open_at(
            "tiles",
            [
                tile_panels.row_panel(self._context, row_id),
                tile_panels.tile_panel(self._context, row_id, tile_id),
            ],
        )

    def close(self) -> None:
        self._popup.close()
        self._leave_panels(self._stack)
        # Emptied, not kept: reopening builds a fresh stack, and a panel
        # still sitting here would be told it had left a second time.
        self._stack = []
        self._leave_preview()
        self.set_visible(False)
        self._on_close()

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        margin = scale.px(
            tokens.REFERENCE_VIEWPORT_HEIGHT_PX * tokens.SAFE_AREA_DEFAULT_PERCENT / 100.0
        )
        self._content.set_margin_start(margin)
        self._content.set_margin_end(margin)
        self._content.set_margin_top(margin)
        self._content.set_margin_bottom(margin)
        self._content.set_spacing(scale.px(8.0))
        self._body.set_spacing(scale.px(48.0))
        self._body.set_margin_top(scale.px(24.0))
        self._sections_host.set_size_request(scale.px(420.0), -1)
        self._sections.set_scale(scale)
        self._panel_list.set_scale(scale)
        self._preview_bar.set_spacing(scale.px(24.0))
        self._preview_bar.set_margin_start(margin)
        self._preview_bar.set_margin_end(margin)
        self._preview_bar.set_margin_bottom(margin)
        self._popup.set_scale(scale)

    def set_pointer_active(self, active: bool) -> None:
        self._pointer_active = active
        self._sections.set_hover_enabled(active)
        self._panel_list.set_hover_enabled(active)
        self._popup.set_hover_enabled(active)

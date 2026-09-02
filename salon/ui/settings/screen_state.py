# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings.screen_shared import (
    ActionRow,
    Config,
    Pane,
    Panel,
    Scale,
    SettingsRow,
    panel_builders,
    provider_panels,
    tile_panels,
    tokens,
)


def _section_detail(panel: Panel) -> str:
    """The live summary, when the section has useful state to report.

    Guarded: a summary reads real state — an audio sink, a network — and
    the section list is built before any of those have answered. A section
    that cannot describe itself yet falls back rather than failing.
    """
    if panel.summary is not None:
        try:
            live = panel.summary()
        except Exception:  # noqa: BLE001 - a summary may not be answerable yet
            live = ""
        if live:
            return live
    return ""


class SettingsStateController(ServiceComponent):
    def _build_sections(self) -> None:
        context = self._owner._context
        settings = self._owner._settings
        self._owner._section_panels = [
            tile_panels.rows_panel(context),
            provider_panels.providers_panel(
                context,
                settings,
                self._owner._provider_registry,
                self._owner._provider_outcomes,
                self._owner._reload_catalog,
            ),
            panel_builders.appearance_panel(context, settings),
            panel_builders.audio_panel(context, settings),
            panel_builders.input_panel(context, settings),
            panel_builders.network_panel(context, settings),
            panel_builders.system_panel(context, settings),
            panel_builders.about_panel(context, settings),
        ]
        rows: list[SettingsRow] = [
            ActionRow(
                panel.title,
                lambda i=index: self._owner._enter_section(i),
                value="›",
                icon_name=panel.icon_name,
                # State, when the section has something useful to report.
                detail=_section_detail(panel),
            )
            for index, panel in enumerate(self._owner._section_panels)
        ]
        self._owner._sections.set_rows(rows)

    def _save(self) -> None:
        """Write the catalogue, then rebuild: every editing call site does
        `edit(); save_config()`, and a panel that still showed the old row
        order after a move would be the first thing anyone noticed."""
        self._owner._host_save()
        self._owner._rebuild_panel()

    def set_config(self, config: Config) -> None:
        """Repoint at a freshly loaded catalogue. Our own save comes back
        through the file monitor as a *new* Config object, so without this
        the next edit would be applied to a detached copy."""
        self._owner._context.config = config
        if self._owner.get_visible():
            self._owner._rebuild_panel()

    def open(self) -> None:
        self._owner._popup.close()
        self._owner._pane = Pane.SECTIONS
        self._owner._set_stack([self._owner._section_panels[self._owner._sections.selected_index]])
        self._owner._leave_preview()
        self._owner.set_visible(True)
        self._owner._begin_fade()
        self._owner._rebuild_panel()

    def open_at(self, panel_id: str, deeper: list[Panel] | None = None) -> None:
        """Open Settings already inside a section, optionally deeper still.

        Exists because a menu item named "About Salon" that lands on the
        section list is indistinguishable from one named "Settings", and
        "Edit tiles…" pressed over Netflix should arrive at *Netflix* — not
        four navigations away from it.
        """
        index = next(
            (
                i
                for i, panel in enumerate(self._owner._section_panels)
                if panel.panel_id == panel_id
            ),
            None,
        )
        if index is None:
            self.open()
            return
        self._owner._popup.close()
        self._owner._sections.select(index)
        self._owner._set_stack([self._owner._section_panels[index], *(deeper or [])])
        self._owner._pane = Pane.PANEL
        self._owner._leave_preview()
        self._owner.set_visible(True)
        self._owner._begin_fade()
        self._owner._rebuild_panel()

    def open_tile(self, row_id: str, tile_id: str) -> None:
        """Straight to one tile's editor, three panels deep."""
        self.open_at(
            "tiles",
            [
                tile_panels.row_panel(self._owner._context, row_id),
                tile_panels.tile_panel(self._owner._context, row_id, tile_id),
            ],
        )

    def close(self) -> None:
        self._owner._popup.close()
        self._owner._leave_panels(self._owner._stack)
        # Emptied, not kept: reopening builds a fresh stack, and a panel
        # still sitting here would be told it had left a second time.
        self._owner._stack = []
        self._owner._built_panel = None
        self._owner._leave_preview()
        self._owner.set_visible(False)
        self._owner._on_close()

    def set_scale(self, scale: Scale) -> None:
        self._owner._scale = scale
        horizontal = scale.px(64.0)
        self._owner._content.set_margin_start(horizontal)
        self._owner._content.set_margin_end(horizontal)
        self._owner._content.set_margin_top(scale.px(34.0))
        self._owner._content.set_margin_bottom(scale.px(44.0))
        self._owner._content.set_spacing(scale.px(8.0))
        self._owner._header.set_spacing(scale.px(32.0))
        self._owner._body.set_spacing(scale.px(34.0))
        self._owner._body.set_margin_top(scale.px(19.0))
        # 420du here cut seven of the nine live summaries mid-word
        # ("Midnight · Lamplight am…"), which is most of the value of
        # having them — the point is answering the visit without entering
        # the section. The panel beside it is capped at 1150du anyway, so
        # the extra 100du comes out of dead space rather than out of a row.
        self._owner._sections_host.set_size_request(scale.px(540.0), -1)
        self._owner._sections_host.set_margin_bottom(scale.px(140.0))
        self._owner._sections.set_scale(scale)
        self._owner._panel_list.set_scale(scale)
        self._owner._legend.set_scale(scale)
        self._owner._preview_bar.set_margin_start(scale.px(tokens.CONSOLE_WIDTH_DU))
        self._owner._preview_bar.set_margin_end(0)
        self._owner._preview_bar.set_margin_bottom(0)
        self._owner._preview_bar.set_scale(scale)
        self._owner._popup.set_scale(scale)

    def set_pointer_active(self, active: bool) -> None:
        self._owner._pointer_active = active
        self._owner._sections.set_hover_enabled(active)
        self._owner._panel_list.set_hover_enabled(active)
        self._owner._popup.set_hover_enabled(active)

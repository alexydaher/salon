# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings screen shell (§6.8).

Two panes, like search: sections on the left, the current panel on the
right. RIGHT or OK from a section enters it; LEFT always leaves, whichever
pane and however deep. Panels form a stack, so the tile editor can drill
from rows to one row to one tile and BACK unwinds it a level at a time
rather than dumping the user back at the home screen.

The horizontal axis reads the same way at every depth: **RIGHT goes in,
LEFT comes back out**, and LEFT is never a value change. A row with a set of
values does not change on a direction key at all — OK raises the values as a
small list beside the row (`popup.py`) and the choice is made there, which is
how a console does it and the only arrangement where the alternatives can be
seen before one is picked. See `widgets.py` for the two designs this
replaced and why.

Panels are rebuilt from their `build()` callback whenever anything changes,
rather than mutated in place. A settings list is a few dozen widgets and
the alternative — keeping a retained tree in sync with a catalogue the user
is actively editing — is exactly the kind of bookkeeping that goes wrong
quietly.

Two things here are about being able to *leave*, which is not a detail on a
device with no window controls:

* a legend along the bottom naming what each button does, because BACK
  unwinding one level at a time is only obvious to whoever wrote it;
* LEFT from the section list, and MENU from anywhere, both close the screen
  outright — so there is always a single press between Settings and home
  however deep the tile editor has been walked into.

And one is about being able to *see*: a row marked `preview` collapses this
whole screen to a strip along the bottom edge and lets the live home screen
render behind it, because accent colour, tile size, row density and safe
area cannot be judged against a list of their own names.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gio, GLib, Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.config import Config  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.core.provider import ProviderOutcome  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.providers.registry import ProviderRegistry  # noqa: E402
from salon.ui import motion  # noqa: E402
from salon.ui.motion import SizeReporter  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings import panels as panel_builders  # noqa: E402
from salon.ui.settings import providers as provider_panels  # noqa: E402
from salon.ui.settings import tiles as tile_panels  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.popup import ValuePopup  # noqa: E402
from salon.ui.settings.widgets import ActionRow, SettingsList, SettingsRow  # noqa: E402

_BUMP_DISTANCE_DU = 26.0
_MAX_NOTES = 12


class Pane(Enum):
    SECTIONS = auto()
    PANEL = auto()


class SettingsScreen(Gtk.Box, motion.FadesIn):
    def __init__(
        self,
        scale: Scale,
        settings: Gio.Settings,
        *,
        config: Config,
        save_config: Callable[[], None],
        toast: Callable[[str], None],
        edit_text: Callable[[str, str, Callable[[str | None], None]], None],
        installed_apps: Callable[[Callable[[list[Tile]], None]], None],
        provider_registry: ProviderRegistry,
        provider_outcomes: Callable[[], tuple[ProviderOutcome, ...]],
        reload_catalog: Callable[[], None],
        quit_app: Callable[[], None],
        on_close: Callable[[], None],
        phone_remote_running: Callable[[], bool],
        set_phone_remote: Callable[[bool], bool],
        phone_remote_hint: Callable[[], str],
        pointer_backend: Callable[[], str],
        bindings: Callable[[], object],
        capture_binding: Callable[[Callable[[str, int], None]], None],
        cancel_capture: Callable[[], None],
        rebind: Callable[[str, int, str], None],
        reset_bindings: Callable[[], None],
        version: str,
        config_path: str,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._init_fade()
        self.add_css_class("salon-search")  # same full-bleed dark field
        self.set_visible(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._scale = scale
        self._settings = settings
        self._on_close = on_close
        self._host_save = save_config
        self._provider_registry = provider_registry
        self._provider_outcomes = provider_outcomes
        self._reload_catalog = reload_catalog
        self._pane = Pane.SECTIONS
        self._stack: list[Panel] = []
        self._pointer_active = False

        self._context = SettingsContext(
            config=config,
            save_config=self._save,
            toast=toast,
            edit_text=edit_text,
            push=self._push,
            pop=self._pop,
            rebuild=self._rebuild_panel,
            quit_app=quit_app,
            close=self.close,
            installed_apps=installed_apps,
            open_control_center=self._open_control_center,
            phone_remote_running=phone_remote_running,
            set_phone_remote=set_phone_remote,
            phone_remote_hint=phone_remote_hint,
            pointer_backend=pointer_backend,
            bindings=bindings,
            capture_binding=capture_binding,
            cancel_capture=cancel_capture,
            rebind=rebind,
            reset_bindings=reset_bindings,
            version=version,
            config_path=config_path,
        )

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.append(self._content)

        self._title = Gtk.Label(label="Settings")
        self._title.add_css_class("salon-search-query")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        self._content.append(self._title)

        self._breadcrumb = Gtk.Label(label="")
        self._breadcrumb.add_css_class("salon-search-hint")
        self._breadcrumb.set_halign(Gtk.Align.START)
        self._content.append(self._breadcrumb)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)
        self._body = body
        self._content.append(body)

        self._sections = SettingsList(scale)
        # Fixed width, so the panel beside it gets everything else — two
        # lists that both expand end up splitting the screen down the
        # middle, which leaves the section names swimming in dead space.
        # propagate_minimum=False: a Gtk.Fixed measures to fit its children,
        # so a list longer than the screen would ask to be that tall, get
        # it, and then never scroll — see SizeReporter. The tile editor's
        # installed-app picker is fifty rows.
        self._sections_host = SizeReporter(
            self._sections, self._sections.on_resize, propagate_minimum=False
        )
        self._sections_host.set_vexpand(True)
        body.append(self._sections_host)

        self._panel_list = SettingsList(scale)
        self._panel_host = SizeReporter(
            self._panel_list, self._panel_list.on_resize, propagate_minimum=False
        )
        self._panel_host.set_hexpand(True)
        self._panel_host.set_vexpand(True)
        body.append(self._panel_host)

        # The list of values for whichever row is open. One instance for the
        # whole screen, re-parented onto each row it is opened for — see
        # popup.py on why it never stays attached.
        self._popup = ValuePopup(scale, on_chosen=self._on_value_chosen)
        # A click on a panel row takes the same path OK does. Without this a
        # row whose value lives in a list would answer a click with nothing:
        # there is no longer anything for `activate_row` to do on one.
        self._panel_list.set_activate_handler(self._activate_panel_row)

        self._legend = Gtk.Label()
        self._legend.add_css_class("salon-settings-legend")
        self._legend.set_halign(Gtk.Align.START)
        self._legend.set_ellipsize(Pango.EllipsizeMode.END)
        self._content.append(self._legend)

        # The preview strip lives outside _content so it can sit on the
        # bottom edge of the *screen* while everything above it is hidden
        # and the home screen shows through.
        self._preview_row: SettingsRow | None = None
        self._preview_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._preview_bar.add_css_class("salon-settings-preview-bar")
        self._preview_bar.set_visible(False)
        self._preview_bar.set_valign(Gtk.Align.END)
        self._preview_bar.set_vexpand(True)
        self.append(self._preview_bar)

        self._preview_label = Gtk.Label()
        self._preview_label.add_css_class("salon-settings-label")
        self._preview_label.set_halign(Gtk.Align.START)
        self._preview_label.set_hexpand(True)
        self._preview_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._preview_bar.append(self._preview_label)

        self._preview_value = Gtk.Label()
        self._preview_value.add_css_class("salon-settings-preview-value")
        self._preview_bar.append(self._preview_value)

        self._preview_hint = Gtk.Label()
        self._preview_hint.add_css_class("salon-settings-legend")
        self._preview_bar.append(self._preview_hint)

        self._content.set_vexpand(True)

        self._section_panels: list[Panel] = []
        self._build_sections()
        self.set_scale(scale)

    # --- lifecycle -------------------------------------------------------

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

    # --- panel stack -----------------------------------------------------

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

    # --- live preview ----------------------------------------------------

    def _enter_preview(self, row: SettingsRow) -> None:
        """Collapse to a strip on the bottom edge and let the home screen
        render behind it.

        Nothing is duplicated or mocked up here: the thing behind the strip
        *is* the home screen, still bound to the same GSettings keys these
        rows write, so what the user sees while adjusting is exactly what
        they get when they leave. That's the whole reason this exists —
        "Row density 85%" is not a claim anyone can evaluate.
        """
        self._preview_row = row
        self._content.set_visible(False)
        self._preview_bar.set_visible(True)
        self.add_css_class("preview")
        self._refresh_preview()

    def _leave_preview(self) -> None:
        if self._preview_row is None:
            return
        self._preview_row = None
        self._preview_bar.set_visible(False)
        self._content.set_visible(True)
        self.remove_css_class("preview")
        # The row's own value label is stale by now: the strip has been
        # writing straight through to GSettings while the list was hidden.
        self._panel_list.refresh_values()

    def _refresh_preview(self) -> None:
        row = self._preview_row
        if row is None:
            return
        row.refresh()
        self._preview_label.set_label(row.label_text)
        self._preview_value.set_label(f"‹  {row.value_text}  ›")
        self._preview_hint.set_label("BACK when it looks right")

    def _previewable_indices(self) -> list[int]:
        return [i for i, row in enumerate(self._panel_list.rows) if row.previewable]

    def _step_preview(self, delta: int) -> None:
        """UP/DOWN inside the strip walks the *previewable* rows only.

        Stepping through every row would put "Browser command" in a bar that
        has no keyboard and nothing to show behind it; these four are the
        ones the home screen answers for.
        """
        indices = self._previewable_indices()
        if not indices or self._preview_row is None:
            return
        current = self._panel_list.rows.index(self._preview_row)
        position = indices.index(current)
        target = position + delta
        if not (0 <= target < len(indices)):
            return
        self._panel_list.select(indices[target])
        self._preview_row = self._panel_list.rows[indices[target]]
        self._refresh_preview()

    # --- input -----------------------------------------------------------

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

    # --- odds and ends ---------------------------------------------------

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

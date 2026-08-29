# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Settings view composition and compatibility facade."""

from __future__ import annotations

from salon.ui.settings.screen_actions import SettingsActionController
from salon.ui.settings.screen_navigation import SettingsNavigationController
from salon.ui.settings.screen_preview import SettingsPreviewController
from salon.ui.settings.screen_shared import (
    ArtworkResolver,
    Callable,
    Config,
    Gio,
    Gtk,
    Pane,
    Panel,
    Pango,
    ProviderOutcome,
    ProviderRegistry,
    Scale,
    SettingsContext,
    SettingsList,
    SettingsRow,
    SizeReporter,
    Tile,
    ValuePopup,
    motion,
)
from salon.ui.settings.screen_state import SettingsStateController
from salon.ui.settings.screen_values import SettingsValuesController


class SettingsScreen(
    Gtk.Box,
    motion.FadesIn,
    SettingsStateController,
    SettingsNavigationController,
    SettingsPreviewController,
    SettingsValuesController,
    SettingsActionController,
):
    def __init__(
        self,
        scale: Scale,
        settings: Gio.Settings,
        *,
        config: Config,
        save_config: Callable[[], None],
        toast: Callable[[str], None],
        edit_text: Callable[[str, str, Callable[[str | None], None]], None],
        choose_path: Callable[[str, bool, Callable[[str | None], None]], None],
        installed_apps: Callable[[Callable[[list[Tile]], None]], None],
        artwork: ArtworkResolver,
        provider_registry: ProviderRegistry,
        provider_outcomes: Callable[[], tuple[ProviderOutcome, ...]],
        reload_catalog: Callable[[], None],
        quit_app: Callable[[], None],
        on_close: Callable[[], None],
        preview_chrome: Callable[[bool], None],
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
        self._owner = self
        self._init_fade()
        self.add_css_class("salon-search")  # same full-bleed dark field
        self.set_visible(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._scale = scale
        self._settings = settings
        self._on_close = on_close
        # Told when the home screen is the thing being looked at, so it can
        # take its own bottom bar out of the way of the strip.
        self._preview_chrome = preview_chrome
        self._host_save = save_config
        self._provider_registry = provider_registry
        self._provider_outcomes = provider_outcomes
        self._reload_catalog = reload_catalog
        self._pane = Pane.SECTIONS
        self._stack: list[Panel] = []
        # Which panel the row list currently holds, so a rebuild can tell
        # itself apart from a navigation. See `_rebuild_panel`.
        self._built_panel: Panel | None = None
        self._pointer_active = False

        self._context = SettingsContext(
            config=config,
            save_config=self._save,
            toast=toast,
            edit_text=edit_text,
            choose_path=choose_path,
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
            # The tile editor draws the tile it is editing, so it resolves
            # artwork exactly as the home screen does — same cache, same
            # fallbacks, same result. A bound method rather than the
            # resolver itself: the editor needs one call, not a service.
            resolve_artwork=artwork.resolve,
            scale=lambda: self._scale,
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
        # popup.py on why it never stays attached. The two extra callbacks
        # are live preview: on a previewable row the value under the cursor
        # is applied to the home screen behind, and dropping the list
        # without picking one puts the original back.
        self._popup = ValuePopup(
            scale,
            on_chosen=self._on_value_chosen,
            on_candidate=self._peek_candidate,
            on_dismissed=self._on_value_dismissed,
        )
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
        # The same strip, entered from OK rather than OPTIONS, with the
        # row's value list open above it. `_peek_restore` is the choice the
        # row held when the list opened, because BACK has to undo whatever
        # walking the list wrote.
        self._peek_row: SettingsRow | None = None
        self._peek_restore = ""
        self._preview_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._preview_bar.add_css_class("salon-settings-preview-bar")
        self._preview_bar.set_visible(False)
        self._preview_bar.set_valign(Gtk.Align.END)
        self._preview_bar.set_vexpand(True)
        self.append(self._preview_bar)

        # Label and value sit together on the left and the hint takes the
        # rest: the label used to expand, which pushed the two halves of one
        # statement a thousand pixels apart and left the value touching the
        # hint. "Tile size" and "65%" are one thing being said.
        self._preview_label = Gtk.Label()
        self._preview_label.add_css_class("salon-settings-label")
        self._preview_label.set_halign(Gtk.Align.START)
        self._preview_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._preview_bar.append(self._preview_label)

        self._preview_value = Gtk.Label()
        self._preview_value.add_css_class("salon-settings-preview-value")
        self._preview_value.set_halign(Gtk.Align.START)
        self._preview_bar.append(self._preview_value)

        self._preview_hint = Gtk.Label()
        self._preview_hint.add_css_class("salon-settings-legend")
        self._preview_hint.set_hexpand(True)
        self._preview_hint.set_halign(Gtk.Align.END)
        self._preview_hint.set_ellipsize(Pango.EllipsizeMode.END)
        self._preview_bar.append(self._preview_hint)

        self._content.set_vexpand(True)

        self._section_panels: list[Panel] = []
        self._build_sections()
        self.set_scale(scale)

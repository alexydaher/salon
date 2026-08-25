# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Home screen composition root and compatibility view."""

from __future__ import annotations

from typing import Any

from salon.services.component import component_attribute
from salon.ui.home_action_router import HomeActionRouter
from salon.ui.home_bindings import HomeBindingController
from salon.ui.home_catalog import HomeCatalogController
from salon.ui.home_focus import HomeFocusController
from salon.ui.home_idle import HomeIdleController
from salon.ui.home_launching import HomeLaunchController
from salon.ui.home_layout_build import HomeLayoutBuilder
from salon.ui.home_navigation import HomeNavigationController
from salon.ui.home_overlays import HomeOverlayController
from salon.ui.home_phone_catalog import HomePhoneCatalogController
from salon.ui.home_phone_input import HomePhoneInputController
from salon.ui.home_phone_lifecycle import HomePhoneLifecycleController
from salon.ui.home_preferences import HomePreferences
from salon.ui.home_reload_pointer import HomeReloadAndPointerController
from salon.ui.home_repeat import HomeRepeatController
from salon.ui.home_rows import *
from salon.ui.home_scrolling import HomeScrollController
from salon.ui.home_setup_catalog import HomeCatalogSetup
from salon.ui.home_setup_foundation import HomeFoundationSetup
from salon.ui.home_setup_input import HomeInputSetup
from salon.ui.home_setup_monitors import HomeMonitorSetup
from salon.ui.home_setup_surfaces import HomeSurfaceSetup
from salon.ui.home_shared import *
from salon.ui.home_spring import *
from salon.ui.home_viewport import *


class HomeView(Gtk.Box):
    def __init__(
        self, application: Gtk.Application, scale_manager: ScaleManager, theme_manager: ThemeManager
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._components = (
            HomeFoundationSetup(self),
            HomeSurfaceSetup(self),
            HomeCatalogSetup(self),
            HomeInputSetup(self),
            HomeMonitorSetup(self),
            HomePreferences(self),
            HomeCatalogController(self),
            HomeLayoutBuilder(self),
            HomeFocusController(self),
            HomeScrollController(self),
            HomeReloadAndPointerController(self),
            HomeBindingController(self),
            HomeIdleController(self),
            HomePhoneInputController(self),
            HomePhoneCatalogController(self),
            HomePhoneLifecycleController(self),
            HomeRepeatController(self),
            HomeActionRouter(self),
            HomeNavigationController(self),
            HomeOverlayController(self),
            HomeLaunchController(self),
        )
        self._setup_foundation(application, scale_manager, theme_manager)
        self._setup_surfaces(application, scale_manager, theme_manager)
        self._setup_catalog(application, scale_manager, theme_manager)
        self._setup_input(application, scale_manager, theme_manager)
        self._setup_monitors(application, scale_manager, theme_manager)

    def __getattr__(self, name: str) -> Any:
        return component_attribute(self._components, name)

# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    CEC,
    Action,
    Bindings,
    Callable,
    GLib,
    cec_out,
)


class HomeBindingController(ServiceComponent):
    def _apply_cec_setting(self) -> None:
        """Start or stop the CEC source, and wake the television when it's
        turned on. Starting `cec-client` claims the adapter, so this only
        ever runs when the user asked for it."""
        if self._owner._settings.get_boolean("cec-enabled"):
            if not self._owner._cec.running and self._owner._cec.start():
                cec_out.wake_display()
        else:
            self._owner._cec.stop()

    def _on_cec_action(self, action: Action) -> None:
        self._owner._note_input_source(CEC)
        if self._owner._binding_capture is not None:
            return
        # A TV remote produces discrete presses with no key-up, so it feeds
        # _handle_action directly rather than the Repeater — the television
        # is already doing its own auto-repeat.
        self._owner._set_pointer_visible(False)
        self._owner._handle_action(action)

    def _reload_bindings(self) -> None:
        self._owner._bindings = Bindings(self._owner._settings.get_value("input-bindings").unpack())
        self._owner._gamepad.set_bindings(self._owner._bindings)
        self._owner._cec.set_bindings(self._owner._bindings)

    def _save_bindings(self) -> None:
        self._owner._settings.set_value(
            "input-bindings", GLib.Variant("a{ss}", self._owner._bindings.to_storage())
        )

    def begin_binding_capture(self, on_captured: Callable[[str, int], None]) -> None:
        """Wait for the next physical button, from any source, and hand its
        code back.

        Every source is armed at once on purpose: someone rebinding OK does
        not want to be asked first whether they are holding a controller or
        pointing a remote. Whatever they press is the answer, including a
        button that currently does nothing — which is exactly the case
        rebinding exists for.
        """
        self._owner._binding_capture = on_captured

    def cancel_binding_capture(self) -> None:
        self._owner._binding_capture = None

    def _on_raw_input(self, source: str, code: int) -> None:
        capture = self._owner._binding_capture
        if capture is None:
            return
        self._owner._binding_capture = None
        capture(source, code)

    def bindings(self) -> Bindings:
        return self._owner._bindings

    def rebind(self, source: str, code: int, action: str) -> None:
        self._owner._bindings.bind(source, code, action)
        self._save_bindings()

    def reset_bindings(self) -> None:
        self._owner._bindings.clear_all()
        self._save_bindings()

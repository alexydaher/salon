# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import (
    _DIRECTIONS,
    _REPEAT_POLL_MS,
    Action,
    GLib,
)


class HomeRepeatController(ServiceComponent):
    def _on_gamepad_action(self, action: Action) -> None:
        if self._owner._binding_capture is not None:
            # The press is being captured as a binding; acting on it as
            # well would navigate away from the screen doing the capturing.
            return
        self._owner._set_pointer_visible(self._owner._pointer_mode)
        if action in _DIRECTIONS:
            self._start_repeat(action)
        self._handle_action(action)

    def _start_repeat(self, action: Action) -> None:
        self._owner._repeater.press(action)
        self._owner._repeat_action = action
        if self._owner._repeat_timer_id is None:
            self._owner._repeat_timer_id = GLib.timeout_add(_REPEAT_POLL_MS, self._poll_repeat)

    def _stop_repeat(self, action: Action) -> None:
        if self._owner._repeat_action is action:
            self._owner._repeater.release()
            self._owner._repeat_action = None

    def _poll_repeat(self) -> bool:
        action = self._owner._repeater.poll()
        if action is not None:
            self._handle_action(action)
        return bool(GLib.SOURCE_CONTINUE)

    def _handle_action(self, action: Action) -> None:
        """Every input source lands here, and every screen change starts
        here — so this is also the one place the phone's snapshot has to be
        refreshed from. Wrapping the dispatch rather than adding a publish
        to each of its two dozen early returns: one of those would have been
        forgotten, and the symptom would be a phone showing the wrong screen
        with no clue why."""
        self._owner._dispatch_action(action)
        self._owner._publish_remote_state()

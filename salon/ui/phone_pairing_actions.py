# SPDX-License-Identifier: GPL-3.0-or-later
"""Safe action state for the phone-pairing card."""


class PhonePairingActions:
    def _request_stop(self) -> None:
        self._confirming_stop = True
        self._address.set_label("Stop the phone remote?")
        self._status.set_label("This phone will stop controlling Salon.")
        self._rows[0].set_label("Cancel")
        self._rows[1].set_label("Stop phone remote")
        self._select(0)

    def _cancel_stop(self) -> None:
        self._confirming_stop = False
        self._restore_buttons()
        self._refresh()

    def _restore_buttons(self) -> None:
        self._rows[0].set_label("Done")
        self._rows[1].set_label("Stop phone remote")

    def _activate(self, index: int) -> None:
        if self._confirming_stop:
            self._cancel_stop() if index == 0 else self._stop()
        elif index == 0:
            self.close()
        else:
            self._request_stop()

# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.action_rows import ActionRow  # noqa: E402
from salon.ui.settings.settings_list import SettingsList  # noqa: E402


def test_unavailable_row_exposes_reason_and_cannot_activate() -> None:
    Gtk.init()
    actions: list[str] = []
    row = ActionRow("Wi-Fi configuration", lambda: actions.append("activated"))
    row.make_unavailable("Managed by the host outside Flatpak")
    rows = SettingsList(Scale(1080))
    rows.set_rows([row])
    rows.activate()
    assert not row.available and not row.selectable
    assert row.unavailable_reason == "Managed by the host outside Flatpak"
    assert actions == []


def test_navigation_skips_unavailable_rows() -> None:
    Gtk.init()
    first = ActionRow("First", lambda: None)
    unavailable = ActionRow("Host control", lambda: None).make_unavailable("Unavailable here")
    last = ActionRow("Last", lambda: None)
    rows = SettingsList(Scale(1080))
    rows.set_rows([first, unavailable, last])
    assert rows.selected_index == 0
    assert rows.move(1)
    assert rows.selected_index == 2
    rows.select(1)
    assert rows.selected_index == 2

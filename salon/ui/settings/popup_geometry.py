# SPDX-License-Identifier: GPL-3.0-or-later
"""Where a `ValuePopup` places its list and its scroll position.

Pure arithmetic, split out so `popup.py` stays about the widget and this
stays testable without a display.
"""

from __future__ import annotations


def anchored_offset(
    selected: int,
    count: int,
    row_height: int,
    gap: int,
    max_visible: int,
    nudge_x: int,
) -> tuple[int, int]:
    """Pixel ``(dx, dy)`` for ``Gtk.Popover.set_offset`` so the selected
    value sits centred on the setting row the list was opened from."""
    pitch = row_height + gap
    visible = min(count, max_visible) or 1
    first = max(0, min(selected - visible // 2, count - visible))
    selected_centre = (selected - first + 0.5) * pitch
    vertical = selected_centre + row_height * 0.54
    return nudge_x, -round(vertical)


def scroll_target(selected: int, pitch: float, page: float) -> float:
    """Adjustment value that centres the selected row within the page."""
    return selected * pitch + pitch / 2.0 - page / 2.0

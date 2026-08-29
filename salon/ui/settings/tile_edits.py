# SPDX-License-Identifier: GPL-3.0-or-later
"""One shape of edit, shared by every field in the tile editor.

Open the keyboard, take what comes back, write it, save, rebuild. Every
edit in the editor did those five things by hand, which is five chances to
forget the save.
"""

from __future__ import annotations

from collections.abc import Callable

from salon.ui.settings.context import SettingsContext


def edit_field(
    context: SettingsContext,
    prompt: str,
    current: str,
    apply: Callable[[str], None],
    *,
    allow_empty: bool = True,
) -> None:
    """`allow_empty=False` for a field a tile cannot do without.

    A title or a launch target cleared to nothing leaves a tile that draws
    a blank card and launches nothing, which is worse than the edit not
    having happened — so it does not happen. Everything else may be
    cleared, because "no subtitle" and "no artwork" are real answers.
    """

    def done(value: str | None) -> None:
        if value is None:
            return
        text = value.strip()
        if not text and not allow_empty:
            return
        apply(text)
        context.save_config()
        context.rebuild()

    context.edit_text(prompt, current, done)

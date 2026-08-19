<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contributing to Salon

Salon is GPL-3.0-or-later. By sending a patch you agree it can be
distributed under that licence.

## Before anything else

```sh
meson setup build
./scripts/check.sh
```

`check.sh` is the gate: ruff, `mypy --strict` over `salon/core` and
`salon/input`, pytest, `meson compile`, and the AppStream and desktop-entry
validators. It must exit 0. The same gates run in CI on every push, under
Xvfb so the tests that resolve real icon names against a theme run rather
than skip.

`./bin/salon` builds and then runs, so it can never launch stale code.

## The rules that aren't obvious from reading the tree

* **`salon/core/` must never import `gi`.** A test walks the AST and fails
  if it does. The core is the part that stays testable without a display,
  and it is only worth having if that holds.
* **`salon/core` and `salon/input` are under `mypy --strict`.** The rest of
  the tree isn't, because GTK's introspected types don't survive it.
* **Don't unit-test GTK widgets.** Test the pure layers underneath. Widget
  behaviour is verified by running the thing and looking at it.
* **Every size is a design unit**, resolved against the real monitor at
  runtime by `ui/scale.py`. `salon.css` contains no raw pixel values and a
  test enforces that. If you need a number, add a token in
  `core/tokens.py`.
* **One input vocabulary.** Every source — keyboard, gamepad, CEC, mouse —
  normalises to an `Action` from `salon/input/actions.py`. Nothing
  downstream should care which device a press came from.

## Layout changes need a screenshot, not an argument

Geometry bugs in this project have a track record of surviving careful
reasoning and dying instantly to a screen capture. If you change layout,
run the app and capture the window — `Gtk.WidgetPaintable` →
`Gsk.Renderer.render_texture` → `save_to_png` works in-process. Say in the
pull request that you looked at it.

## Commits

One change per commit, and a message that says why rather than what — the
diff already says what. `DECISIONS.md` gets a dated entry for any judgement
call that isn't obvious from the code; if you had to think about a
trade-off, that's where the thinking goes.

## Reporting bugs

Include the GNOME and GTK versions, whether you're on Wayland (Salon does
not support X11), and the log. Salon writes to the journal and to
`$XDG_STATE_HOME/salon/salon.log`; run it with `SALON_DEBUG=1` for the
verbose version. If Salon is running as the session, it restarts on crash
and the screen barely blinks — the log file is the only record.

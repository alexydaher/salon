<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Changelog

Notable changes per release. Dates are ISO. This project follows
[semantic versioning](https://semver.org/) from 0.1.0 onward, with the usual
0.x caveat that the interface is still allowed to move.

## 0.1.0 — 2026-08-19

First release. A fullscreen launcher for GNOME, meant to be read from a sofa
and driven with six buttons.

### The interface

* Rows of large tiles sized in design units resolved against the real
  monitor, so the layout reads the same on a 1080p set and a 4K one. Focus
  is a scale-up, an accent ring and a bloom cast onto neighbouring tiles.
* One input vocabulary. A gamepad, a keyboard, an HDMI-CEC remote and a
  mouse all normalise to the same `Action`, and every screen is reachable
  from a D-pad alone.
* A top bar that is a focus row rather than decoration: up from the first
  row of tiles reaches search, all applications, settings and power.
* Search across the tile catalogue and every installed application at once,
  with an on-screen keyboard — or type on a phone, over a code-paired
  server that runs only while search is open.
* An all-apps grid, A–Z, with per-tile options and pinned favourites.
* Settings and a full tile editor in the home screen's own visual language,
  both driveable from a controller, with a live preview strip for the
  choices that are easier to see than to name.
* Onboarding once, on first run, because nothing on screen otherwise
  explains that the MENU button exists.

### Launching

* Desktop entries, Flatpaks, plain commands, and web apps opened fullscreen
  in their own browser profile.
* A two-phase launch state machine that can tell a Flatpak wrapper exiting
  from an application actually closing, and a way back out: MENU closes the
  running application and returns to Salon.
* Gamepad-driven pointer control over the RemoteDesktop portal, for
  browser-hosted streaming services that expect a mouse. Asks for
  permission once, then restores the grant silently.

### Under it

* `salon/core/` is pure Python with no `gi` import anywhere, enforced by a
  test that walks the AST: the model, the focus machine, launch resolution,
  ranking, the provider runner and the on-screen keyboard are all testable
  without a display.
* Providers run concurrently against one shared deadline; a provider that
  hangs, raises or returns nonsense contributes nothing and is reported,
  rather than taking the catalogue with it.
* Runs as its own gnome-session, with `Restart=always`, or as an ordinary
  application in a normal desktop.
* Logs to the journal and to a rotated file under `$XDG_STATE_HOME`,
  including from threads and from GLib.

### Known limits at 0.1

CEC has never met an adapter, the power actions have never been invoked, and
the session has not yet been logged into. See
[the README](README.md#what-hasnt-been-tested) for the full and honest list.

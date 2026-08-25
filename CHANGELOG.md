<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Changelog

Notable changes per release. Dates are ISO. This project follows
[semantic versioning](https://semver.org/) from 0.1.0 onward, with the usual
0.x caveat that the interface is still allowed to move.

## Unreleased

## 0.2.10 — 2026-08-25

### Centred top-bar shortcuts

* The top bar's shortcut buttons are square at rest again, so each
  icon-only button renders as a circle, and every glyph is centred
  within it instead of sitting left of centre.
* The phone connection dot now sits on the phone glyph's corner
  rather than below it.

## 0.2.9 — 2026-08-25

### Reliable release validation

* The Flatpak release smoke test now follows Advanced input to verify its
  sandbox-only controls and initializes D-Bus correctly in minimal builders.

## 0.2.8 — 2026-08-25

### Host apps and a calmer Home screen

* Flatpak installations now discover the host's desktop applications, so the
  All Apps page is no longer limited to entries visible inside the sandbox.
* Home-screen shortcut buttons are compact when idle, without extra space
  beside each icon, and generated tiles show application logos directly
  without a second shape behind them.
* Moving between apps now recolours the ambient wallpaper from each app's
  accent while preserving the photo's light and texture; app logos are no
  longer enlarged or blurred into the background.

## 0.2.7 — 2026-08-25

### A more cohesive Home screen

* Salon now ships a restrained ambient background with subtle texture and
  edge lighting, while custom wallpapers and a flat-background opt-out remain
  available.
* Generated application tiles place icons in a shared translucent medallion,
  giving unrelated desktop, web and symbolic icons one visual language.
* Shortcut buttons are clearer and more cohesive, the focused row has an
  accent marker, and selected-tile context sits in a compact glass card.
* Background feedback begins sooner and settles more smoothly as focus moves
  between tiles.

## 0.2.6 — 2026-08-25

### Safer and easier to control

* Destructive system, Bluetooth and phone-remote actions now require an
  explicit confirmation, with the safe choice focused first.
* Physical keyboards can type, paste, erase and submit directly in Search and
  text editors; Search also opens from All Apps and exposes tile options.
* Onboarding and action hints use one consistent OK, BACK, MENU, OPTIONS,
  SEARCH and GROUP vocabulary.

### More predictable navigation

* Home, Search and All Apps share contextual tile actions, while persistent
  hints explain what the current buttons do and Search reports loading and
  result counts.
* Settings uses OK consistently for opening controls, reserves OPTIONS for
  live preview, separates advanced controls, and makes hidden scrolling clear.
* Rows and tiles can be reordered from dedicated controller-friendly flows.

### Better setup and context

* Pointer users get native file and folder pickers plus browser and input
  configuration tests.
* The selected tile remains described while media is playing, and unfocused
  row headings remain more legible on television panels.
* The phone remote uses the same Add to Home action and confirms before the
  sole active remote is stopped.

## 0.2.5 — 2026-08-25

### Fixed

* Appearance settings now scroll far enough to show every item when rows
  render taller than their nominal height.

## 0.2.4 — 2026-08-25

### Improved

* Fresh installs now start with a short, detected set of TV-friendly apps
  alongside editable Netflix, Prime Video, Disney+, YouTube and GeForce NOW
  tiles. Untouched older starter catalogues are upgraded without changing
  catalogues their owners have edited.

## 0.2.3 — 2026-08-25

### Packaging

* Tagged releases now publish a native Debian package alongside both Flatpak
  architectures.
* A dedicated OpenPGP key signs a self-hosted Flatpak repository on GitHub
  Pages, providing a one-click `.flatpakref` and automatic updates without
  relying on Flathub.

## 0.2.2 — 2026-08-25

### Hardened

* Salon no longer changes the global GNOME screen-lock setting.
* Catalogue parsing now validates and normalizes every known value and reports
  all malformed inputs as location-aware configuration errors.
* Browser launching and the sole `wpctl` audio backend execute explicitly on
  the host when sandboxed and report unavailable/error states to the UI.
* Phone requests, remote downloads, decoded images, and generated cache growth
  now have strict resource limits; portal failures are contained and reset.
* Flatpak Settings rows honestly disable unsupported host integrations.
* Native dependency minimums, Wayland/Flatpak smoke harnesses, crash recovery,
  reproducible screenshots, and explicit component composition are enforced.

## 0.2.1 — 2026-08-25

### Improved

* Settings now use controller-first navigation: RIGHT enters a section or
  control, B alone goes back, and LB/RB move between top-level sections.
* The status bar shows when a controller or phone is connected and exposes
  that state to assistive technology.
* The Flatpak now grants input-device access instead of every host device,
  and disables host power and GNOME host-setting controls rather than
  requesting direct logind and dconf permissions.
* The Flathub listing has brand colours, a shorter user-facing summary and
  an explicit explanation of the Flatpak's login-session limitations.
* Pushes now verify release-version consistency; a matching version tag builds
  both Flatpak architectures and publishes a GitHub release with a
  commit-pinned Flathub manifest.

## 0.2.0 — 2026-08-25

### The phone is a second screen

* **Scan and you're connected.** MENU → Connect a phone shows a QR code
  carrying a 128-bit session token in the URL fragment, so there is nothing
  to type and the secret reaches no server log. The four-digit code remains
  for anyone typing the address by hand, and is now accepted at `/connect`
  and nowhere else.
* **The phone can see the television.** A 1 Hz state poll carries the rows
  and their artwork, where the cursor is, which screen is in front, and
  what is playing. Tapping a tile opens it through the same launch path as
  a press on the television.
* **A remote worth holding.** Four panes — the catalogue, a D-pad with
  press-and-hold repeat at the cadence set in Settings, a trackpad, and a
  keyboard — plus transport controls for the current player. Haptics, a
  screen wake lock, and a web manifest so it installs to the home screen.
* **Refuses requests from outside the local network**, and says so when the
  trackpad has no pointer grant instead of accepting gestures into nothing.

### Fixed

* **The phone keyboard reaches other applications.** Typing with no Salon
  field on screen now goes to whatever the compositor has focused — the
  search box inside a launched browser, which is the one text field on a
  television that Salon cannot draw. Backspace and Enter came with it.
* **The trackpad's cursor is visible.** The pointer was moving all along;
  Salon just never revealed its own cursor for it, so it dragged something
  invisible and hover-to-focus stayed off.
* **The remote stays connected.** The session token is remembered on the
  phone, so a discarded tab or a pull-to-refresh no longer drops you to the
  code screen; and a remote you switched on no longer switches itself off
  after five idle minutes while your phone's screen is dark.
* **Losing the connection says which kind.** A banner distinguishing "the
  television isn't answering" from "this session ended", a Retry button,
  and a poll that backs off instead of retrying every second forever.
* The QR code rendered at a half-pixel origin, which antialiased every
  module edge and made it unreadable to a strict decoder.
* Turning the phone remote on now takes the RemoteDesktop pointer session,
  so the trackpad works on a catalogue with no browser tile in it.

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

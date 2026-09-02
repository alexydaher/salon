<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Changelog

Notable changes per release. Dates are ISO. This project follows
[semantic versioning](https://semver.org/) from 0.1.0 onward, with the usual
0.x caveat that the interface is still allowed to move.

## Unreleased

### Changed

- The release workflow runs the quality gates on every push to `main` again,
  not only on a `v*` tag. They had moved into the tag-triggered workflow at
  0.3.2 and lost the branch trigger on the way, so between 0.3.2 and 0.4.0
  the tag was the first thing CI saw. Cutting a release now means pushing
  `main`, waiting for green, and tagging after.
- Flatpak bundles are built from a manifest pinned to the exact commit that
  triggered the run, instead of re-resolving the release tag at clone time.
- The signed Flatpak repository is deployed to GitHub Pages *after* the
  GitHub release is published rather than before, so a failure late in a
  release cannot deliver an update to installed copies with no release
  behind it.
- Release tags are protected against being moved or deleted.
- Every third-party GitHub Action is pinned to a commit hash, with Dependabot
  opening the updates as pull requests, and every job has a timeout.
- This changelog is tracked in the repository. It was ignored, which quietly
  turned the changelog release gate into a no-op in every CI run, since the
  check only ran when the file existed and a clean checkout never had it.
  `--require-changelog` now makes its absence a failure rather than a skip.

### Fixed

- `docs/publishing.md` claimed the ARM64 Flatpak bundle was smoke-tested. It
  is built and never run; only the AMD64 bundle is installed and started.

## 0.4.0 — 2026-09-02

### Added

- Controller-native button prompts that name the pad in hand.
- The phone remote's Type drawer is a full sheet that streams each keystroke
  to the television, seeds itself from the field already on screen, and has a
  "Clear field" button.

### Changed

- The Aurora Console redesign reworks the home shell, overlays, tile focus,
  backgrounds, and settings preview controls into one visual language and
  trims repetitive UI copy.
- The standing phone-pairing QR code is larger.
- Launched apps keep running, with every now-playing source addressable in a
  fixed order.
- Home and All Apps navigation refined.
- The now-playing card shows per-source cover art, an artist line, and a
  play-state marker.

### Fixed

- Custom wallpaper detail and colours are preserved.
- The settings sidebar stays visible in nested panels.

## 0.3.8 — 2026-08-30

### Fixed

- The phone remote now takes its height from the browser's live dynamic
  viewport and uses JavaScript only for the bounded visual-viewport origin,
  avoiding stale geometry when mobile browser chrome settles without a final
  resize event.
- Remote shell pages, stylesheets, and modules are no longer cached across
  Salon upgrades, so a first QR navigation cannot resurrect older viewport
  behavior until the phone is manually refreshed.

## 0.3.7 — 2026-08-29

### Fixed

- The phone remote now remeasures the visible viewport through the browser's
  short startup and connection settling window, covering late mobile toolbar,
  manifest-mode, and safe-area changes that do not emit a final resize event.

## 0.3.6 — 2026-08-29

### Fixed

- The phone remote now stays inside the browser's unobscured visual viewport
  when mobile toolbars expand or collapse, without losing controls above the
  scroll origin or exposing empty document space below the tab bar.

## 0.3.5 — 2026-08-29

### Fixed

- The installed phone remote now uses true fullscreen mode instead of opening
  with standalone app chrome around it.
- The remote no longer locks itself to portrait, so its compact landscape
  layout is reachable when the phone rotates.

## 0.3.4 — 2026-08-29

### Added

- Settings now exposes a guided television setup, per-section summaries,
  modified indicators, per-setting and per-section restore actions, audio test
  playback, tile backup and restore, artwork picking, accent swatches, and a
  real tile preview.
- The phone remote can tune previewable picture settings while the television
  shows their effect live.

### Changed

- Settings is reorganized into eight focused sections. Values are drawn with
  controls such as switches, swatches, and meters instead of being presented
  as names alone, and empty or disabled values are visually muted.
- Audio outputs and controller bindings use concise human-readable names.
  Tile position is one ordered choice, and About presents version, licence,
  and a pairing QR code instead of internal filesystem paths.
- Settings lists preserve cursor identity across asynchronous rebuilds, share
  consistent edge fades, and keep previews and trailing details aligned.

## 0.3.3 — 2026-08-29

### Changed

- Opening a previewable Appearance value list now collapses Settings to its
  bottom strip and shows the real home screen behind the choices. Moving
  through the list applies each candidate live, OK keeps it, and Back restores
  the value that was active when the list opened.
- Pointer clicks and controller presses now enter the same live-preview flow,
  while the home screen's own bottom bar fades out so it does not compete with
  the preview controls.

## 0.3.2 — 2026-08-29

### Changed

- Release quality gates and publication now live in one tag-triggered GitHub
  Actions workflow. A combined `main` and release-tag push starts one run,
  with every gate visible before its packaging and publishing jobs.
- Pull requests use that workflow's same quality-gate job but do not enter
  the tag-only release jobs.

## 0.3.1 — 2026-08-29

### Changed

- The existing tile-size preference now controls the All Applications grid
  as well as Home. Changing it recomputes the grid's column count immediately,
  so smaller tiles fit more applications rather than leaving empty space.

### Fixed

- Flatpak host applications whose desktop entries or icon files are hidden by
  the sandbox now fall back to generated artwork. PyGObject reports a missing
  desktop entry as a `TypeError` rather than the nullable result promised by
  Gio; that exception used to interrupt Home layout before its rows were
  positioned, stacking every heading and tile at the same coordinates.

## 0.3.0 — 2026-08-29

### Added

- A tile is a proportional object. The tile-size preference now scales the
  title and subtitle, the inner padding, the focus bloom and the row heading
  along with the card, instead of shrinking the box around type that stayed
  where it was. The shipped default comes down with it, because the design
  size fits only two rows in the band, and the range extends below the old
  0.75 floor,
  which existed only because the bloom stopped fitting inside the tile's
  bleed.
- Game controllers have a play/pause: `BTN_SELECT` — Create on a DualSense,
  View on an Xbox pad, Minus on a Switch Pro. Not L3/R3, which are clicked by
  accident while the navigation stick is being pushed. The old rule that
  play/pause launches the focused tile when nothing is playing now applies to
  HDMI-CEC alone, where the largest button on the remote is play.
- Now playing has moved to the centre of the top bar, draws the player's own
  cover art, and takes a click to pause. It stays a status rather than a
  button, so a screen reader still announces track changes.
- The phone remote browses the full installed-application catalogue with an
  A-Z index rail, and its pointer pane reports what each gesture just did.
- The Flatpak build regains power actions, Wi-Fi status and joining,
  Bluetooth pairing, the battery indicator, HDMI-CEC, GNOME Settings
  delegation and the shell on-screen keyboard. Each was withheld on the
  reasoning that a sandboxed app should not hold host-wide access, which
  did not survive the host-spawn grant a launcher already needs: it can
  reach all of them by other means. The four narrow system-bus names are
  declared in the manifest instead, where `flatpak info --show-permissions`
  can show them.
- Host application icons and tile artwork given as an explicit path now
  resolve inside the Flatpak, which previously drew a generated gradient
  card for every installed application.

### Changed

- The cursor carries one column across the whole grid instead of each row
  remembering its own. Moving down lands on the tile already under the
  cursor, and the rows on screen line up rather than reading as independent
  strips that happen to be stacked.
- The focus ring is drawn in the focused tile's own dominant colour. The
  backdrop pool and the bloom already followed the artwork, so the sharpest
  part of the halo was the one part that disagreed with the rest of it.
- The phone remote is rebuilt around a persistent header and three panes.
  The controls whose meaning never changes — the connection, closing a
  launched application, the player and volume — move into the header, and
  the two that only sometimes apply appear only when they do. Volume is a
  popover hung off a measured header height; typing is a drawer inside
  Pointer, where the aim-then-tap-then-type sequence already lives, so the
  tab strip is Browse, Remote and Pointer.
- Scrolling no longer renders full-screen offscreen images every frame. The
  row and band edge fades mask only their own ramps rather than the whole
  widget, and the backdrop renders into a quarter-size cached texture keyed
  on everything it is a function of.
- The 60Hz right-stick poll is armed when a controller connects and retires
  itself when the last one disconnects. With no controller attached it had
  been waking the main loop sixty-two times a second to read an empty
  dictionary, for 1.03% of a core against 0.117% gated.
- `salon/services/onscreen_keyboard.py` splits out of `pointer_shared.py`;
  the three public names are re-exported, so import sites are unchanged.
- The README is an install guide rather than a manual: what Salon is, the
  four ways to install it, the kiosk session, updating and removing. The
  agent orientation, the design journal, the maintainer release procedure
  and the house rules stay on disk and out of the published repository.

### Fixed

- A phone remote lockout could strand a household without a remote. A stale
  token spent one of the five allowed attempts, so five reloads of a phone
  paired before a restart burned the session; a token that does not match is
  answered 401 now and never reaches the code comparison. The lockout expires
  after five minutes and mints a new code on the way out, rather than lasting
  for the life of a server whose only route to a remote it was hiding. And a
  server that could not bind no longer leaves its credentials minted and its
  holder recorded, which used to draw a pairing QR for a port the process
  does not hold.
- A tile whose `icon_name` is not in the icon theme now asks the desktop
  entry it launches what its icon is called before falling back to a
  generated card. An application id is not an icon name: the seeded Chrome
  tile says `com.google.Chrome` while the package installs `google-chrome`.
- An accented application name is filed under its own letter. `casefold()`
  alone sorts every accented title after "Z", so "Éditeur de texte" came
  after "Zoom" and landed under a second "#" heading sharing an id with the
  first.
- Card grids on the phone use `minmax(0, 1fr)`. A bare `1fr` is
  `minmax(auto, 1fr)`, whose floor is the item's min-content width, and an
  installed application's subtitle is a whole `Comment=` sentence — which
  drew tracks of 312px, 89px and zero across one phone.
- HDMI-CEC and the shell keyboard probed the sandbox's own PATH and dconf
  rather than the host's, so both reported themselves unavailable on
  machines that supported them.
- No test harness can write the user's GSettings. A temporary
  `XDG_CONFIG_HOME` does not isolate a dconf write, because the write is a
  D-Bus call to a daemon that resolves the user database from its own
  environment — so the value landed in the live session while the read came
  back out of the empty temporary copy. A screenshot run had left
  `remote-hint=false` behind in a real dconf, silently disabling the corner
  pairing card, which is the one thing Salon shows when there is no
  controller and no phone.

## 0.2.11 — 2026-08-26

### Clearer controls throughout Salon

* Home now shows button names for the keyboard, remote, phone, or controller
  actually in use, keeps each row's own remembered position, centres short
  catalogues, fades overflowing row edges, and gives selected-tile context and
  now-playing state distinct, quieter treatments.
* The system menu is shorter and moves session-ending actions into a nested
  Power page, while MENU and POWER remain reachable consistently from other
  screens and launched applications.

### A more capable phone remote

* The phone can browse the full installed-app catalogue, see local or streamed
  cover art, mirror and edit Salon text fields, and reach Menu, Power, and the
  way back from an application from every pane.
* D-pad swipes, accelerated trackpad movement, adaptive accent contrast, and
  responsive landscape and tablet layouts make the remote easier to use
  without looking away from the television.
* The remote page is split into small, directly served modules with no build
  step, backed by strict resource routing and tests that reject missing,
  unbundled, orphaned, or oversized assets.

### Reliability and accessibility

* Menu roles, input vocabulary, phone endpoints, installed-module coverage,
  scale handling, text controls, and real-window navigation have broader
  automated coverage.

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

# Salon

A fullscreen, remote- and controller-driven launcher for GNOME. Full brief
and milestone plan live in the human's original spec (not checked into this
repo); this file is the fast-orientation summary for future sessions.

## Build & run

```sh
meson setup build          # first time only
./bin/salon                # builds ./build, then runs it
```

`bin/salon` runs ninja itself and refuses to start on a failed build, so it
can never run stale code. `SALON_NO_AUTOBUILD=1` skips that.

To get it into GNOME's Show Applications, use the **dev entry** — it points
`Exec=` at `bin/salon`, so the shell icon is always the current source:

```sh
./scripts/install-dev.sh          # ./scripts/install-dev.sh --undo to remove
```

`meson install -C build` (with `--prefix="$HOME/.local"`, which this build
dir is already configured for) is the real deployment path, but it copies
the tree into `$prefix` — that install is a *snapshot* and goes stale the
moment anything is edited. The two desktop entries share a file id, so
whichever was written last wins; re-run `install-dev.sh` after a
`meson install` to get the development one back.

## Gates

```sh
./scripts/check.sh         # ruff, mypy --strict (core+input), pytest,
                           # meson compile, meson test (metadata validation)
```

Must exit 0 before any milestone is considered done. The same gates run in
CI (`.github/workflows/checks.yml`) on every push, under Xvfb so the tests
that resolve real icon names run rather than skip, finishing with a staged
`DESTDIR` install.

## Layer rules

- `salon/core/` — **no `gi` imports, ever.** Enforced by
  `tests/test_no_gi_import_in_core.py` (walks the AST). Must stay importable
  and testable headlessly.
- `salon/input/` — also gi-light: `actions.py` (Action, Repeater) is pure
  and covered by `mypy --strict`; `keyboard.py`/`gamepad.py` use gi to talk
  to GDK/libmanette and normalize everything to `Action`.
- `salon/core` and `salon/input` are the only packages under `mypy --strict`.
- `salon/ui/`, `salon/services/`, `salon/providers/` use gi freely.
- Never unit-test GTK widgets directly; test the pure layers instead.

## Verifying visually

There is a real display available in this environment, so **do not guess at
layout**. The pattern that works: run the app on the live Wayland session,
drive it with synthetic `Action`s or by poking `HomeView` directly, and
capture the window with
`Gtk.WidgetPaintable` → `Gsk.Renderer.render_texture` → `save_to_png`. The
GNOME Shell screenshot D-Bus method is *not* permitted to this process, so
in-process capture is the only route. Every layout claim below was checked
against such a capture; the geometry bugs that survived three sessions of
careful reasoning were all obvious in the first screenshot. Sampling raw
pixels out of the capture is worth reaching for too — the clipped-bloom bug
was a hard 28→72 step in one scanline, which is far more decisive than
looking at it.

**Icon trap:** an SVG whose `<svg>` element is pushed past the first ~256
bytes (by a long leading XML comment, say) is rejected outright by
gdk-pixbuf's format sniffing, so it renders nowhere in the shell — while
`Gtk.IconPaintable` still displays it happily, which is how it passes a
visual check. Keep comments inside the element; `tests/test_icons.py`
enforces it.

**GTK4 trap, hit twice:** `do_size_allocate` on a `Gtk.Fixed` (or `Gtk.Box`)
subclass **never runs** — GTK dispatches allocation to the layout manager
instead of the class vfunc, and those containers install one. Swapping the
layout manager breaks `put`/`move`/`set_child_transform`, which go through
the pointer `GtkFixed` cached in its own init. Use `motion.SizeReporter`,
which wraps the container in a plain `Gtk.Widget` (no layout manager, so its
vfunc is what GTK actually calls).

**Third trap, same family:** a `Gtk.Fixed` used as a *scroll viewport*
measures to fit its children, so a viewport around content taller than the
screen asks to be that tall — and an overlay child gets it. The clip then
happens at the window edge instead of the viewport's, the reported height is
the content's height, and every "is the focused row off-screen?" test
answers no, so the list stops scrolling. Wrap it in
`motion.SizeReporter(..., propagate_minimum=False)`, which reports a zero
minimum and hands the decision to the parent. The all-apps grid, the search
results and both settings lists all needed it.

## Input vocabulary

`Action` (salon/input/actions.py) is the only currency; every source
normalises to it.

| Action | Gamepad | Keyboard | CEC |
|---|---|---|---|
| OK / BACK | A / B | Return / Backspace | 0x00 / 0x0D |
| MENU | START | Menu | 0x09 |
| OPTIONS | X | F10 or `o` | 0x0B, 0x71 |
| SEARCH | Y | `/` | — |

**MENU is the one button that always means the same thing.** On the home
screen it is the system menu; inside Settings it closes Settings; while a
launched app is in front of Salon it closes that app and comes back (see
`_return_from_child`). It is checked first in `_handle_action`, ahead of
every mode, so a stuck launch can never swallow it.

**OPTIONS is per-item, and exists because long-press OK can't work here.**
Long-press means firing OK on release, and a CEC remote produces presses
with no release — the TV remote would stop launching anything.

## Current state (as of 2026-08-22)

The project jumped from M0 straight to a working POC — real launching,
gamepad input, and gamepad-driven mouse control over browser-hosted DRM
tiles via the RemoteDesktop portal — and the real architecture has been
backfilled under it since. **M0–M11 are all complete and visually
verified.** What remains is hardware that isn't attached to this machine
(a controller, a CEC adapter, a television) and the short gap list below.

- **M0 — done.** Meson, GResource, GSettings, gates, and (as of this
  session) `ui/scale.py`: the du→px runtime pipeline from §7.2, which had
  been an accepted gap. `core/tokens.py` holds every size in design units;
  `ui/scale.py` resolves them against `Gdk.Monitor` geometry, emits them as
  CSS custom properties on `:root`, and recomputes on monitor change.
  GTK 4.16+ supports `var()`, so `salon.css` contains no raw px at all and
  `tests/test_css_has_no_raw_px.py` enforces that. Widget geometry that CSS
  can't express comes from `Scale.du()` in Python. Note the generator is
  `build-aux/gen-tokens-css.py`, not the plan's `tools/gen_css.py`.
- **M1 (core, headless) — done.** `model.py`, `config.py`, `catalog.py`,
  `launchspec.py`, all `mypy --strict` clean. `ui/home.py` loads
  `~/.config/salon/tiles.json` (seeding it on first run only) and hot-
  reloads via `Gio.FileMonitor`, preserving focus by tile id.
  `tests/test_launchspec.py` covers every `LaunchKind` including the full
  Chrome flag set and the conditional ozone flag — it did not exist before
  this session, which is how a hardcoded `--ozone-platform=wayland`
  survived in a milestone marked done.
- **M2 (focus model, headless) — done.** `core/focus.py` (pure; no
  wraparound, rubber-band at every edge, tile-removal recovery,
  `column_for(row)` so the UI can position every row and not just the
  focused one). Vertical movement **carries the column** rather than
  remembering one per row, so every row rests at the same column and moving
  down lands on the tile that was already under the cursor and `input/actions.py`'s accelerating `Repeater`. The
  `Bump` the model returns is now actually rendered as a 90ms
  overshoot-and-settle; it was being discarded until this session.
  `core/ranking.py` is built, tested and now wired into the search UI.
- **M3 (tile widget) — done, both stages, verified on screen.**
  `ui/tile.py` draws the whole tile in `do_snapshot`, because the scale
  transform, the bloom's `push_blur` and the generated artwork gradients
  are all unreachable from GTK4 CSS. Focus drives a single 0..1 spring from
  which scale, bloom intensity, ring opacity and the brightness lift are
  all derived. §7.4 artwork resolution is complete: explicit path, drop
  folder, `https://` URL fetched async through libsoup3 into
  `$XDG_CACHE_HOME/salon/art/`, app icon composited on a gradient built
  from its own dominant colour, and a hashed gradient with the title's
  initial. `services/artwork.py` owns resolution, caching by (path, mtime)
  and dominant-colour extraction.
- **M4 (home screen) — done, verified on screen.** Rows are positioned at
  absolute y (not stacked in a box — tile bleed makes consecutive rows
  overlap), row viewports span the full window width so the only horizontal
  clip is the screen edge, and both axes clamp their scroll to the content
  bounds. `ui/backdrop.py` is a bounded pool of accent light behind the
  focused tile rather than a full-screen wash. Row content fades at the top
  and bottom edges through a `push_mask` alpha gradient. `ui/statusbar.py`
  carries the clock, the date and (§6.9) the network and battery glyphs —
  `services/netinfo.py` over NetworkManager and `services/battery.py` over
  UPower, both live, both **honestly absent** when there is nothing true to
  draw. `core/status.py` holds the pure reading→icon table and
  `tests/test_status.py` checks every bucket *and* that each name resolves
  in the icon theme.
- **M5 (launching) — done.** `services/launcher.py` is a two-phase state
  machine: phase 1 shows `LaunchingOverlay` with a 12s timeout, phase 2
  waits for return via debounced `notify::is-active` *or* subprocess exit.
  A subprocess exit within 2.5s of launch while still awaiting child focus
  is ignored, because that's a Flatpak/systemd-scope wrapper, not a return
  (§11). `DESKTOP` tiles launch through `Gio.DesktopAppInfo` per §6.3, not
  by exec'ing a parsed `Exec=` line. Bounded idle inhibit is released on
  return as well as on its timer. Recents, `services/audio.py` and the
  volume OSD are wired.
- **M7 (search, OSK, phone pairing) — done, verified on screen.**
  `ui/search.py` is a two-pane full-screen overlay: the keyboard on the
  left, results on the right, crossing between them at the panes' edges.
  It searches the tile catalogue and every installed application at once,
  ranked catalogue-first via `core/ranking.py`, filtered live per keystroke;
  results are ordinary `TileWidget`s so they get the same artwork, focus
  treatment and launch path as home-screen tiles. `core/osk.py` holds the
  keyboard layout and cursor (pure, tested — including that vertical
  movement is *spatial*, not by index); `ui/osk.py` renders it as real
  buttons so a mouse works too. `services/appinfo.py` scans desktop entries
  on a worker thread. `services/pairing.py` began as the §6.12 phone
  keyboard and is now the whole second screen — see below.
- **The phone is a second screen, not just a keyboard (2026-08-22).**
  `services/pairing.py` serves `data/remote/index.html` (in the GResource
  bundle, *not* a Python string any more) — four panes: the catalogue with
  real artwork, a D-pad, a trackpad, a keyboard, plus a now-playing card.
  Read DECISIONS.md 2026-08-22 before changing any of it. The shape:
  - **Two credentials.** A 128-bit token is the session credential and is
    what the QR carries, **in the URL fragment** (`#k=…`) so it never
    reaches a server log. The four-digit code is a bootstrap credential
    accepted at `/connect` *only*, and that one endpoint owns the lockout.
    Wrong *tokens* are deliberately not counted — counting them would be a
    denial-of-service on the paired phone.
  - **`core/remote.py` is the boundary.** Pure, `mypy --strict`,
    `tests/test_remote.py`. `RemoteState` is the snapshot; `StateFeed`
    holds it with a version that only moves on a real change and serialises
    lazily; `is_local_address` refuses off-LAN sources. Nothing about the
    phone lives in `home.py` except filling the snapshot in.
  - **`GET /state` is a 1 Hz poll**, 204 when the phone is current. It runs
    on the main loop, so keep it that cheap. `_handle_action` wraps
    `_dispatch_action` purely so the snapshot is republished after every
    press, whichever of the two dozen early returns fired.
  - **`/launch` and `/art` check ids against the published state**, never
    the catalogue and never the filesystem. That is also why traversal is
    structurally impossible.
  - **The top bar's phone button** (and MENU → Connect a phone) opens
    `ui/phonepairing.py`; the screen closes itself ~1.6s after a phone
    authenticates, and closing it leaves the remote running. `core/qr.py`
    is wired here via `ui/qrcode.py`. `KeyboardPane` no longer starts
    anything — it claims the text sink on map, and gives it back through
    `release_text_sink` (which only clears the slot if it still holds it,
    because GTK maps the incoming screen before unmapping the outgoing).
  - **QR trap:** flooring the module size is not enough — the *origin* must
    be whole-pixel too, or every module edge antialiases and libzbar
    refuses the symbol outright. It looked perfect and read as nothing.
  - **Page trap:** `header`/`nav` are `display: flex`, which beats the user
    agent's `[hidden] { display: none }`. The page carries an explicit
    `[hidden] { display: none !important }`.
  - **Typing goes to Salon first, the session second.** `/type` prefers the
    `_text_sink`; with none, `PointerInjector.type_text` taps keysyms
    through the *same* RemoteDesktop grant the trackpad uses, so a search
    box inside a launched browser is reachable. Character→keysym
    **delegates to `Gdk.unicode_to_keyval`** — `0x01000000 + codepoint` is
    wrong for characters with legacy named keysyms (`tests/test_keysyms.py`
    keeps the evidence).
  - **A capability test is not a working-feature test.** `_pointer.ready`
    was True and the pointer really moved while the whole feature looked
    dead, because the cursor was hidden. Anything that injects input needs
    `_set_pointer_visible(True)` alongside it.
  - **A press on the phone hides the mouse** (`_on_phone_action`,
    `_on_phone_launch`), like every other input source — the same flag gates
    hover-to-focus, so a parked mouse used to yank the selection back from
    under the phone. The trackpad reveals it again.
  - **`PointerInjector.ready` means `Start` succeeded, not "there is a
    session handle".** The portal returns the handle at CreateSession, well
    before the grant exists; taking that as ready made `/type` and
    `/pointer` answer 200 into a session mutter had never started. See
    DECISIONS 2026-08-23.
  - **The Type tab does reach a launched app** — measured against both a GTK
    child and a Chrome URL tile. What it cannot do is focus a text field:
    the keys go wherever that app's cursor is, and a freshly opened app has
    none, so you tap the search box with the Pad first.
  - **The phone holds its own screen on by playing a video, not with
    `navigator.wakeLock`.** That API is gated on a secure context and the
    remote is HTTP on a LAN address, so on a phone it is *absent* — the
    `"wakeLock" in navigator` guard made the feature dead code. `#awake` in
    the page plays `data/remote/awake.{webm,mp4}` from the bundle. Same
    constraint rules out a service worker, so Android will never offer to
    install the page; iOS Add to Home Screen works and always did. This is
    why the remote is not becoming a PWA or a native app — DECISIONS
    2026-08-23 (later) has the measurements and the version-skew argument.
  - **A held session never idles out.** `stop()` clears `_holders`, so
    letting the idle timer fire on a remote the user switched on turned it
    off mid-film. Only unheld sessions expire.
  - **Menu on the phone closes a launched app**, same `_return_from_child`
    path as START on a controller, and for the same structural reason: the
    press arrives over HTTP into Salon's own process, so it does not need
    keyboard focus. Verified against a real child. The launcher's four
    lifecycle callbacks must all `_publish_remote_state()` — they arrive
    asynchronously, and without that the phone's header is one event behind
    and reads exactly inverted.
- **Mouse is a first-class input.** Tiles take clicks and hover-to-focus,
  the scroll wheel navigates, the power menu's selection follows the
  pointer, and the cursor hides until the mouse actually moves. Hover is
  gated on real pointer movement, because GTK sends a motion event whenever
  a widget maps or scrolls under a stationary cursor.
- **M8 (Settings and the tile editor) — done, verified on screen.**
  `ui/settings/` is a two-pane screen in the home screen's own visual
  language, not `Adw.PreferencesPage`: sections on the left, the current
  panel on the right, panels forming a stack so BACK unwinds one level at a
  time. `widgets.py` is the row kit (action/info/toggle/choice/range/text);
  `tiles.py` is the full editor
  (add/rename/reorder/delete rows and tiles, set kind, target, accent,
  artwork, fullscreen, spatial nav, move a tile between rows) driven end to
  end from a controller through `ui/textentry.py`; `panels.py` covers
  appearance, input, browser, audio, system and about. Every scalar lands in
  GSettings and is applied live — tile size, row density, safe area, accent,
  key-repeat timings, volume step and audio sink all take effect without a
  restart. `ui/theme.py` owns the one colour token that can change at
  runtime. System configuration delegates to gnome-control-center (§1).
  Verified end to end on the live session: Add row → on-screen keyboard →
  Done wrote `tiles.json` and the editor followed into the new row's panel.
- **Settings' horizontal axis: RIGHT goes in, LEFT comes back out.** A row
  with values (choice, range) has to be *engaged* before it can be changed —
  RIGHT steps into it, it fills with accent and takes the whole horizontal
  axis, OK or BACK releases it. LEFT is never a value change at any depth:
  it pops one panel, then returns to the sections, then closes Settings.
  Toggles, text rows and rows that open a sub-panel have no inside to step
  into, so RIGHT does the thing directly; plain action rows ("Shut Down",
  "Delete row") refuse RIGHT with a 220ms flash rather than firing on a
  direction key. The legend at the bottom is per-row and says which of these
  the selected row is. See DECISIONS.md 2026-08-19.
- **Power menu.** `services/power.py` wraps logind (system bus, never
  `systemctl`); `ui/overlays.py`'s `SystemMenu` is bound to `Action.MENU`
  and checked *before* every other mode in `_handle_action`, including
  `pointer_mode`/`child_active`, so it survives a stuck launch. The status
  bar carries visible Settings and power buttons, because MENU is invisible
  to a mouse. The power actions have been invoked against the real machine
  and work; the polkit *refusal* path has never been reached.
- **Gamepad pointer control is on by default and prompts once, ever.**
  `services/pointer_injector.py` asks the RemoteDesktop portal for
  `persist_mode=2` and keeps the returned `restore_token` in
  `remote-desktop-restore-token`; passing it back to `SelectDevices` makes
  the portal restore the grant with no dialog. Re-verified live this
  session (it hadn't been since the revert in `5bdd8fc`): first run shows
  one dialog, every later run starts the session silently. The session is
  taken at startup, not mid-launch, so that one dialog lands over Salon's
  own screen instead of over Netflix — and it's skipped entirely when the
  catalogue has no browser tile. Settings → Input → "Forget remote-control
  permission" clears the token. Requires portal RemoteDesktop version ≥ 2;
  on older portals the options are ignored and the dialog returns per
  launch, which is the old behaviour rather than a failure.

- **M9 (providers) — done.** `core/provider.py` is the pure, gi-free
  contract and runner: providers run concurrently on their own threads
  against **one shared 3s deadline**, and a raise, a timeout or a malformed
  return are all treated the same — that provider contributes nothing, a
  `ProviderOutcome` records why, and the rest of the catalogue builds. Three
  built-ins (`recents` 10, `static` 20, `apps` 90, off by default);
  third-party ones are `.py` files in `$XDG_DATA_HOME/salon/providers/`
  exposing `provider()`. Import failures are guarded separately in
  `external.py`, because they happen *before* `collect()` can protect
  anything. Settings → Providers lists every provider with what it
  contributed or why it didn't. `catalog.sanitize()` is the lenient front
  door: `Catalog` still raises on duplicate ids, but provider output is
  sanitised first so one bad tile id costs a row rather than the screen.
  The build is **asynchronous** — see DECISIONS for the 6004 ms → 86 ms
  measurement.
- **M10 (packaging and first run) — done.** Installed launcher
  (`bin/salon.in` → `$bindir/salon`; there was none before, despite the
  desktop entry saying `Exec=salon`), app icon and symbolic icon,
  `io.github.alexydaher.Salon.yaml` Flatpak manifest, `core/sandbox.py` +
  `host_prefix` so every launch kind escapes the sandbox via
  `flatpak-spawn --host`, a gnome-session definition and `wayland-sessions`
  entry, the autostart toggle, HDMI-CEC in both directions, and
  `ui/onboarding.py`. Verified by staging a `DESTDIR` install and running
  *that* copy.
- **M11 (polish) — done.** Error-copy pass (no Python reprs, no bare
  exceptions, every launch failure names its tile), README with the honest
  DRM section, screenshots in `docs/screenshots/`.
- **Reachability pass (this session) — done, verified on screen.** The
  changes below all came from one complaint: things existed but could not be
  got to. See DECISIONS.md for the reasoning on each.
  - `ui/statusbar.py` is a **focus row**, not two dim icons: UP from the
    first tile row moves into Search / All apps / Settings / Power, DOWN
    comes back, and the tile ring drops while the bar holds the cursor.
  - `ui/appsgrid.py` is the **all-apps grid** — every installed application
    A–Z, columns computed from the real viewport width. Reached from the top
    bar. The `show-apps-row` provider setting still exists and is unchanged.
  - `providers/favourites.py` is a **pinned row above Recents**, backed by
    `favourite-tile-ids`. Pinning an app from the grid does *not* write to
    `tiles.json`; the provider resolves `app:` ids against the installed-app
    scan, and only pays for that scan when there's one to resolve.
  - `Action.OPTIONS` opens a **per-tile menu** (`SystemMenu` with different
    items) from the home screen and from the grid.
  - `LauncherService.close_child()` + `HomeView._return_from_child()` are
    **the way out of a fullscreen app**: MENU sends SIGTERM to the child,
    then SIGKILL after four seconds, and the compositor hands focus back.
    Verified headlessly against a real child process.
  - Settings gained a **live preview strip** (OK on accent / safe area /
    tile size / row density collapses the screen to a bottom bar over the
    real home screen), a **button legend**, LEFT-from-sections as a second
    way out, a **Network** section reading NetworkManager over D-Bus
    (`services/netinfo.py`), section icons, and the system rows a television
    actually needs (display, date & time, region, accessibility, power,
    updates) — all delegating to gnome-control-center per §1.
  - Three layout/model bugs fixed: an empty row no longer traps focus
    (`core/focus.py`; empty rows are also dropped from the rendered
    catalogue), rows stack by their own heights instead of one shared pitch
    (mixed tile aspects used to overlap), and the vertical anchor is no
    longer clamped at the bottom so the last row can reach the anchor line.
  - Power actions **report their refusal** instead of failing silently.

## Release state (0.1.0)

The paperwork a first release needs is done: **GPL-3.0-or-later** with an
SPDX line in every source file, an AppStream metainfo file validated by
`meson test` (and so by `check.sh` and CI), logging to the journal *and* to
`$XDG_STATE_HOME/salon/salon.log` with `sys.excepthook`, `threading`'s and
GLib's writer all routed through it, CI, and the phone keyboard's
brute-force lockout. The tree is committed as eleven milestone-grouped
commits rather than the working directory it used to be.

The Flatpak has now actually been built and installed rather than assumed:
libmanette builds against the GNOME 50 SDK, `$bindir/salon` finds the
gresource and the compiled schemas inside the sandbox, and the packaged
module tree imports. The manifest header carries the exact command.

Both of the things that were "left for when there is a public repository"
are now done. The application id is **`io.github.alexydaher.Salon`** — the
old one asserted `salon.rocks`, which was never registered, and an AppStream
id has to be something its author demonstrably controls. The metainfo has
`<screenshots>` pinned to the `v0.1.0` tag, plus bugtracker, vcs-browser and
contribute URLs, and the Flatpak manifest builds from a git source rather
than `type: dir`. The repository is `github.com/alexydaher/salon`.

**The session was the big one.** `RequiredComponents=` in the `.session`
file did nothing — gnome-session 50 doesn't act on that key and it isn't in
the manual page any more — so picking Salon at the login screen would have
started a session containing nothing, and the restart-on-exit behaviour the
"television rather than a desktop" claim rests on did not exist. It's a real
systemd unit now (`data/systemd/`), with `Restart=always` and a bounded
start limit, plus a drop-in on `gnome-session@salon.target`. See DECISIONS.

## What is still missing

**2026-08-23: the human tested everything except CEC**, against the build at
`22141c6` — so the session, the power actions, the phone remote on a real
phone and the controller are all reported working. That is a *report*, not
a measurement taken here, and the distinction is kept below wherever the
sub-item is finer than the report was.

- **CEC has never touched hardware, and is now the only one.**
  `input/cec_in.py` and `services/cec_out.py` are written and the keycode
  table is tested, but there is no CEC adapter here and `cec-client` isn't
  installed. Everything else on this list that needed hardware has now had
  it.
- **The Salon session has been logged into.** Picking *Salon* at the login
  screen brings the Shell and Salon up. The systemd units under
  `data/systemd/` are what makes that work; `RequiredComponents=` never
  did. What has not been separately watched is the `Restart=always`
  behaviour after a crash, or the bounded start limit tripping.
- **The power actions work; a refusal has never been seen.**
  `services/power.py` calls `Suspend`/`Reboot`/`PowerOff` on logind and
  they do what they say. The part flagged as most likely to be wrong is
  still untested and structurally hard to reach: an account permitted to
  power the machine off never triggers the polkit denial, so whether that
  denial arrives back as a message on screen rather than vanishing is
  unknown. Testing it means a deliberately unprivileged account.
- **The gamepad has met one controller, and the mapping is confirmed.** A
  DualSense over USB: libmanette enumerates it as "Sony Interactive
  Entertainment DualSense Wireless Controller", and the mapping
  (Cross→OK, Circle→BACK, Square→OPTIONS, Triangle→SEARCH, Options→MENU) is
  reported correct in use — it had previously only been reasoned about. No
  second pad has been tried. What was measured here rather than reported:
  **a stick at rest is not at zero.** Hands off the pad, both Y axes report
  +0.11..+0.15 continuously, about sixty events a second, so the old 0.15
  right-stick dead zone had a margin of 0.016 against a cursor that slides
  down the screen by itself. It's 0.25 now, with
  `actions.stick_deflection` rescaling what's left so the wider dead zone
  costs no slow-speed control. The DualSense's touchpad also enumerates as
  a mouse: brushing it moves Salon's pointer and wakes hover-to-focus.
- **Only web tiles can be launched fullscreen.** URL tiles pass
  `--start-fullscreen` (per-tile toggle in the editor); native apps decide
  their own window state and no Wayland client may override another's.
- **The Flatpak needs `--disable-rofiles-fuse` here.** `org.flatpak.Builder`
  can't spawn `rofiles-fuse` in this environment; the flag skips the
  hardlink-protection layer and the build proceeds normally.
- **No i18n.** No gettext, no `po/`; every string is hardcoded English.
  A decision for 0.1, not an oversight — but it is a decision.
- **The phone keyboard is plaintext.** `services/pairing.py` is HTTP on the
  LAN: the code and its lockout stop a stranger *sending* text, not anyone
  on the same network *reading* it. Documented in the README rather than
  fixed, because a search box is what it is for.
- **Smaller gaps:** the backdrop is a pool of accent light, not blurred
  artwork (§7.4) — pre-blurring at fetch time is the missing piece;
  `data/fonts/` is empty, so Archivo/Inter are requested but fall back to
  the system UI font.
- **Three actions fire from behind a launched app (found 2026-08-22, not
  fixed).** `SEARCH`, `POWER` and `PLAY_PAUSE` are each handled in
  `_dispatch_action` *above* the `if self._child_active: return` guard, so
  while an application is covering Salon they act on a window nobody can
  see. Measured, from the phone, with a real child in front:
  - `PLAY_PAUSE` "falls through to launching the focused tile when nothing
    is playing" — so with a paused player it **launched GeForce NOW**
    behind the app that was already running. The worst of the three.
  - `SEARCH` opened the search overlay behind the app (`get_visible()`
    True), and because the search branch is *also* above the guard, the
    phone's D-pad then drove an invisible screen.
  - `POWER` is the same shape (system menu); read off the dispatch order
    rather than measured.
  The MENU handler's own comment already states the rule these break: "a
  menu drawn in Salon's own window would appear underneath Netflix where
  nobody can see it". Not the RemoteDesktop consent dialog — all three
  reproduced with the grant already held and no dialog shown.
- **The phone lists the catalogue, not every installed app.** 11 tiles
  against 53 installed here. Settings → Providers → `show-apps-row` is the
  workaround (measured: 11 → 64 tiles, via an "All applications" row), but
  it adds that row to the television too. A phone-only all-apps list is the
  real fix.
- **The phone remote has now met a real phone** (2026-08-23, against the
  build carrying the muted-video screen-awake fallback). Before that, every
  endpoint, the QR (read back off a screen capture with libzbar) and each
  of the page's four panes had been verified — the panes by rendering the
  real page in headless Chrome at a phone viewport against a running
  server. The harness pattern is worth keeping: drive `HomeView` directly,
  then talk HTTP to it from a worker thread. What a browser could not tell
  us — touch events, `navigator.vibrate`, the wake fallback, Add to Home
  Screen, the trackpad's feel — is reported working rather than measured
  here, and no one timed how long a phone screen actually stays lit.
- **Accessibility is published but has never met a screen reader.** Tiles,
  rows, the top bar and the settings rows all carry roles and names, and the
  cursor is published as SELECTED plus ACTIVE_DESCENDANT on the container
  (the tiles never take GTK focus — `core/focus.py` owns navigation). This
  was verified by walking the live AT-SPI tree: rows and tiles named, the
  glyphs reading "Wi-Fi: SFR_936F" and "Battery 61%", exactly one tile
  SELECTED, following the cursor. Orca itself has not been run against it,
  so whether each tile is *spoken* on arrival is still unverified.

## Where to look next

- **Needs the real TV, not this monitor:** whether 320×180du tiles and the
  38% row anchor read correctly at three metres, and whether the bloom is
  too strong or too weak on a panel with a different black level.
- **Needs hardware, and it is only CEC now.** `input/cec_in.py` and
  `services/cec_out.py` have never run against a real device; there is no
  adapter here and `cec-client` isn't installed. The gamepad and the phone
  both got their hardware pass on 2026-08-23.
- **Needs an unprivileged account:** the polkit refusal path in
  `services/power.py`. The power actions work, which is precisely why that
  branch is unreachable from the machine they were tested on.
- **Worth doing next if anything:** pre-blurred backdrop artwork, and an
  A–Z rail in the all-apps grid — 200 apps at five columns is 40 rows of
  D-pad. On the phone: the all-apps list (it shows the *catalogue*, not
  every installed application), and search from the phone rather than
  through the television's search screen.
- `DECISIONS.md` has the dated reasoning for every judgement call made
  without an explicit spec answer.

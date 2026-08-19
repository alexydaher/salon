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

## Current state (as of 2026-08-19)

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
  on a worker thread. `services/pairing.py` is the §6.12 phone keyboard: a
  `SoupServer` started only while search is open, one page, a four-digit
  code checked with `compare_digest` on every POST, five-minute expiry —
  verified end to end (page served, wrong code rejected 403, right code
  delivered, clean shutdown).
- **`core/qr.py` exists, is tested, and is deliberately not wired up.**
  A dependency-free QR encoder (byte mode, EC level M, versions 1-6),
  verified by decoding its output with libzbar. It was written to replace
  the pairing screen's printed URL with a scannable code, and then
  explicitly deferred by the human before the widget was built. The pairing
  hint still shows the URL and code as text. To finish it: render the
  matrix and place it in `SearchOverlay`'s hint area. Do not delete it.
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
  to a mouse. The power actions themselves have never been invoked against
  the real machine; only the read-only `Can*` queries have.
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
  `rocks.salon.Salon.yaml` Flatpak manifest, `core/sandbox.py` +
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

Two things are deliberately left for when there is a public repository:
the metainfo has no `<screenshots>` (AppStream needs absolute URLs; the
images are already in `docs/screenshots/`), and the homepage URL claims
`salon.rocks`, which is the domain the application id already asserts —
if that isn't registered, the *id* is what has to change.

## What is still missing

What's left is hardware verification and a short list of documented gaps.

- **CEC has never touched hardware.** `input/cec_in.py` and
  `services/cec_out.py` are written and the keycode table is tested, but
  there is no CEC adapter here and `cec-client` isn't installed.
- **The gamepad has never touched hardware either.** The libmanette source
  and hotplug are wired, and Settings → Input → "Test a controller" shows
  what Salon receives live, but no controller has been attached in any
  session.
- **Only web tiles can be launched fullscreen.** URL tiles pass
  `--start-fullscreen` (per-tile toggle in the editor); native apps decide
  their own window state and no Wayland client may override another's.
- **The Flatpak needs `--disable-rofiles-fuse` here.** `org.flatpak.Builder`
  can't spawn `rofiles-fuse` in this environment; the flag skips the
  hardlink-protection layer and the build proceeds normally.
- **No i18n.** No gettext, no `po/`; every string is hardcoded English.
  A decision for 0.1, not an oversight — but it is a decision.
- **Smaller gaps:** the backdrop is a pool of accent light, not blurred
  artwork (§7.4) — pre-blurring at fetch time is the missing piece;
  `data/fonts/` is empty, so Archivo/Inter are requested but fall back to
  the system UI font; `core/qr.py` is finished and tested but deliberately
  unwired (see above).
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
- **Needs hardware:** the gamepad source and HDMI-CEC, neither of which has
  ever run against a real device. The RemoteDesktop pointer path *has* been
  re-verified live; what's untested there is whether the right stick reads
  well as a cursor on a real controller.
- **Worth doing next if anything:** wire `core/qr.py` into the pairing hint,
  pre-blurred backdrop artwork, idle/screensaver behaviour (Salon sits at
  full brightness indefinitely today), and an A–Z rail in the all-apps grid
  — 200 apps at five columns is 40 rows of D-pad.
- `DECISIONS.md` has the dated reasoning for every judgement call made
  without an explicit spec answer.

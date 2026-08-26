# Decisions

One-paragraph, dated entries for judgment calls made without an explicit
answer in the spec. See CLAUDE.md for current milestone status.

## 2026-08-18

**Backfilled M1/M2 core under the existing POC rather than rewriting the
POC first.** The project had already jumped from M0 straight to a working
proof-of-concept (real launching, gamepad, hardcoded tiles) rather than
following the milestones in order. Rather than unwind that first, this
session built the real `core/focus.py`, `core/catalog.py`,
`providers/static.py`, and `core/ranking.py` as the milestones specify
(pure, headless, tested), then wired them under `ui/home.py` in place of
the hardcoded catalog and ad hoc navigation. Rejected: reverting the POC to
a blank M1 starting point first. Reason: the POC is the only thing that's
been run and used; replacing its guts incrementally kept the app runnable
at every step instead of going dark for a session.

**`providers/static.py` is a plain function, not a `Provider` ABC
instance.** The plan's §6.10 Provider ABC (`async def rows()`, `refresh()`,
timeout + exception isolation for third-party providers) is explicitly M9
scope. Building that scaffolding now for a single trusted, synchronous,
in-process source would be inventing machinery nothing yet needs — ground
rule 1 ("do not build ahead"). `core/catalog.py` takes a plain `list[Row]`
so the real ABC can be dropped in at M9 without changing `Catalog`'s shape.

**`Repeater` (input/actions.py) is wired into both keyboard and gamepad
in `ui/home.py`, ahead of a formal M2 UI milestone.** The module itself is
pure/tested per the plan's M2 scope. Wiring it required tracking held-key
state to distinguish a fresh physical press from GTK's own OS-level
key-pressed auto-repeat (which reuses the same keyval), and adding a
`button-release-event` + axis-centered-transition release path to
`GamepadSource` that didn't exist before. Judgment call: this was small
and mechanical enough (no new geometry/animation risk) to finish rather
than leave the module built-but-unused.

**Stopped before M4 (row anchoring/backdrop/status bar) despite having
budget left in the session.** M3's tile widget (Gtk.Fixed + Gsk.Transform
scale via Adw.SpringAnimation) is code-complete but its own acceptance
criterion in the plan requires visual verification on real hardware/TV,
which the human is doing separately and asked not to be tested here right
now. Ground rule 1 says not to start the next milestone before the current
one is verified. Row anchoring in particular needs live `compute_bounds()`
geometry against a real allocation to get right — exactly the kind of GTK
code the plan says not to unit-test — so building it now, unverified, on
top of an also-unverified M3 would stack two rounds of unconfirmed visual
work. Used the remaining time on `scripts/check.sh` and this file instead:
zero visual risk, directly mandated by the plan's own ground rules, and
previously missing.

**`scripts/check.sh` also runs `meson compile -C build`, not just
ruff/mypy/pytest.** The plan's M0 acceptance criterion includes "meson
compile && ./salon shows a fullscreen dark window." The script checks the
build half of that (compile must succeed) but deliberately does not launch
`./salon` itself — a gate script spawning a fullscreen GUI app is wrong
regardless of the current no-live-testing constraint; that check belongs
to a human (or a future `run` skill/agent with a real display) verifying
the app, not to an automated gate.

**Went ahead and built M4 + M5 in the same session as an unverified M3,
on explicit instruction to finish both right now.** This reverses the
previous entry's caution. The instruction to proceed was direct and
repeated; the previous entry's ground-rule-1 caution stands as the
*default* behavior, not as something to argue with an explicit
instruction to the contrary. What changed to make this tractable anyway:
row/tile pixel sizes are fixed constants (not measured live via
`compute_bounds()`), which turns the anchoring math into something
checkable by reading the code rather than something that only exists at
runtime — see the next two entries for what specifically that risks.

**Row and tile viewport "clipping" uses `Gtk.Fixed` + `overflow=HIDDEN` +
a single child, not `Gtk.ScrolledWindow`/`Gtk.Viewport`.** Tried the
latter first: headless `measure()` calls on both `Gtk.Viewport` and
`Gtk.ScrolledWindow` (with `propagate-natural-{width,height}` at its
default `False`) still reported the *child's* full natural size rather
than a bounded one, in a throwaway unparented-widget test. Rather than
trust that measurement (possibly just an artifact of measuring outside a
real window/style-context) or spend more of this session's budget
chasing it, fell back to the mechanism already proven to work for tile
scale: a `Gtk.Fixed` whose one child is positioned via
`set_child_transform`, with `overflow=HIDDEN` doing the actual render
clipping. The reasoning for why this should be safe even though
`Gtk.Fixed.measure()` also reports the child's full size: GTK's
*allocate* phase (not measure) is what actually bounds a widget's
rendered size, driven top-down from the real (fixed, fullscreen) window
size regardless of what a child's measurement claims to want, and
`overflow=HIDDEN` clips rendering to whatever allocation actually lands —
measurement mismatches should at worst produce harmless stderr warnings,
not visual overflow. This chain of reasoning is exactly the kind of thing
that's cheap to get subtly wrong without a live window to check against —
if row/tile clipping visibly overflows or warnings spam the console, this
is the first place to look.

**Row and tile layout geometry (heading height, row spacing, peek margin,
anchor fraction) are constants picked by reading the spec, not tuned
against a screen.** `_HEADING_HEIGHT_PX = 32`, `_TILE_PEEK_MARGIN_PX =
64`, `_ROW_ANCHOR_FRACTION = 0.38` (the spec's own number), etc., in
`ui/home.py`. The anchor fraction is straight from §6.1; the others are
reasonable guesses sized against `TILE_WIDTH`/`TILE_HEIGHT` from
`ui/tile.py`. These are the first numbers to retune once someone can
actually watch the home screen scroll.

**`LauncherService` was verified by driving it directly with real,
harmless subprocesses (`true`, `sleep N`) and a real (but window-less)
`Gtk.Application`, not by launching an actual tile.** This exercises the
full state machine — phase transitions, the 400ms return-debounce, the
process-exit fallback path, `cancel()`'s force-exit — against real
`Gio.Subprocess`/`GLib` timing, which is meaningfully stronger evidence
than reading the code, but it is not the same as confirming the launching
overlay actually paints correctly or that a real browser/app window
triggers `notify::is-active` the way `sleep` obviously can't. Also
verified `Gtk.Application.inhibit()`/`uninhibit()` standalone (acquire,
then immediately release) since it's the one call in this file that talks
to the real session over D-Bus, however briefly.

**Found and fixed a real bug this way**: `Catalog` rejected the catalogue
outright (falling back to empty) the moment anything was pushed to
Recents, because it enforced globally-unique tile ids and Recents by
design re-lists a tile id that already exists in its home row. Fixed by
scoping the uniqueness check to within a row (see `core/catalog.py`,
`tests/test_catalog.py::test_same_tile_id_allowed_across_different_rows`).
Found by constructing `HomeView` headlessly end-to-end (real
`Gtk.Application`, real `Gio.Settings`, sandboxed `XDG_CONFIG_HOME`/
`XDG_DATA_HOME` so it never touched the real `~/.config/salon/tiles.json`)
and calling the same push-then-refresh path `_on_launch_started` uses.
This is worth repeating as a matter of habit before trusting any new
catalog/provider wiring in this codebase — it caught something that
`Catalog`'s own unit tests didn't, because those tests never modeled two
rows sharing a tile.

## 2026-08-19

**Found the actual cause of the "halo cut off in the top-left corner" bug
after live feedback, and fixed the root cause rather than patching around
it.** The row and tile viewports in `ui/home.py` (`Gtk.Fixed` +
`overflow=HIDDEN`) were sized *exactly* to each tile's rest-state box.
Any focus-scale growth, and the CSS glow added in this same pass, had
nowhere to bleed into — worst at column 0, where the clip boundary sits
flush against the tile's own left edge, compounding with the same issue
at the top edge. Fixed by giving `TileWidget` itself a `TILE_BLEED` (28px)
margin of transparent padding on every side (`ui/tile.py`), growing each
row viewport's height by `2*TILE_BLEED` to match, and shrinking the
safe-area's left/right margins by `TILE_BLEED` to compensate — the tile's
*visual* rest position on screen is unchanged (the two offsets cancel
exactly; verified by hand for both column 0 and a scrolled-into-focus
column), but there's now genuine clip buffer around every tile. Switched
each row's tile container from `Gtk.Box` to `Gtk.Fixed` at the same time,
since padded tile footprints legitimately overlap their neighbours (by
design — that overlap is where the glow bleeding onto adjacent tiles is
*supposed* to show up) and `Gtk.Box`'s spacing can't be negative.

**Retuned the focus-scale spring, and added a CSS glow, after "it's not
modern" / "it's not good" feedback on the motion and the flat border.**
The brief's own numbers (damping 0.82, stiffness 320) are visibly
underdamped — a real bounce/overshoot on every focus change, not just a
one-off; changed to damping 0.92 / stiffness 500 for a fast, minimal-
overshoot settle. This is a real judgment call overriding a literal
number in the brief, made on direct instruction ("do better", "I expect
more from you") rather than guessed — worth revisiting again after a live
look, since "modern" is a taste call the human should get final say on,
not something to consider settled from one round of tuning. Also replaced
`.salon-tile.focused`'s flat 4px border with a two-layer `box-shadow`
(crisp ring + soft blurred glow in the accent colour) — a legitimate,
cheap approximation of §7.1's "light-fall focus" glow that the tile-bleed
fix above makes possible without clipping, ahead of the real blurred-
bloom widget (M3 stage 2). Also implemented §6.1's row-heading dimming
(unfocused rows' headings at 55% opacity) since it was in the spec,
already had the a wiring point (`_update_focus`), and was a one-line-per-
row gap making the screen read flatter than intended.

**Built a minimal power/exit menu now rather than waiting for M8
Settings, on the human's own framing: Salon runs fullscreen, controlled
only by a controller or a phone-as-mouse (KDE Connect) — no keyboard.**
Before this change there was *no reachable way* to suspend, shut down, or
even exit Salon back to the desktop without a physical keyboard (the only
quit path was the dev-only Escape shortcut, deliberately excluded from
the Action pipeline). That's not a missing nice-to-have, it's a machine
the user can get stuck in. `services/power.py` wraps logind
(Suspend/Reboot/PowerOff over the *system* bus, never `systemctl`, per
§8); `ui/overlays.py`'s new `SystemMenu` is a D-pad-navigable list of real
`Gtk.Button`s, so mouse clicks (KDE Connect) work with zero extra
wiring — matching the "or a mouse" half of the brief for free rather than
needing separate handling. Menu items are built from `CanSuspend`/
`CanReboot`/`CanPowerOff` at startup so the menu never offers something
logind will refuse. Bound to `Action.MENU`, deliberately checked *before*
every other mode gate in `_handle_action` (including `pointer_mode`/
`child_active`) — it has to survive a stuck launch or an active pointer
session, since it's the only way out of either. Explicitly not full M8
Settings (no tile editor, no appearance/input/browser/audio panels) —
that's still real, separate future work; this is the narrow slice that
was actually urgent. Verified end-to-end (menu open/close, navigation,
BACK, OK-activates-selected, the MENU-during-pointer_mode escape-hatch
case, and the Settings tile opening the same menu) against the real
logind `Can*` queries on this machine — but `suspend()`/`reboot()`/
`power_off()` themselves were never actually invoked in testing, for the
obvious reason that this is the human's real, currently-running machine.

## 2026-08-18 — UI/UX overhaul, and the review that preceded it

The human ran M5 on a real screen and reported that it wasn't up to bar.
A screenshot showed row headings truncated to "Ap…" and "Streami…", tiles
that occupied a fraction of a 1920px screen with most of it empty, a flat
green cast over the whole display, and the focused tile's halo clipped
mid-air. This entry records what the review found and what changed. All
of it was verified on the real display this time, not reasoned about: a
throwaway harness runs the app, drives it with synthetic `Action`s, and
captures the window through `Gtk.WidgetPaintable` →
`Gsk.Renderer.render_texture` → PNG. Every claim below was checked
against a capture.

**Built `ui/scale.py`, the du→px runtime pipeline (§7.2), which had been
an accepted-but-unbuilt M0 gap.** This was the single root cause of "the
UI is too small". Every size in the codebase was a raw px constant chosen
to look reasonable on a desktop monitor: tiles 280×160 against the
brief's 320×180du, row headings 20px against 34du, the clock 28px
against 44du. The brief's own numbers were right; nothing was resolving
them. `ui/scale.py` now computes `du = monitor_height / 1080` from
`Gdk.Monitor` geometry, emits every du-derived token as a CSS custom
property on `:root` at `PRIORITY_APPLICATION + 1`, and recomputes when
the window moves between monitors. GTK 4.16+ supports `var()`, so
`salon.css` is now written entirely against custom properties with no raw
px, and `tests/test_css_has_no_raw_px.py` enforces that §10 gate — which
had never been written. Logical monitor geometry is deliberately what's
sampled: a 4K TV the compositor already scales 2× reports 1080 and
correctly gets du=1.0, while an unscaled 4K TV reports 2160 and gets 2.0.

**Row headings truncated because `Gtk.Fixed` allocates children their
*minimum* size, not their natural one.** A `Gtk.Label` with
`ellipsize=END` has a minimum width of roughly one ellipsis, so every
heading collapsed to "Ap…". Nothing about the labels was wrong; the
container was. Rows are now positioned at explicit coordinates with
explicit `set_size_request` widths, so allocation is deterministic
everywhere rather than depending on which of two size requests a
container happens to consult.

**Row viewports now span the full window width instead of stopping at the
safe-area margin.** §6.1 wants the focused tile left-anchored at the safe
margin with the previous tile peeking past it, which is only expressible
if the clip boundary is the *screen edge*. Clipping at the safe margin
meant the focused tile's glow was cut off in a hard vertical line partway
across the screen — the artefact visible in the human's screenshot, and
the thing the previous session's `TILE_BLEED` fix had tried and failed to
solve from the wrong end. As a consequence `_row_scroll_x` no longer
special-cases column 0: every row left-anchors identically, which also
fixes rows disagreeing with each other about where their first tile sits.

**Scroll offsets are now clamped to the content bounds on both axes.**
Previously, focusing the third tile of a four-tile row scrolled it to the
left margin and left two thirds of the screen empty. A row now
left-anchors its focused tile right up until doing so would strand empty
space at the right edge, then stops. This is a deliberate, small
departure from §6.1's literal "focused tile is left-anchored" — for the
last screenful of a row it isn't — taken because the alternative looks
broken, and every TV launcher worth copying does the same. The vertical
anchor is clamped the same way, and pins below the status bar when the
whole catalogue is shorter than the screen rather than floating it in
dead space.

**Non-focused rows were never scrolled at all.** `_update_focus` only
ever positioned the focused row, so every other row sat at offset 0
regardless of its remembered column. Added `FocusModel.column_for(row)`
(pure, tested) so the UI can ask where each row is resting, and every row
is now positioned on each focus change.

**The backdrop's flat accent wash became a bounded pool of light.** It
was filling the entire screen with the focused tile's accent at 12%
luminance; on GeForce NOW's `#76B900` that reads as the display being
tinted green, not as ambient light — exactly what the screenshot showed.
It's now a feathered radial gradient at 13% alpha over 40% of the screen,
positioned behind the focused tile, with the 150ms debounce §7.4 asks for
so fast scrolling doesn't strobe it.

**Implemented §7.3 stage 2 (the bloom) and §7.4 artwork levels 3 and 4.**
The tile now draws itself in `do_snapshot` instead of nesting CSS boxes,
because all three of the things that make it look designed — the scale
transform, `push_blur`, and gradient-built cards — are unreachable from
GTK4 CSS. Tiles with no artwork were previously a flat `surface-1`
rectangle with a 48px icon, which is the "looks like a fallback" outcome
§7.4 explicitly warns against; they're now an icon on a gradient derived
from that icon's own dominant colour (level 3), or the title's initial on
a hashed gradient (level 4), both with a vignette and the title in the
display face. `services/artwork.py` does the resolution, caching by
(path, mtime), and dominant-colour extraction via GdkPixbuf. Missing
icons are detected with `IconTheme.has_icon` rather than allowed to
resolve to `image-missing` — the red no-entry glyph on the Chrome tile in
the human's screenshot was that fallback, and it reads as a bug.

**Bloom colour is normalised to a light source (`glow_color`).** The
first working version was invisible: a tile's accent is whatever its
artwork happens to be built from, and a muted icon or a hashed hue
blurred at low alpha against near-black produces no visible glow at all,
leaving the focus treatment reading as a flat outline again. Lightness
and saturation are now lifted to a floor, preserving hue. The bloom rect
is also drawn slightly *larger* than the tile rather than inset — the
card is opaque and covers whatever sits under it, so an inset bloom is
only ever visible as a few pixels of feather.

**Mouse is now a first-class input.** The brief's own hardware list is
"a controller, or a phone acting as a trackpad", and a phone trackpad
produces nothing but pointer events — yet tiles had no click handler at
all, so the entire pointer path could only ever reach the power menu.
Tiles now take clicks and hover-to-focus, the scroll wheel navigates, and
the system menu's selection follows the pointer. Hover is gated on the
pointer having actually moved: GTK delivers a motion event whenever a
widget maps or scrolls under a stationary cursor, which made the power
menu open with whatever item happened to sit under the mouse selected
instead of the first one. The cursor itself stays hidden until the mouse
moves and hides again on the next D-pad press.

**Bugs found in the launch path.** (1) `--ozone-platform=wayland` was
hardcoded, which §0 lists as a mistake that breaks X11 sessions outright;
it's now conditional on `XDG_SESSION_TYPE`, passed into
`core/launchspec.py` as an argument so the module stays pure and both
branches are testable. (2) `--force-device-scale-factor` was always 1.0,
making web UI unreadable at three metres on a 4K TV; it's now derived
from the same du scale and clamped to [1.0, 3.0] per §6.3. (3) The
subprocess-exit return signal fired immediately for Flatpak and
systemd-scoped launches, whose wrapper PID exits at once — §11 says to
expect exactly this — so the launching overlay tore down a fraction of a
second after appearing and "returned" while the app was still starting.
An exit within 2.5s of launch while still awaiting child focus is now
ignored, leaving the window-activity signal to carry it as §6.4 intends.
(4) The idle inhibit was only ever released by its timer, so returning
within 90 seconds left the screen pinned awake in front of an idle
launcher. (5) `DESKTOP` launches parsed `Exec=` by hand and spawned it
directly, bypassing D-Bus activation, transient systemd scopes and
startup notification; they now go through `Gio.DesktopAppInfo` per §6.3,
falling back to argv resolution when there's no such entry. Verified by
actually launching gnome-calculator from a tile.

**§6.2's boundary rubber-band was specified, produced, and thrown away.**
`FocusModel` had been returning a `Bump` on every failed move since M2
and the UI discarded it, so hitting the end of a row was silent — which
§6.2 says outright "reads as a broken remote". The UI now renders it as a
90ms overshoot-and-settle on the relevant axis.

**Added `tests/test_launchspec.py`, which did not exist.** M1's stated
acceptance criterion was that pytest proves every `LaunchKind` resolves
to correct argv "including the full Chrome flag set and the conditional
ozone flag". That milestone had been marked done with no such test; the
hardcoded ozone flag is precisely the bug it would have caught.

**Rows fade out at the top and bottom edges** via a `push_mask` alpha
gradient over the row content rather than a scrim painted on top, so the
backdrop's glow stays visible underneath. Without it the first row is
sliced by a hard clip edge directly under the clock, which reads as a
rendering fault rather than as content continuing off-screen.

## 2026-08-19 — M7: search, on-screen keyboard, phone pairing

**Deviated from §6.6's "6x5 grid: QWERTY layout" — those two requirements
contradict each other.** QWERTY rows are ten, nine and seven keys wide;
wrapping the alphabet at six columns produces a grid nobody reads as a
keyboard. The stated intent is a recognisable QWERTY that arrow keys can
cross, so `core/osk.py` is a ten-column layout with ragged rows, plus a
digits row and the `@ . - /` symbols a URL or an account name needs. Space,
Backspace, Shift and Done are all present as §6.6 requires.

**Vertical movement across the keyboard is spatial, not by index.** Each
key occupies a span of grid cells and moving up or down lands on whichever
key contains the current key's centre. Index-based movement would send "b"
(fifth in its row) to "Done" (fourth and last in the bottom row) simply
because the numbers are close; spatially it lands on Space, which is what
is actually underneath it. Both cases are tested.

**Shift is one-shot, like a phone keyboard**, not a latch that survives the
next letter. Typing a name or a URL almost never wants two capitals in a
row, and a stuck Shift on a screen you can't see the state of is worse than
an extra press.

**The keyboard's edge behaviour is a return value, not a silent clamp.**
`KeyboardModel.move()` returns False at a row edge, which is what lets the
search screen use RIGHT-off-the-keyboard to cross into the results grid and
LEFT-off-the-results to cross back. A model that clamped internally would
force the widget to reimplement the edge test.

**Installed-app discovery runs on a worker thread.** `Gio.AppInfo.get_all()`
walks every `applications` directory on the system; §10 forbids that on the
main loop. Search therefore opens showing the catalogue immediately and
widens when the scan lands, rather than stalling for it.

**Empty query shows the catalogue rather than nothing.** The user opened
search to go somewhere; a blank screen that refuses to admit anything
exists until they type is hostile on a D-pad.

**Found and fixed a real pointer bug while verifying search.** The printed
pane state disagreed with the rendered one: the results grid was focused
when the model said the keyboard was. Cause — GTK delivers a motion event
when a window maps under a stationary cursor, so `HomeView`'s motion
handler concluded the pointer was in use at startup, revealed the cursor,
and armed hover-to-focus; the next widget rebuild under the parked mouse
then silently stole focus. Motion is now only believed when the position
actually changed. The same class of bug had already been patched at two
call sites (tiles, the power menu) by gating on a flag — this was the flag
itself being wrong.

**Wrote a QR encoder (`core/qr.py`) rather than adding a dependency, then
stopped short of wiring it up on instruction.** The human asked for a QR
code instead of the printed pairing URL, then said to skip it for now. The
encoder is finished: byte mode, EC level M, versions 1-6, all eight masks
with penalty scoring. It is **not referenced by any UI** — the pairing hint
still prints the URL and code as text. It's kept rather than deleted
because it is complete and verified, and deleting tested working code that
was asked for minutes earlier is pure waste; a future session only needs to
render the matrix and place it in the search overlay's hint area.

Adding a third-party encoder would have meant a new runtime dependency in
the Flatpak manifest and in every distro package, for one small screen.
Levels: M rather than L because the code is read off a television across a
room, at an angle, often with glare, and the redundancy costs one version
step.

**The QR encoder is verified against a real decoder, and that mattered.**
`tests/test_qr.py` renders the matrix and decodes it with libzbar through
ctypes (test-only; Salon has no such dependency, and the test skips when
the library is absent). The first implementation passed every structural
check I wrote — correct size, finder patterns, timing patterns, format
strings matching the standard's table, Reed-Solomon matching a published
vector, and a clean round-trip of its own data placement — and decoded on
nothing at all. The fault was the format-information bit order: the 15-bit
string is placed most-significant-bit first, and I had reversed it.
Nothing self-consistent can catch that, which is the whole argument for
testing against an independent decoder rather than against my own
understanding. libqrencode, also already on the system, was used to
establish which of the encoder and the test harness was wrong.

## 2026-08-19 — M8 (Settings and the tile editor)

**Settings is a purpose-built two-pane screen, not `Adw.PreferencesPage`.**
§6.8 requires it to look like the home screen and be operable with six
buttons; libadwaita's preference rows assume a pointer, a scrollbar and a
desktop-sized hit target. `ui/settings/widgets.py` is the replacement kit:
six row kinds over one `SettingsList`, where UP/DOWN moves the selection,
LEFT/RIGHT adjusts the selected row *in place* (a toggle flips, a choice
cycles, a range steps) and OK activates it. Nothing that has three options
gets a sub-dialog. Every row is still a real `Gtk.Button`, so a mouse works
without a second code path.

**Panels are rebuilt from a callback, never mutated in place.** A settings
list is a few dozen widgets; keeping a retained widget tree in sync with a
catalogue the user is actively editing is exactly the bookkeeping that goes
wrong quietly. `SettingsContext.save_config` therefore both writes and
rebuilds, because every editing call site is `edit(); save_config()`.

**The tile editor writes `tiles.json` and lets the existing file monitor
reload it.** It deliberately does not reach into `HomeView` to patch the
live catalogue: a hand edit and an in-app edit now come back in through the
same single path, so there is only one way the catalogue is ever reloaded.
The consequence is that `HomeView._config` is *replaced* by each reload, so
`SettingsScreen.set_config()` repoints the editor at the new object — an
edit applied to the previous one would be silently detached.

**`do_size_allocate` on a `Gtk.Fixed` subclass never runs.** GTK4 dispatches
allocation to the layout manager *instead of* the widget class vfunc when
one is set, and every `Gtk.Fixed` installs a `GtkFixedLayout` in its own
init. `_LayoutViewport.on_resize` had therefore never once fired, and
`HomeView._viewport_width/_height` had always been the 1920×1080 fallback
constants — invisible on this monitor, wrong on any other. Swapping the
layout manager is not a fix either: `GtkFixed` caches the one it created
and `put`/`move`/`set_child_transform` all go through that cached pointer,
so replacing it makes those three fail outright. `motion.SizeReporter` is
the fix — a plain `Gtk.Widget` (no layout manager, so its vfunc is the one
GTK calls) wrapping the container and reporting the real size. Without it
the settings rows collapsed to a single ellipsis, because a `Gtk.Fixed`
sizes children from their own measurement and an ellipsized label measures
one ellipsis wide.

**The first tile in every row had half its bloom cut off.** Tiles were
placed at `col * step - bleed` inside the row's tiles box, so column 0 sat
at a negative x — outside the box's own bounds, and clipped along that edge.
Tiles now start at x=0 and the row's scroll offset carries the bleed
instead. Verified by sampling the rendered pixels either side of the card:
the left edge went from a hard 28→72 step to the same smooth ~35px falloff
the right edge always had.

**Vertical movement now carries the column instead of remembering it per
row.** The human asked for it directly: moving down should land on the tile
below the focused one, not wherever that row was last left. Per-row column
memory is gone, and `column_for()` rests *every* row at the focused column
so the grid stays aligned — otherwise moving down would land on a tile that
wasn't under the cursor a moment earlier. A shorter row clamps, and the
clamp sticks on the way back up; the alternative is a cursor that travels
sideways on its own.

**Gamepad pointer control is on by default, and the consent dialog appears
exactly once.** The complaint was the RemoteDesktop prompt landing on top of
Netflix or Prime on every launch. The fix is the portal's own mechanism, not
a toggle: `org.freedesktop.portal.RemoteDesktop` version 2 (this machine has
it) added `persist_mode` and `restore_token`, the same thing screen-sharing
tools use so they don't re-prompt. Salon asks for
`PERSIST_EXPLICITLY_REVOKED`, stores the token the portal hands back in
`remote-desktop-restore-token`, and passes it to `SelectDevices` next time;
the portal then restores the grant silently.

Verified live, not assumed. Driving the dialog needed AT-SPI (it belongs to
xdg-desktop-portal-gnome, so nothing in-process can reach it), and two
things only showed up by doing it: the "Remember This Selection" box is
ticked by default — so a real user gets the persistent grant without doing
anything extra — and Share stays *insensitive* until the interaction switch
is on, which is what made the first three attempts look like the portal was
ignoring us. With a stored token, a second run of Salon starts the session
in under a second with zero dialogs; confirmed by inspecting the portal's
window list mid-run.

Two consequences fell out of it. The session is now taken at startup rather
than at child-focus time, so the one-time dialog appears over Salon's own
home screen, anchored to Salon's window, while nothing is launching — asking
mid-launch is what put it on top of Netflix. It's skipped entirely when the
catalogue has no browser tile, so a machine full of native apps is never
prompted at all. And a token the portal has stopped honouring (revoked in
system settings, or invalidated by a compositor restart) is *discarded* on
failure rather than retried forever, because the retry is silent and the
user would only see the pointer quietly never work again. Settings → Input
has "Forget remote-control permission" as the matching way to hand it back.

**Settings and the power menu got visible buttons in the status bar.** A
controller reaches both through MENU and a keyboard has no binding at all,
so a mouse — one of the three input paths the brief names — had no way in
and nothing on screen to say those existed. They sit dimmed at 55% until
hovered.

**Launching fullscreen is only within Salon's power for web tiles.** URL
tiles already pass `--start-fullscreen`, and that is now a per-tile toggle
in the editor. Native apps (`desktop`, `command`, `flatpak`) decide their
own window state and no Wayland client may override another's, so there is
deliberately no equivalent switch for them rather than one that quietly
does nothing.

**The accent colour is the one live colour token.** Everything else is
generated into `tokens.css` at build time; `ui/theme.py` installs a provider
above it that redefines `@accent`, and exposes `theme.accent()` for the two
places CSS cannot reach — the tile's focus ring and the backdrop's light
pool, both drawn in `do_snapshot`. Keeping that a module-level function
rather than a constructor argument means a colour change reaches every
already-built widget without being threaded through.

## 2026-08-19 — M9 (providers)

**The provider runner lives in `core/`, the providers don't.** `Provider`,
`ProviderContext` and `collect()` are pure and gi-free, so the failure
isolation that is the entire point of this layer can be tested without a
display — and it is: a raising provider, a hanging one, and one that returns
a string instead of a list all have tests. The concrete providers need
`Gio.Settings` and desktop-entry scanning, so they stay under
`salon/providers/`.

**One shared deadline, not one per provider.** Three providers with three
seconds each is a nine-second worst case, and the user is looking at an
empty screen for all nine. They run concurrently against a single deadline
instead. A thread that never finishes can't be killed in Python, so provider
threads are daemons and late results are discarded — a hung provider costs
one leaked thread until exit, rather than a launcher that won't start.

**Providers read the config, not each other's output.** The obvious design
has the recents provider consume the static provider's rows, which makes
them ordered and therefore serial. Resolving recent tile ids against
`context.config` instead is equivalent — a tile can only be recent if it was
launched, and it could only be launched if it's in the catalogue on disk —
and it is what makes running them in parallel sound.

**The catalogue build had to become asynchronous, and that was not
optional.** `collect()` waits up to three seconds; doing that on the main
thread froze the entire interface every time a tile was launched or
`tiles.json` changed. Measured with a 50 ms heartbeat against a provider
that sleeps for thirty seconds: **6004 ms worst main-loop gap synchronous,
86 ms asynchronous**. Builds carry a generation counter, because an edit can
outrun a slow provider and an older build landing after a newer one would
silently undo it.

**`Catalog` stayed strict; `sanitize()` is the lenient front door.** The old
behaviour on a duplicate id was to catch `CatalogError` and fall back to an
*empty* catalogue — one duplicated tile id blanked the television. Rows are
now sanitised before construction: the ambiguous entries are dropped, the
rest is kept, and the user is told what was dropped.

**Turning a provider off is not a failure.** Reported as one initially, which
meant a toast on every catalogue rebuild telling the user about their own
decision. `ProviderOutcome.disabled` separates the two.

**Settings → Providers exists because the worst failure mode of a plugin
system is a row that silently isn't there.** Every provider is listed with
what it contributed or why it didn't — including modules that failed to
*import*, which never became providers at all and would otherwise be
invisible in exactly the case someone needs to see them.

## 2026-08-19 — M10 (packaging and first run)

**There was no installed executable at all.** The desktop entry has said
`Exec=salon` since M0 and nothing ever installed a `salon`; the only way to
run it was the uninstalled dev launcher. `bin/salon.in` is now configured
with the real `pkgdatadir` and installed to `$bindir`. Verified by staging a
`DESTDIR` install and running *that* copy, not the build tree.

**The Flatpak manifest is shipped with a warning in it.** Salon's whole job
is starting other applications, which is precisely what a sandbox prevents.
The only sanctioned route out is `flatpak-spawn --host`, which needs
`--talk-name=org.freedesktop.Flatpak` — a permission equivalent to
unsandboxed session access. There is no version of a launcher that is both
meaningfully confined and able to launch things, so the manifest says so
rather than implying a confinement it doesn't have. `core/sandbox.py` and a
`host_prefix` parameter on `launchspec.resolve()` make every launch kind go
out through the host when sandboxed, including `desktop`, which falls back
to `gtk-launch` because the host's `.desktop` files aren't visible inside.

**The session entry is a gnome-session definition, not a compositor.** Salon
is an ordinary Wayland client and cannot be a `wayland-sessions` target on
its own. Picking "Salon" at the login screen runs `gnome-session
--session=salon`, whose required components are the Shell and Salon — and
"required" is what makes the Shell restart Salon if it exits, which is the
difference between a television and a desktop with a launcher on it.

**CEC is wired but untested.** There is no CEC adapter on this machine and
`cec-client` isn't installed, so `input/cec_in.py` and `services/cec_out.py`
are honest about that in their docstrings. What *is* tested is the part that
would be wrong silently: the CEC 1.4 user-control-code table and the
line parsing, including that the numeric code is read rather than the label,
since cec-client localises the label.

**Onboarding is four screens and asks nothing.** The problem it solves is
narrow: Salon has no menu bar, no window controls and no text saying what
the buttons do, so someone handed a controller has no way to discover that
MENU exists. Nothing in it can be answered wrongly, every screen is
skippable, and it is checked *before* MENU in the action chain — the
introduction is what explains that MENU exists, so MENU cannot be what
dismisses it.

**A wrapping GTK label ignores `set_size_request`.** The onboarding body ran
the full 1800px width regardless. A size request sets the *minimum*; a
wrapping label's natural width is still the whole unwrapped line, and a box
hands out natural width. `set_max_width_chars()` is what actually bounds it.

## 2026-08-19 — M11 (polish, error copy, README)

**No user-facing message contains a Python repr or a bare exception.** The
pass turned `"{target!r} isn't wired up yet."` into a sentence, gave every
launch failure the tile's name (a message with no subject leaves the user
guessing which tile it was about), and rewrote the resolution errors into
things a person can act on — "No web browser was found. Install Chrome or
Chromium, or name one in Settings under Browser" rather than "No browser
command configured for URL launch."

**The README leads with what Salon can't do.** The DRM section says plainly
that Netflix, Prime Video and Disney+ cannot be played by Salon or by any
non-browser application on Linux, that this is a Widevine licensing wall
rather than a missing feature, and that the browser path is usually limited
to 720p. Burying that would make every one of those users feel lied to on
day one, and it costs nothing to say — everything that isn't DRM-locked is
unaffected.

**The icon existed and was installed correctly, and still didn't appear.**
A long XML comment between the `<?xml?>` declaration and `<svg>` pushes the
element past gdk-pixbuf's format-sniffing window; the loader then refuses
the file with "couldn't recognize the image file format" and the icon is
simply absent everywhere in the shell. Nothing warns,
`gtk4-update-icon-cache` is perfectly happy, and — the reason it survived a
visual check — `Gtk.IconPaintable` rendered the broken file without
complaint, because GTK4 does not take the same path GNOME Shell does.
Comments now live *inside* the `<svg>` element. `tests/test_icons.py` loads
every shipped icon through GdkPixbuf specifically, and separately asserts
`<svg` appears in the first 256 bytes so a regression says why rather than
just "could not recognise the file format".

## 2026-08-19 — Reachability pass (top bar, escape from a child, live preview)

**The top bar is a focus row reached by pressing UP, not a MENU-only
surface.** Settings and power were reachable two ways: the MENU button,
which nothing on screen mentions, and two dim icons a mouse could click on a
device that has no mouse. Pressing UP from the first row now moves the
cursor into the bar (Search / All apps / Settings / Power), which is what
every ten-foot launcher does and the only route that is discoverable by
pressing a direction. `core/focus.py` is untouched: the bar is not a row in
the model — it's a boolean in `HomeView` that intercepts the `Bump.UP`
the model already returns at the top edge. Putting it in the model would
mean every consumer of `FocusModel` (search results, the all-apps grid)
inherited a row that only the home screen has.

**MENU while something else owns the screen means "close it and come
back", and closing it means killing the process.** There was no way off a
fullscreen Netflix tab with a controller. Wayland forbids a client raising
itself, so Salon cannot put its own window back in front; the only lever it
has over a window it doesn't own is the process it started. `close_child()`
sends SIGTERM (so Chrome writes its profile out), then SIGKILL after four
seconds. Rejected: drawing a "return to Salon" overlay — it would render in
Salon's own window, underneath the app it is offering to close. This is
reachable *because* libmanette reads evdev directly, so gamepad and CEC
buttons arrive even while another window holds keyboard focus; a keyboard
cannot reach it and can't be made to, which is why the toast at launch names
the controller button specifically.

**A per-item menu needed its own button rather than a long-press on OK.**
Long-press is the Android TV idiom, but implementing it means firing OK on
*release*, and CEC remotes produce presses with no release at all — the TV
remote would stop being able to launch anything. Worse, no controller has
ever been attached to this machine, so betting the primary action on
button-release events arriving is untested in the one place it must not
fail. `Action.OPTIONS` is a new verb mapped to X on a pad, F10 or `o` on a
keyboard, and the CEC contents-menu and blue keys.

**Settings collapses to a strip on the bottom edge for the four settings
the home screen answers for.** Accent, safe area, tile size and row density
cannot be judged from a list of their own names. OK on one of those rows
hides the whole settings screen except a single row docked at the bottom and
turns its background transparent, so what shows through is the real home
screen — still bound to the same GSettings keys the strip writes. Rejected:
a scaled-down mock beside the list, which would have needed a second render
path that could disagree with the real one.

**Empty rows are passable in the model and invisible on screen.**
`FocusModel.handle()` refused every action while resting on a row with no
tiles, so a provider that returned nothing — or a row the user had just
created in the editor — swallowed the focus permanently: nothing moved again
until Salon restarted. Vertical movement now passes through; LEFT/RIGHT
rubber-band. Separately, `HomeView` drops zero-tile rows from the catalogue
it renders, because a heading with a void under it reads as a rendering
fault. They stay visible in the tile editor, which is where a row you just
added is supposed to be.

**Rows are stacked by their own heights, not by one shared pitch.** A single
`_row_pitch` derived from the default tile aspect was wrong the moment a
catalogue mixed aspects: a poster row (300du) ran straight through the
heading of the row beneath it. The same figure fed `_content_height`, so the
stack measured shorter than it was and the screen concluded it had nothing
to scroll — which is what made the last row unreachable. `_recompute_row_tops`
now walks the rows accumulating each one's real height.

**The vertical anchor is no longer clamped at the bottom.** Refusing to
scroll past the end of the content is right for a *row* (a void beside the
last tile looks broken) and wrong for the stack: with four rows on a 1080p
screen it left about 90px of travel, so the bottom rows could never reach
the anchor line. The focused row now always rises to the 38% anchor, leaving
empty space below it, which is what every ten-foot launcher does; the
backdrop lives in that space.

**Power actions report their refusal.** `Suspend`/`Reboot`/`PowerOff` were
dispatched with a NULL D-Bus callback, so a refusal — an inhibitor holding a
block lock, or a polkit prompt landing behind Salon's fullscreen window —
arrived as nothing at all: the menu closed and the machine carried on
running. Indistinguishable from a button that isn't wired up, which is
exactly how it was reported. The calls stay asynchronous (polkit can take
seconds) but now name the failure in a toast.

**Favourites resolve installed apps without writing to `tiles.json`.**
Pinning something from the all-apps grid would otherwise have to invent a
tile in the user's catalogue behind their back. `FavouritesProvider` falls
back to the installed-app scan for `app:`-prefixed ids it can't resolve from
the config, and only pays for that scan when there is at least one such id —
it already runs on a worker thread under the provider deadline. "Add to
Home" is the separate, explicit action that does write a tile.

**`bin/salon` builds before it runs, and there is a dev desktop entry.**
`meson install` copies the tree into `$prefix`, so GNOME's Show Applications
kept launching whatever the last install captured; every edit needed a
re-install and forgetting was silent. `scripts/install-dev.sh` writes a
desktop entry whose `Exec` is `bin/salon`, and `bin/salon` now runs ninja
first and refuses to start on a failed build rather than silently running
the previous code. `SALON_NO_AUTOBUILD=1` opts out.

## 2026-08-19 — Settings: a row has to be entered before it can be changed

**LEFT no longer edits. It leaves.** In the right-hand panel, LEFT/RIGHT
used to adjust whichever row the cursor happened to be resting on, and LEFT
only fell through to "go back" on rows that had nothing to adjust. So the
button that means *back* on the home screen, in the section list, in search
and in every sub-panel silently meant *decrement* on about half the rows in
Settings — and on those rows there was no way out except BACK, which a CEC
remote maps somewhere else entirely. The horizontal axis now reads the same
way everywhere: **RIGHT goes in, LEFT comes back out.** A row with values to
walk is *engaged* first (RIGHT, or OK where activating would otherwise
change a value blind); while engaged it takes the whole horizontal axis plus
BACK, and OK or BACK releases it. Rejected: keeping direct adjustment and
adding a separate "exit" row or relying on BACK alone. Reason: the complaint
was not that leaving was hard to *find*, it was that the same press did two
unrelated things depending on the row — the fix has to remove the ambiguity,
not document it.

**Toggles are activated, not engaged.** On/Off has no inside to step
through: engaging one would cost two presses to reach the only other value,
and LEFT inside it would mean "Off" at exactly the moment the rest of the
screen has taught it to mean "back". RIGHT flips a toggle directly, the same
as OK. Sub-panel rows (a section, a tile, a text field) are entered directly
by RIGHT too, which is what RIGHT already did in the section list.

**RIGHT refuses plain action rows instead of running them.** "Shut Down",
"Delete row" and "Add tile" do something irreversible or destructive on
activation, and a direction key must never be how a television gets turned
off — OK is a deliberate press, RIGHT is what a thumb does while reading. It
is `ActionRow(opens=...)`, defaulting to the `›` chevron the screen already
draws on every row that leads somewhere, so a drill-in row written like the
existing ones is enterable without a second flag to remember.

**The engaged state is a filled row and a heavier ring, not a glyph.**
Selected is a 16% accent tint with a thin ring; engaged is 32% with a ring
1.75× thicker and the value in white. Small `‹ ›` chevrons flank the value
of every adjustable row and light up when it is engaged, dimming per
direction when that end of the range is reached — but they are the detail,
not the signal: at three metres the difference between "the cursor is here"
and "this row has the buttons" has to be a difference in weight. They are
rendered at 2% alpha when the row isn't selected so the space is reserved
and landing on a row fades them in instead of shifting the value sideways.

**A refused press flashes the row.** RIGHT on a row with no inside, or a
step past the end of a range, brightens the row for 220ms. The lists already
rubber-band vertically for the same reason — silence at a boundary reads as
a broken remote — and there is no horizontal scroll here to bump.

**The engaged flag lives on `SettingsList`, not on the screen or the row.**
Any edit that saves the catalogue rebuilds the panel and replaces every row
object, so a reference held by the screen would point at a widget that had
already been thrown away; and every path that moves the selection has to
drop the flag, including the mouse hover and click paths the screen never
sees. The list re-applies it to whatever row is selected after a rebuild,
and drops it if that row has nothing to adjust.

## 2026-08-19 — Status glyphs, and an accessible tree

**The bar's glyphs are absent rather than approximate.** §6.9's network and
battery indicators had been left out on the grounds that a fake icon is
worse than a gap; the rule survives now that they are real. The network
glyph disappears entirely when NetworkManager can't be asked (no daemon, no
system bus) rather than drawing an "unknown" state, and the battery glyph
only ever appears on a machine whose UPower display device is a battery
that is actually present — a permanent 100% icon on the box under a
television is a lie that never changes. Both are unfocusable and
unclickable: they report, and Settings › Network is where the detail is.

**The glyph table is in `core/`, not in the D-Bus code.** `core/status.py`
maps a strength, a percentage and a connectivity state to icon names and
spoken phrases, and it's pure, so `tests/test_status.py` can assert every
bucket boundary. The failure this prevents is specific: a typo in an icon
name draws a broken-image square in the corner of a television and logs
nothing at all. The same test then asks the live icon theme whether each of
the 30-odd names it can return actually resolves, which is the half a pure
test can't cover.

**Two feeds, two update strategies.** UPower announces every percentage step
on its display device, so `BatteryWatcher` is signals only. NetworkManager
announces connect, disconnect and captive-portal transitions on the manager
object, but *signal strength* lives on the access point, and subscribing to
that means re-subscribing every time the primary connection changes — for a
number with five buckets. So `NetworkWatcher` is signals plus a 30-second
poll, and both drop an unchanged reading rather than pushing it.

**Tiles are `aria-activedescendant`, not real focus.** Salon runs its own
focus model and `HomeView` is the widget that holds GTK focus, so a screen
reader lands on the container and the tiles — which paint themselves in
`do_snapshot` and have no child labels at all — were a blank rectangle to
it. Making the tiles focusable instead would hand arrow keys to GTK's own
focus movement, which is precisely the machinery `core/focus.py` exists to
replace. So each tile gets role BUTTON, a name, a description and a live
SELECTED state, each row gets role ROW and its heading as a name, and the
container publishes ACTIVE_DESCENDANT — the standard pattern for a
composite widget that keeps the keyboard focus and moves a cursor inside
itself. The apps grid and the search results do the same.

**Verified through AT-SPI, not by reading the code.** Walking the live
accessibility tree of the running app shows the rows named, every tile named
under them, the top bar as a labelled toolbar whose glyphs read "Wi-Fi:
SFR_936F" and "Battery 61%", and exactly one tile carrying SELECTED —
which follows the cursor through UP/UP/RIGHT/RIGHT/DOWN/LEFT. What has
*not* been done is running Orca against it: no `active-descendant-changed`
event was observable from a listener process here even with
`toolkit-accessibility` on, so whether Orca speaks each tile as the cursor
moves is still unverified. The tree it would read is correct.

**GTK collects an accessible tristate as a plain int.** Passing
`Gtk.AccessibleTristate.TRUE` to `update_state` boxes a GValue of the enum's
own type; GTK asserts `G_VALUE_HOLDS_INT`, warns, and drops the update — so
the state silently never lands. `int(...)` is required. Worth writing down
because the failure is a warning on stderr and an accessibility tree that
looks fine until something reads it.

## 2026-08-19 — Two geometry bugs in the all-apps grid

**A `Gtk.Fixed` scroll viewport must not report its content's height.**
The grid stopped scrolling: DOWN moved the selection into rows allocated
off the bottom of the window. The viewport is a `Gtk.Fixed`, which measures
to fit its children, so with fifty applications in it the viewport asked to
be 2012px tall on a 1080px screen — and, being an overlay child, was given
exactly that. `_scroll_to_focused` then compared each focused row against a
"viewport height" of 2012 and correctly concluded that nothing was ever
off-screen. `SizeReporter` grew a `propagate_minimum=False` mode that
reports a zero minimum and lets the parent decide the size. The same latent
bug was in the search results and in both settings lists — the tile
editor's installed-app picker is fifty rows, and everything past the first
screenful was unreachable there too. One flaw, three screens, one fix.

**Edge tiles need a bleed of padding inside the clip, not zero.** Every
tile widget is `bleed` (56du) larger than its card on all four sides, and
that transparent margin is where the focus bloom and the scale-up are
drawn. The grid placed the first row and column at `-bleed`, which put the
card flush with the viewport's corner and its glow *outside* it, where the
clip sheared off the top and left of the hover lighting — the reported
symptom. Cards are now inset by one bleed on every side, the content bounds
and the scroll clamp both include it (otherwise the last row's bloom is cut
at the bottom instead), and the viewport spans the full window width so the
only horizontal clip is the screen edge, which is exactly what the home
rows already do. Where the bleed is wider than the safe area — 56du against
54du at the reference size — the card starts at the bleed, two pixels right
of the title above it, rather than clipping two pixels of glow.

**The search results keep their left clip on purpose.** Same top-edge fix
there, but not the horizontal one: the left edge of that viewport is the
boundary with the on-screen keyboard, three columns already fill the pane,
and glow spilling over the keys is worse than glow that stops at them.

## 2026-08-19 — What a first release actually needed

**GPL-3.0-or-later, and an SPDX line rather than a copyright block.** The
project had no licence at all, which is not a neutral state: it means nobody
may legally use, fork or package it, and Flathub rejects a submission
outright. GPL-3 matches the GNOME applications Salon sits beside and links
against. One SPDX identifier per file rather than a header paragraph, so the
licence travels with a file that gets moved and the header stays one line.

**The tree became eleven milestone commits, not one.** Eighty-seven
uncommitted paths had accumulated — the entire application below the
original proof-of-concept. Grouped by milestone because that is the only
grouping that explains *why* a file exists; a subsystem split would cut
across every feature, and one "backfill" commit would say nothing at all.
The commits are snapshots of a tree built out of order, so an intermediate
one does not necessarily build: that is inherent in backfilling, and worth
less than the history being readable.

**Metadata is validated by the build, not at submission time.**
`appstreamcli validate` and `desktop-file-validate` run as `meson test`, and
`check.sh` now runs `meson test`. A wrong AppStream tag otherwise surfaces
when someone tries to publish, which is the worst moment to learn it. Two
things are deliberately missing from the metainfo — screenshots need
absolute URLs and there is no public repository yet, and the homepage claims
the domain the app id already asserts. Both are flagged in comments in the
file rather than filled with plausible-looking lies.

**The pairing code is now rate-limited, because four digits is not a
secret.** `compare_digest` defeats a timing oracle; it does nothing about a
loop over ten thousand possibilities, which any script on the same network
finishes in seconds, and the prize is typing into a search box that launches
applications. Five wrong codes burn the session — including for the right
code, so guessing it on the last allowed attempt wins nothing — and the only
way back is closing and reopening search, which mints a new one. The
television says so, since otherwise the phone has silently stopped working
and nothing on screen explains it. Driven over real HTTP in
`tests/test_pairing.py`, because what is being asserted is what a request
from the network gets back.

**Logging exists because the restart hides the crash.** Salon is a
`RequiredComponent` of its own gnome-session, so a crash is followed
immediately by a restart: the screen blinks and there is nothing to look at
afterwards, and no terminal in the room was watching. Two sinks — stderr for
the journal, and a rotated file under `$XDG_STATE_HOME` because a set-top
box may keep the journal in volatile storage. `sys.excepthook`,
`threading.excepthook` and GLib's writer all route through it; an exception
escaping into a GTK callback otherwise prints a traceback nobody sees and is
swallowed by the main loop. Unhandled exceptions are logged and the process
is left running — taking the whole television down because an artwork thread
raised would be the worse failure. Everything below WARNING from GLib is
dropped unless `SALON_DEBUG` is set: a custom writer bypasses
`G_MESSAGES_DEBUG` filtering, and the first version filled the log with the
Vulkan loader enumerating physical devices four times per startup, which
would have rotated away the one thing the file exists to keep.

## 2026-08-19 — A stick at rest is not at zero

The first controller ever attached to this project was a DualSense, and the
useful finding needed no button presses at all: with the pad face down on
the table, libmanette reports Y deflections of +0.079..+0.150 on both sticks
— mean +0.142 left, +0.111 right — at around sixty events a second, forever.

The right-stick dead zone was 0.15. That is a margin of sixteen thousandths
against a pointer that drifts downwards while nobody is holding the
controller, on the one input path where drift is not a cosmetic problem:
gamepad pointer control exists to click things inside Netflix. It is 0.25
now.

Widening a dead zone normally costs slow-speed control, because the old code
passed the raw value through once it cleared the threshold — so the slowest
speed available was the dead zone itself, and the cursor jumped from
stationary to a quarter speed. `actions.stick_deflection` rescales the
remaining range back to 0..1, so motion starts from nothing at the edge and
reaches full speed at full deflection. It's pure and in `actions.py` rather
than in the gi-bound `gamepad.py`, so the numbers above are asserted in
`tests/test_actions.py` as regression cases: every one of those resting
readings must produce exactly 0.0.

The left stick's 0.35 quantisation dead zone was already safe against this
(0.15 max observed), which is why nothing had ever misbehaved on the
directional path.

## 2026-08-19 (release preparation)

**The application id is `io.github.alexydaher.Salon`, not `rocks.salon.Salon`.**
An AppStream id has to be something its author demonstrably controls, and
Flathub checks it: either a domain, or a code-hosting account. `salon.rocks`
was never registered, so the old id asserted something untrue and would have
been rejected at submission. The GitHub form needs no registrar. Rejected:
registering the domain to keep the prettier id — it costs money annually to
hold a claim the project doesn't otherwise need, and the id can move to a
domain later if one is ever bought. Note this orphans settings already on
disk under `/rocks/salon/Salon/`, including the RemoteDesktop restore token;
`dconf dump` piped into `dconf load` at the new path moves them.

**The gnome-session `RequiredComponents=` key did nothing, and the session
mode had never been run.** The `.session` file said the Shell and Salon were
required components, and both the README and `logs.py` stated as fact that
this is what restarts Salon when it exits. It isn't. gnome-session 50 does
not act on that key — it isn't in `gnome-session(1)` at all any more, where
SESSION DEFINITION now lists only `Name` and `Kiosk`, and the page says
plainly that a session definition "doesn't do anything on their own" and must
be accompanied by systemd configuration. The shipped `ubuntu.session` is two
lines, `Name=Ubuntu`, with all the wiring in
`gnome-session@ubuntu.target.d/ubuntu.session.conf`. So Salon's session entry
would have started a session containing nothing, and the restart behaviour
that the whole "television, not a desktop" claim rests on did not exist.

Fixed by shipping what actually works: a drop-in on `gnome-session@salon.target`
naming `gnome-session-services.target`, `org.gnome.Shell@user.service` and
Salon's own unit, plus `io.github.alexydaher.Salon.service` carrying
`Restart=always`. The restart is now a real, inspectable policy rather than a
property assumed of a key. `StartLimitBurst=5` in thirty seconds bounds it:
an app that cannot start at all should return the user to the login screen,
not spin forever behind a black screen. `org.gnome.Shell@user.service` rather
than `@ubuntu` because `user` is gnome-shell's built-in default mode and
exists everywhere. Installed to `datadir/systemd/user`, which is on systemd's
user unit search path under both `--prefix=/usr` and `--prefix=$HOME/.local`.

**The session definition is `Kiosk=true`.** It is gnome-session's own term for
a session built around starting one specific app, which is exactly this, and
it stops `~/.config/autostart` being replayed into a television. It also
resolves a collision that would otherwise be a real bug: Settings' "Start
Salon at login" writes an autostart entry, so without `Kiosk=true`, logging
into the Salon session with that toggle on would have started Salon twice.

**Salon suppresses the idle screen lock, but only when it is the session.**
GNOME blanks after five minutes and locks when it blanks. In a living room
that is a dead end — the screen returns showing a password field, and neither
a gamepad nor a CEC remote can type one, so the set is bricked until someone
fetches a keyboard. `services/screenlock.py` sets
`org.gnome.desktop.screensaver lock-enabled` false while Salon runs and
restores it on shutdown. Blanking is deliberately left alone: the panel and
the power bill both want the screen to go dark, and only the *lock* is the
trap. Rejected: inhibiting idle entirely (leaves a static bright image on an
OLED indefinitely), and a gschema override (changes the default system-wide,
including for the user's ordinary desktop session). The guard is
`core/session.py`, pure and tested, and it is deliberately strict: a false
positive means silently unlocking somebody's laptop because they opened Salon
from Show Applications, which is far worse than a false negative.

**The Flatpak manifest is tag-only, with no `commit:`.** Flathub wants a git
source pinned to a hash as well as a tag, but this manifest lives inside the
repository it builds and no commit can contain its own hash. That is what the
separate `flathub/<app-id>` repository is for; the in-tree manifest stays
tag-only, for building from a clean checkout.

## 2026-08-22 — the phone becomes a second screen

**The QR code carries a 128-bit session token in the URL *fragment*, and
the four-digit code is demoted to a bootstrap credential.** Scanning the
code on the television used to open the page and then ask for four digits,
which made the camera a shortcut for typing an IP address and nothing more.
Now `services/pairing.py` mints a token alongside the code; `pair_url`
appends it as `#k=…`; the page reads it out of `location.hash`, posts it to
`/connect`, and strips it from the address bar. A fragment is never sent to
a server, so the secret lands in no access log, no `Referer`, and no
proxy's history — which makes scanning not merely more convenient than
typing but the *stronger* of the two paths. The code is now accepted at
`/connect` and nowhere else, so the brute-force lockout guards exactly one
endpoint. Rejected: keeping the code as the only credential (ten thousand
possibilities is why the lockout had to exist at all), and putting the
token in the query string (same secret, but in every log that sees the
request line). **Wrong tokens are deliberately not counted toward the
lockout.** Counting them would trade an attack that cannot succeed — 128
bits is not guessable — for one that trivially can: anyone who can reach
the port could lock out the phone that is legitimately paired.

**`GET /state` is a 1 Hz poll with a version counter, not Server-Sent
Events.** The phone needs to *see* the television — the catalogue, the
cursor, what is playing — and something has to push that across. libsoup3
can stream a response by pausing the message and appending to the body by
hand, but it is fiddly, and at the rate a human glances at a remote a
one-second poll is indistinguishable from a live feed. The cost that
actually mattered was different: `Soup.Server` dispatches on the main loop,
so every byte serialised for the phone is serialised on the thread
animating the tiles. `core/remote.StateFeed` answers that — publishing
compares a frozen dataclass and does nothing when it matches, the JSON is
built lazily on first request and cached, and a phone that is already
current gets a 204 with no body. A state that is superseded before anyone
asks is never serialised at all.

**`_handle_action` is a wrapper around `_dispatch_action`.** The phone's
snapshot has to be refreshed after anything that could change what is on
screen, and `_dispatch_action` has two dozen early returns. Adding a
publish to each would have meant forgetting one, and the symptom — a phone
showing the wrong screen with no clue why — is invisible from the
television. One wrapper, one call site.

**`/launch` and `/art` resolve ids against the *published state*, not the
catalogue.** The phone is a second remote, not a second way in: it can
reach what it was shown and nothing else. That also means there is no path
to traverse — the id is a set membership test, never joined onto a
filename.

**The remote refuses requests from outside the local network.** It is
plaintext HTTP by design (TLS means a self-signed certificate, which means
a browser interstitial, which destroys the one-scan path the whole thing is
built around). That trade is only defensible while "on the same network"
means something, so `core/remote.is_local_address` checks the source before
the credential is read. The ranges are written out rather than deferred to
`ipaddress.is_private`, which does not mean what its name suggests: it
counts the documentation ranges as private and leaves out RFC 6598
carrier-grade NAT, which some ISP-supplied routers really do hand to
devices on their own LAN.

**"Connect a phone" is in the system menu, and the pairing screen closes
itself when a phone arrives.** The remote was reachable from Settings →
Input and from the search keyboard — both places you go for a reason, which
made the best input Salon has something you had to already know about. MENU
is the one button that works from anywhere. Closing the screen does *not*
stop the remote (you connect a phone once and then use it), and it gets out
of the way ~1.6s after the first authenticated request, because a card
still sitting there would swallow the phone's first press at the exact
moment the phone started working.

**Track skip is `/transport`, not an `Action`.** `Action` is how you drive
Salon, and every source normalises to it. Skipping a track is the one thing
the phone can do that a controller cannot, because it is only meaningful
when you can see what is playing — so it is its own endpoint calling
`services/mpris.py` directly, rather than two new buttons in a vocabulary
no physical remote here has.

**The page is a file in the GResource bundle, not a Python string.** It was
a 200-line `"""` literal, which is why its connect regex needed `\\d` —
one backslash from a bug no editor would highlight. It is now
`data/remote/index.html`, four panes, a poller and a gesture surface, and
it stays one file with no build step: a launcher that needs npm to change a
button is a launcher nobody will change a button in.

**Two bugs the screenshots found that the reasoning did not.** First, the
QR code rendered at a *half-pixel* origin: `ui/qrcode.py` floored the
module size but not the offset, every module edge picked up a grey
antialiased column, and libzbar refused the symbol outright — a code that
looked perfect and read as nothing. Second, the page's header and tab strip
are `display: flex`, which beats the user agent's `[hidden] { display:
none }`, so the chrome of a connected remote showed through the code
screen. Both were obvious in the first capture and invisible in the source.
Per CLAUDE.md: do not guess at layout.

**Application icons are sent with `fit: "contain"`.** The television draws
a 64px icon small and centred on a gradient built from its own colour
rather than cropping it to fill a 16:9 card (`Artwork.icon_texture` is
separate from `texture` for exactly this reason). The first phone capture
was a wall of blurry stretched rectangles; the distinction is now in the
payload rather than re-derived on the phone.

**Turning the phone remote on takes the RemoteDesktop pointer session.**
That session was previously taken only when the catalogue contained a
browser tile — a test about the *gamepad* stick, which exists to aim at a
web page. A phone trackpad is useful over anything, including Salon itself.
Still gated on the same `gamepad-pointer` setting, which is the user saying
whether Salon may move the system pointer at all, and `/pointer` now
answers 409 with an explanation when the grant is missing rather than
returning 200 to a finger sliding on a dead surface.

**"Connect a phone" moved to the top bar, and out of the search keyboard.**
There were three ways to start the phone remote — Settings → Input, a "Use
phone to type" button on the search keyboard, and (as of earlier today) the
system menu. Three switches for one thing, and the two people would find
were the two that framed it as a keyboard. It is now a button in the status
bar's focus row, beside Search and All apps and before Power, which is
where the other whole-screen destinations already are. `KeyboardPane` keeps
the part that was always the point: while it is on screen it *claims the
text sink*, on map rather than on a button, so connecting the phone from the
top bar and then opening search needs nothing else pressed. The release goes
through the new `PairingServer.release_text_sink`, which only clears the
slot if that pane still holds it — GTK maps the incoming screen before it
unmaps the outgoing one, so an unconditional clear would have left the phone
typing into nothing on the screen that had just arrived.

## 2026-08-22 (later) — four things the phone got wrong

**The trackpad was working; the cursor was not.** Measured before touching
anything: injecting motion through the portal and reading the pointer
position back off the surface showed it moving 300px and returning. What
did not happen was any of it being *visible*. Salon hides the cursor until a
real mouse moves, and the reveal hangs off GTK motion events — which
portal-injected motion does not reliably produce over Salon's own window
(30 injected motions, zero events). So the phone dragged something
invisible, and hover-to-focus, which is gated on the same flag, was off too.
`_on_phone_pointer` now says `_set_pointer_visible(True)` explicitly, the
way the gamepad path always has. The lesson is the general one: a
capability test (`_pointer.ready`) is not a working-feature test.

**The phone keyboard now types into other applications.** `/type` delivered
into `_text_sink`, which is always a *Salon* widget, so the moment a browser
tile was in front the keyboard answered 409 — failing at exactly the point
where a phone keyboard is the only thing that can help, because a search box
inside Chrome is the one text field on a television that Salon cannot draw.
The grant was already there: `SelectDevices` has always asked for
`POINTER | KEYBOARD` and only the pointer half was used. `type_text` taps
keysyms through the same session; Salon's own field still wins when one is
on screen, and the 409 that remains names the setting that would fix it.
Two things are deliberate. Keys are spaced ~12ms apart rather than blasted,
because a web page doing its own key handling with a debounce is the target.
And the character→keysym mapping **delegates to `Gdk.unicode_to_keyval`**
rather than computing `0x01000000 + codepoint`: that rule is the one
everybody reaches for and it is wrong in the middle, because several
characters above Latin-1 have legacy named keysyms the keymap is indexed by.
The hand-rolled version passed review and failed its first test.

**The token is stored on the phone.** The page strips it from the address
bar so it stays out of history — and then had nowhere to keep it, so any
reload dropped to the code screen: a discarded background tab, a
pull-to-refresh, a relaunch from the home screen. That is the whole of
"it doesn't stay connected after opening an app". It goes in `localStorage`
now, which is not a weakening: it is the phone's own remote, and anyone who
can read that phone's storage can already read the television it was
scanned from. A fragment still wins over the stored copy, so scanning a
fresh code is how a stale token is replaced.

**A held session no longer times out.** Five minutes of inactivity stopped
the server — and `stop()` clears the holders, so a remote the user had
deliberately switched on switched *itself* off, port closed, Settings
showing "off". The phone stops polling when its screen is off, so this fired
reliably about five minutes into anything worth watching. The timeout was
written when this was a keyboard summoned for one URL; a mode the user turns
on is a mode the user turns off. Unheld sessions still expire, so the
protection that rule existed for is intact.

**And the phone can now tell the two failures apart.** "Could not reach
Salon" was a red dot and a toast for both "your phone was asleep" and "the
television is off". There is a banner that says which, a Retry button, and
the poll backs off 1s → 30s while nothing answers rather than making a
request a second all night.

**The phone's Menu button really is a way back out, and the header that
said where you were was lying.** Verified by launching a real application
from Salon, waiting for it to take focus, and pressing Menu on the phone:
the child was terminated within a second and the compositor handed focus
back. That path works for the phone for the same structural reason it works
for a gamepad and not for a keyboard — the press arrives over HTTP into
Salon's own process, so it does not need Salon to have keyboard focus.

What that test found was that `screen` in the published state was always one
event behind: the launcher's transitions (`_on_launch_started`,
`_on_child_focused`, `_on_returned`, `_on_launch_timed_out`) never
published, and they all arrive asynchronously, long after the button press
that `_handle_action` publishes for. So the phone said "home" while an
application was on the television and "Calculator" once you were back on the
home screen — exactly inverted, on the one line that answers "where am I".
`_current_screen` was also testing only `_child_active`, which a *browser*
tile never sets (it sets `_pointer_mode` instead), so a Netflix tile read as
"home" throughout.

And the toast naming the way out now names the hardware that is actually
connected: "Press START on the controller, or Menu on your phone," when a
phone is talking to us. Telling someone holding a phone to press a button on
a controller they may not own is the difference between a way out and a
trapped television.

## 2026-08-23 — the phone's cursor, and a grant that said yes too early

**A press on the phone hides the mouse, because every other input source
already did.** `_on_key_pressed`, `_on_cec_action` and `_on_gamepad_action`
all call `_set_pointer_visible(False)` before dispatching; `_on_phone_action`
was the one that never did. The consequence is not cosmetic: the flag also
gates hover-to-focus, so a mouse left parked anywhere over the grid kept
stealing the selection back the moment a row scrolled under it — the phone
would move the cursor down and the stationary mouse would drag it
somewhere else. Tapping a tile in the phone's Apps pane hides it too, for
the same reason it already moved the television's cursor: the phone is
driving, so the mouse is not. The trackpad brings the pointer straight back,
which was already true and is what makes the pair legible.

Pointer mode is the exception, exactly as it is for the gamepad — there the
cursor *is* the interface, so both handlers pass `self._pointer_mode` rather
than a bare `False`.

**`PointerInjector.ready` was answering the wrong question.** It returned
`self._session_handle is not None`, and the portal hands that handle back at
*CreateSession* — three round trips and possibly a consent dialog before
`Start` says yes. So through that entire window Salon believed it could
inject: `remote_input=True` went out to the phone, whose keyboard tab then
said "typing goes to whatever is open on the television" and whose trackpad
said "drag to move the pointer"; `/type` and `/pointer` answered 200; and
mutter dropped every keysym and every motion, because a session that has not
been started is not a session. A grant still being asked for is not a grant.
`ready` is now `handle is not None and started`, `move`/`click`/`type_text`
gate on it rather than on the handle, and `_fail` clears it. Measured on the
live session: `ready` is False the instant the remote is switched on and
True four seconds later, with the published `remoteInput` following it.

**What typing into a launched application actually does.** The question was
whether the phone's Type tab can reach Spotify or Prime Video. It can, and
this was measured rather than reasoned about, twice: once against an
ordinary GTK client launched as a child from Salon (a `Gtk.Entry` reporting
its own contents — all nineteen characters arrived intact, at key gaps of
12, 30, 60 and 100 ms, and Enter activated the field), and once against the
Prime-Video-shaped path, a URL tile opened in Chrome with an autofocused
input that posted what it received back to the probe. Both received exactly
what was sent.

So the mechanism is sound and the failure is elsewhere: the keys go to
whatever *that application* has focused, and an application that has just
opened has focused nothing. Typing then works perfectly and shows nothing,
which is indistinguishable from broken. There is no fix available from
Salon's side — no client may ask another where its text cursor is — so the
hint under the Type tab now says the actual procedure: tap the app's search
box with the Pad first, and the keys land wherever that app is focused.

## 2026-08-23 (later) — the phone's screen, and what a LAN address costs

**The remote is not going to become a separate app, and a PWA is not
available to it.** The page already carries a web manifest, `standalone`
display, an icon and the Apple meta tags, so "make it installable" looked
like a small amount of remaining work. It is not work at all — it is
blocked. Measured in Chrome at this machine's LAN address, which is what
the QR carries:

| | `http://192.168.1.151` | `http://127.0.0.1` |
|---|---|---|
| `isSecureContext` | false | true |
| `serviceWorker` | absent | present |
| `wakeLock` | absent | present |
| `vibrate` | present | present |

No secure context means no service worker, which means Chrome will never
offer to install it, whatever the manifest says. And there is no
certificate to be had: no public authority issues for a private address or
a `.local` name, and a self-signed one puts a full-page warning in front of
a guest who has just scanned a QR code — strictly worse than what exists.

A *native* app would clear all of that, and would also bring lock-screen
transport controls, the hardware volume keys, and TLS with a pinned
certificate (which would close the plaintext-keyboard gap). It was still
refused, for a reason that has nothing to do with effort: **the current
design has no version skew.** The phone downloads its whole interface from
the exact television it is talking to, so Salon 0.2 is always talking to a
0.2 remote. Ship an installed client and every endpoint becomes a
compatibility surface, permanently, for one maintainer. The second reason
is guests: scan and you are holding the remote, with no store, no install
and no account, and on a television the second user is the main user.

**`keepAwake()` was dead code, and the measurement above is what found
it.** It guarded on `"wakeLock" in navigator`, which is false at every
address a phone can reach, so it returned immediately and the phone dimmed
mid-film. It now falls back to playing a muted one-second black loop
(`data/remote/awake.webm`, `awake.mp4`, served from the GResource bundle),
which is what every library that solves this does. The real API is still
tried first — it is the only one of the two the operating system knows
about, and it would exist if this were ever served over HTTPS.

Three details that are not incidental. The element is 1px and 1% opaque
rather than `display: none`, `visibility: hidden` or `opacity: 0`: all
three are ways of telling the browser the video need not be played, which
is the one thing being asked of it. Two containers, because Safari wants
H.264 and VP8 has been on Android longer. And it is paused on
`visibilitychange`, because a video looping in a pocket is a battery cost
for nothing.

Verified against the real page loaded from a running Salon at the LAN
address, in Chrome at an iPhone viewport: `isSecureContext` false,
`wakeLock` absent, `#awake` playing and looping off `/awake.webm`,
`readyState` 4, both clips served with the right types. What could *not* be
exercised is the no-gesture refusal path: muted autoplay is permitted by
Chrome's policy regardless of the `--autoplay-policy` flag, so the
retry-on-first-tap handler is belt and braces that has never been reached.
And whether a playing video genuinely holds a *phone's* screen on is still
untested here, because that needs a phone.

**Add to Home Screen already works on iOS** and always did —
`apple-mobile-web-app-capable` is in the page, and Safari asks nothing else
of a page to give it a standalone icon. Nobody knew, because it was
nowhere in the README. It is now, along with why Android will not offer the
same thing.

## 2026-08-23 (later still) — the hardware pass, and what it could not reach

The human tested the session, the power actions, the phone remote and the
controller against the build at `22141c6`, and reports all of them working.
CEC is now the only thing on the list that has never met a device.

That is worth writing down carefully, because it is a *report* and most of
this file is measurement. Where the report is coarser than the claim, the
claim stays narrow:

**The session comes up.** Picking Salon at the login screen starts the
Shell and Salon. This was the highest-value untested item in the project
and it is closed. What nobody watched is `Restart=always` doing its job
after a crash, or the bounded start limit tripping — those need a
deliberate kill, not a login.

**The power actions work, and that is exactly why the interesting half is
still untested.** `Suspend`/`Reboot`/`PowerOff` reach logind and do what
they say. The path this file has flagged for weeks — a polkit denial
arriving back as a message on screen rather than vanishing silently — is
*unreachable from an account permitted to power the machine off*. Testing
it needs a deliberately unprivileged user, and until then the branch is
written but unexercised. Success here did not close the item; it explained
why the item cannot close.

**The controller mapping is confirmed in use** rather than only reasoned
about: Cross→OK, Circle→BACK, Square→OPTIONS, Triangle→SEARCH,
Options→MENU. Still one pad, still a DualSense.

**The phone remote met a real phone**, on a build that already carried the
muted-video screen-awake fallback written earlier the same day. So touch,
haptics and Add to Home Screen have all had a thumb on them. What is still
not *measured* is how long a phone screen actually stays lit — nobody timed
it against a film, and a report that the remote "worked" does not
distinguish a wake fallback that holds for two hours from one that holds
for two minutes. Left open deliberately rather than rounded up.

## 2026-08-23 (later still) — what Flathub's linter is right about, and what it isn't

`flatpak-builder-lint manifest` reported nine errors against the manifest.
Four were real mistakes, and the five that remain are staying, each with a
paragraph in the manifest header written for the submission PR to quote.

**The four that were simply wrong.** Three `--filesystem=xdg-*/salon:create`
grants: a sandboxed app already owns its own XDG directories, so those only
bought the ability to write to the *host's* `~/.config/salon` and share
`tiles.json` with an unsandboxed Salon — which is not what a Flatpak is
for. And `--talk-name=org.freedesktop.portal.Desktop` plus
`--talk-name=org.freedesktop.portal.Flatpak`: portals are always reachable
from inside a sandbox and never need a talk-name. The second of those
carried the comment "Volume via wpctl", which was wrong twice over — that
bus name is the spawn portal, not PipeWire, and `wpctl` is a host binary
reached through `flatpak-spawn`, which the `org.freedesktop.Flatpak` grant
already covers. libmanette is now pinned to the commit behind tag 0.2.9
(`508df23`, the commit the annotated tag points at, not the tag object).

**The dconf complaint is right in general and wrong here, and it took
reading the code to find out why.** The manifest claimed the grant was for
"the system's reduced-motion preference and the on-screen keyboard". The
first half is false: reduced motion comes from Salon's own schema plus
`Gtk.Settings:gtk-enable-animations`, which GTK already feeds from the
Settings portal inside a sandbox. Nothing reads a host reduced-motion key.

What actually needs it is two keys, and *both are writes*:

    org.gnome.desktop.screensaver  lock-enabled            screenlock.py
    org.gnome.desktop.a11y.applications
                                   screen-keyboard-enabled pointer_injector.py

`org.freedesktop.portal.Settings` serves reads and only reads. There is no
portal that writes a host setting, by design. So dropping the grant does
not fail loudly — both features become silent no-ops against the sandbox's
own dconf database. The screen lock one is the appliance-breaking one, and
it was not even mentioned in the old comment: a television that locks to a
password prompt is a television nobody on a sofa can unlock. Keeping a
permission and justifying it beats shipping a Flatpak that looks like a
television and locks like a laptop.

**`org.gnome.SessionManager` cannot replace logind.** This looked like the
easy win and is not available at all. It has no `Suspend` method, so that
grant would have to stay regardless and the linter would still fire — all
cost, no benefit. It collapses `CanReboot` and `CanPowerOff` into a single
`CanShutdown`. And its `Shutdown()` and `Reboot()` raise GNOME's own
confirmation dialog, which under a fullscreen kiosk is a prompt nobody can
see — precisely the failure `power.py`'s error reporting was written to fix
("a polkit prompt the user can't see because Salon is fullscreen over it").

**Wayland-only stays.** Adding `--socket=fallback-x11` to quiet
`finish-args-only-wayland` would produce something that starts, looks
right, and then behaves wrongly wherever the RemoteDesktop grant and
Wayland focus semantics are load-bearing. Refusing to run is the honest
outcome.

**One crash found on the way past.** `set_onscreen_keyboard_enabled` called
`Gio.Settings.new` on `org.gnome.desktop.a11y.applications` with no guard,
and that is not an exception — a missing schema is a `g_error`, which
aborts the process. On a desktop without gsettings-desktop-schemas, Salon
died on the first press of Y in pointer mode. It now looks the schema up
first and says so, the way `screenlock.py` already did for its own host
key. Inside the Flatpak the schema always exists, so this was only ever
reachable from a Meson install on a non-GNOME desktop — which is exactly
the configuration nobody here runs.

## 2026-08-23 (evening) — one press, one thing

**No controller worked, and no gate said so.** `d2bab02` added
`set_bindings()` and `_resolve()` to `GamepadSource` and put them *inside*
`__init__`, between the last assignment and the device-monitor setup.
Everything from `self._axis_state = …` down — creating `Manette.Monitor`,
enumerating the pads already plugged in, connecting the three signal
handlers, arming the right-stick poll — became unreachable code after a
`return`. The object constructed fine, raised nothing and did nothing.
Ruff has no rule for it and mypy's `warn_unreachable` is off by default, so
355 passing tests and a green CI had exactly as much to say about it as
they would have about a comment. `warn_unreachable = true` is on now, and
it flags the original line; reverting `gamepad.py` under the new setting
reproduces the error, which is the only way to know a gate works. The
milestone list called the gamepad "done, mapping confirmed", and it was —
on 2026-08-19, four days before the commit that silently switched it off.
Verified after the fix against the DualSense that is attached: libmanette
enumerates it, 1284 axis events arrive in eight seconds from the resting
stick alone, and `GamepadSource` turns presses into `Action`s again.

**MENU asks the launcher whether a child exists, not the UI's own flags.**
`_child_active` and `_pointer_mode` are set from `on_child_focused`, which
fires on Salon's window going *inactive*. A window that is already inactive
cannot go inactive, so when a launch starts from behind another app the
edge is never generated and both flags stay False — at which point MENU
fell through to opening the system menu underneath the running app, where
it is invisible and swallows the following press to close itself again.
That is the "MENU works every other time" everyone was seeing, and the
phone is what made it common, because the phone is the only remote that can
open a tile while an app is already covering the television.
`LauncherService.has_child` is true across both phases and is now the third
thing MENU checks.

**Launching over a running app closes it first.** Same cause, worse effect:
`launch()` overwrote `_subprocess` with the new child, so the old app was
still on screen with nothing tracking it at all — MENU would then close the
*new* one and leave the old one unreachable forever. `_launch_tile` now
queues the tile, returns from the current child, and starts the new one
250ms after the return, which gives the compositor time to hand focus back
so the next launch's detection edge exists.

**A closing `.desktop` child is watched for actually going.** There is no
`Gio.Subprocess` on that path, so the only other signal is the window
activity that had already been missed. Measured with a real child: MENU
closed the app, the launcher stayed convinced it was out there, and it took
a second press to get anywhere. The pid is polled every 400ms after
SIGTERM, and `close_child()` returning False now calls `abandon()` so a
wrapper pid Salon never had a handle on cannot pin the state machine open.

**The 12s launch timeout resolves instead of just complaining.** If Salon
still has focus, nothing is covering it — the app is slow or dead, the
overlay says so and BACK gives up, unchanged. If Salon does *not* have
focus, something is plainly in front and the edge was simply never
generated, so the launch is treated as arrived. Waiting longer could not
have helped, and the alternative was a launcher that never armed its return
detection at all.

**SEARCH, POWER and PLAY_PAUSE moved below the "an app is in front" guard.**
Flagged as measured-but-unfixed on 2026-08-22 and fixed here, because
PLAY_PAUSE is the one that broke MENU: with nothing playing it falls
through to launching the focused tile, which is how a phone with a paused
player opened GeForce NOW behind the app already running. Volume and mute
stay above the guard — they act on the system's audio, not on a window, and
turning the television down while watching something is the single most
obvious thing a remote should do. In pointer mode SEARCH still toggles
GNOME's on-screen keyboard, which was always deliberate.

**Bluetooth devices can be forgotten, and a paired one opens a panel.**
`BluetoothService.forget` had existed since the panel was written and
nothing ever called it, so a television accumulated pairings and could not
shed them: seven on this machine, one of them connected, most of them
neither present nor wanted. Forgetting is also the only repair for a
pairing that has gone bad, since BlueZ will not re-pair a device it thinks
it already knows. An unpaired row still pairs on OK — one useful action
does not need a menu — while a paired one opens Connect/Disconnect/Forget,
with the same confirmation screen tile deletion uses. That helper moved
from `tiles.py` to `context.py`: deleting a row, deleting a tile and
unpairing a device are the same question, and a confirmation that looks
different each time teaches nobody where Cancel is.

**Panels can be told when they leave.** `Panel.on_leave` exists because
`_bluetooth_panel`'s own docstring claimed discovery "stops when the panel
closes" and `stop_discovery` had no callers anywhere in the tree — the
adapter scanned until Salon exited, which costs power and keeps the radio
busy while a paired controller is trying to use it. Verified by reading
`org.bluez.Adapter1.Discovering` across the transition: True with the panel
open, False after Settings closes.

## 2026-08-23 (night) — the phone stops being a keyboard with buttons

Six changes, all from one observation: the page looked identical whether the
television was on its home screen or three levels into Netflix, even though
what the buttons *do* changes completely.

**The page reshapes itself around `state.app`.** `screen` already carried
the same string, but as one of six reserved words — the page cannot tell "an
app called Settings is in front" from "the Settings screen is open" without
a separate field, and it now hides half its own controls on the answer. With
an application up, the D-pad, OK, Back, Search, Options and the group keys
are greyed with one line saying why, "Close *Netflix*" becomes the prominent
action, and the pane switches to the trackpad *once*, on the transition,
from a pane that has just gone useless. Volume and Play/Pause stay live and
now visibly so: they act on the system's audio and on MPRIS, not on a window.
Rejected: hiding the dead controls. A remote that is a different shape every
time you glance down teaches nothing; one that is visibly unavailable
teaches the rule.

**Search lives in the Apps pane, not behind a fifth tab.** What you are
looking for is an application and that is the pane with the applications in
it. It searches every *installed* app as well as the catalogue, which closes
the "11 tiles against 53 installed" gap without the `show-apps-row`
workaround that also changes the television. `core/ranking.rank_best` is now
shared with `ui/search.py` — the same dedupe-and-cap loop had been written
out at both call sites, and two search surfaces that ordered results
differently would be two things to learn.

**`/search` answers synchronously, on the main loop.** Soup dispatches
there, which is where the catalogue and the installed-app cache already
live, so the handler can simply ask: no thread, no request id, no second
round trip. The price is that the callback must stay cheap, which is why the
installed-app scan happens once when the remote starts rather than per
query — scanning every `.desktop` file inside a keystroke handler would
stall the frame clock on the television while somebody types on a phone.

**`core/remote.OfferedIds` widens "what the phone may reach" from "what is
on the television" to "what it has been shown".** A search result is
deliberately not published — putting a transient result list into the state
snapshot would bump the version on every keystroke — so the ids are recorded
as they are served. Bounded at 400, oldest out first, because it is fed from
a network endpoint and the alternative is a memory leak with a user
interface. `/launch` and `/art` both go through the one `_may_touch` check,
so there is still nothing anywhere in that file that joins an id onto a path.

**`/art` resolves search results too.** It looked only in the catalogue, so
every installed application in a result list advertised artwork the server
then 404ed, and the card fell back to a coloured letter after a wasted
request. Found by looking at a screenshot of the real page, not by reading
the code — the API response said `art: true` and the picture said otherwise.

**Volume is a slider, and absolute.** Two repeat-buttons still send
VOLUME_UP and VOLUME_DOWN as ordinary Actions; this is the other thing. A
finger dragged a third of the way along is asking for a third of the way
along, and expressing that as nineteen step presses is how a volume control
ends up lagging behind the thumb moving it. Throttled to one request per
60ms, and the television's value is not written back into the slider while a
thumb is on it — that is what makes a remote slider fight the finger holding
it. Every existing volume path was rerouted through `_on_volume_read` so a
press on the television moves the slider in someone's hand.

**A long press on a tile opens the per-tile menu.** `Action.OPTIONS` has
reached the same set on the television since the reachability pass, and the
phone — the one surface that shows every tile at once — was the one where
none of them could be changed. Edit opens the *television's* editor rather
than reimplementing a form with eight fields on a phone, and the endpoint
answers with a sentence to say so: a screen changing in another room with no
acknowledgement in your hand is indistinguishable from a dead button.

**`/events` is server-sent events, and the poll is the fallback, not the
loser.** The poll cannot be prompt — a press changes the television now and
the phone finds out up to a second later, which is why `pollSoon()` existed
at all. A held connection is also exactly what a phone breaks: a screen
lock, a Wi-Fi roam, a tab eviction and a captive-portal proxy all end it,
some silently. So the page opens a stream, keeps polling until it is
actually open, and falls back on any error. Both read the same `StateFeed`,
so they cannot disagree. `tests/test_pairing.py` holds a raw socket open and
watches a published change arrive, because "libsoup will let later writes
reach the socket" is the assumption the whole feature rests on and is not
obvious from the API.

One claim here was wrong and is worth recording: the first version of the
comment said accumulation had to be off or nothing would be delivered.
Measured — it is delivered either way. Accumulation is off because libsoup
otherwise retains every byte ever written to a response that is meant to
live for hours, which is a slow leak per connected phone rather than a
broken feature. The test was rewritten to claim only what it proves.

**The trackpad has gestures.** One finger moves and taps; two fingers
scroll and right-click; three fingers middle-click; a long press or a
double-tap-and-hold drags. The last one needed `press`/`release` on
`PointerInjector` as separate calls — a click that releases itself 50ms
later cannot move a window or select a line of text, which are the two
things a trackpad is for that a D-pad is not. Scrolling uses
`NotifyPointerAxis` rather than `…AxisDiscrete`: the discrete call moves in
whole wheel clicks, so a continuous gesture would jump in three-line steps,
and the `finish` option is what stops kinetic scrolling drifting on after
the fingers lift. The legend under the pad is not decoration — a gesture
nobody is told about is a gesture nobody has — and Click/Right click stay as
buttons for the thumb that has not learned them yet.

**Harness note.** The page was driven in real headless Chrome at a phone
viewport over the DevTools protocol, from Node with no dependencies (Node 22
has a WebSocket client built in), against a real `HomeView` with the remote
switched on: launch an app from the phone, watch the page reshape, press
Close, watch it come back. Worth keeping. It also produced a false alarm
worth writing down — the harness runs the phone's browser *on the
television*, so the muted keep-awake video makes the desktop emit
`XF86AudioPlay`, which Salon maps to `PLAY_PAUSE`, which with nothing
playing deliberately launches the focused tile. Intermittent, alarming, and
entirely an artefact of a phone and a television being the same machine.

## 2026-08-23 (late) — a second compositor underneath, and a stale install

**The session files on this machine were four days old and pre-fix.** Before
anything else, `~/.local/share/gnome-session/sessions/salon.session` was
found still reading `RequiredComponents=org.gnome.Shell;rocks.salon.Salon;` —
dead twice over: the key gnome-session 50 does not act on, naming an
application id renamed away in `80dfdb5`. `~/.local/share/systemd/user/` did
not exist at all, and neither did `~/.local/bin/salon`. So `meson install`
had not run since `ba288af`, the commit that made the session real, and
picking *Salon* at the login screen would have started gnome-session with no
components: no compositor, no launcher, a black screen.

This is worth recording as a class of bug rather than an incident. An
installed tree is a snapshot, `bin/salon` deliberately runs from source, and
every gate in `check.sh` reads the source too — so nothing in the loop ever
looks at what is deployed. The tree was right the whole time. Only the
machine was wrong, and only in the one place no test can see. The check that
found it was `ls -l` on the install prefix, which is not a sophisticated
instrument.

It also leaves a claim in CLAUDE.md unresolved: the human reports logging
into the Salon session on 2026-08-23 and getting the Shell and Salon. That
cannot have come from the file above. Either a system-prefix install
happened and has since been overwritten, or what came up was not this
session. Left as an open question rather than quietly corrected — the report
is evidence too, and guessing which half is wrong would throw it away.

**GNOME Kiosk is offered as a second session, not as a replacement.** The
suggestion on the table was to stop starting GNOME Shell and start
`gnome-kiosk` instead — a Mutter-based compositor with no panel, dash, dock
or overview. Three things made it cheap enough to just do:

- The Ubuntu package ships almost nothing beyond the compositor:
  `org.gnome.Kiosk.target` and `org.gnome.Kiosk@wayland.service`, shaped
  exactly like `org.gnome.Shell@.service` and composed the same way
  `gnome-session@ubuntu.target.d/ubuntu.session.conf` composes the desktop.
  So the difference between the two sessions is one `Requires=` line.
- `gnome-kiosk` links `libmutter-18.so.0`, the same soname already installed.
  Not a second Mutter — the same one, driven by a different shell.
- Salon never talks to `org.gnome.Shell`. Grepped: the only compositor-
  adjacent thing in the tree is `org.freedesktop.portal.RemoteDesktop` in
  `services/pointer_injector.py`.

The reason to want it is not the 309 MB of `gnome-shell` RSS, though that is
real. It is that **GNOME Kiosk fullscreens every window it is handed**, and
50 adds a `window-config.ini` with `set-fullscreen=true` matched by window
class. That is the one gap on the "what is still missing" list that no
amount of work inside Salon can close: a native application decides its own
window state, and no Wayland client may override another's. A compositor
may.

The reason not to make it the only session is that the RemoteDesktop portal
path under it is **reasoned about, not measured**. `xdg-desktop-portal-gnome`
reaches `org.gnome.Mutter.RemoteDesktop`, which lives in libmutter and so
should be there — but if it is not, the phone trackpad, `/type` into a
launched app and gamepad pointer control all die together, and they die in a
session with no overview to escape to. Two entries at the login screen costs
two small files and keeps a way back.

**`DesktopNames=GNOME;Salon;` stays in the kiosk entry**, and the file says
why in a comment, because the obvious edit is to remove it once GNOME Shell
is not running. `/usr/share/xdg-desktop-portal/portals/gnome.portal` is
`UseIn=gnome`: dropping GNOME from `XDG_CURRENT_DESKTOP` picks a different
portal backend, or none.

The drop-in requires `org.gnome.Kiosk.target` rather than
`org.gnome.Kiosk@wayland.service` directly. The service is templated on
session *type* and carries `ConditionEnvironment=XDG_SESSION_TYPE=%I`; the
target is upstream's entry point. It `Wants=` the instance rather than
`Requires=` it, which would normally be a way to get a session with no
compositor — but the instance carries its own
`OnFailure=gnome-session-shutdown.target`, so a compositor that fails still
takes the session down instead of leaving a black screen up.

Both sessions share `io.github.alexydaher.Salon.service`. Salon does not know
which compositor it connected to, and a second copy of the `Restart=always`
policy is a second place for it to drift.

## 2026-08-23 (late, cont.) — why the session entry was never at the login screen

**GDM does not read the user's data directory, and cannot.** The session
entries had been installed to `~/.local/share/wayland-sessions/` since
2026-08-19 and were never once offered at the login screen. `strings` on
`/usr/sbin/gdm3` gives the whole answer — the search paths are compiled in
and absolute:

```
/etc/X11/sessions/
/usr/share/gdm/greeter/wayland-sessions/
/usr/share/wayland-sessions/
/usr/share/xsessions/
/usr/share/gnome-session/sessions/%s.session
```

The last one matters as much as the others: GDM checks a session's *runnable*
state against that exact path, so the `.session` definition has to be
system-wide too, not just the `wayland-sessions` entry. And the bare
`wayland-sessions` / `xsessions` strings alongside them are for building
`$XDG_DATA_DIRS/wayland-sessions` — but GDM's `XDG_DATA_DIRS` is the system
default, never anyone's home. There is no path by which a home directory is
consulted. It isn't a permissions problem (the daemon is root and could read
it); it is a design decision, and the right one: a session entry is a thing
that runs before authentication finishes.

**So `meson setup --prefix=$HOME/.local` can never produce a working session
entry.** That is worth stating plainly because the build directory in this
tree is configured exactly that way, and everything else about it is fine —
the schema, the gresource, the icons and the systemd *user* units all work
from a user prefix, because `systemd --user`, `gnome-session` and GTK all run
as the user after login. Only the four files GDM itself reads are different
in kind, and nothing in the build system distinguishes them.

This also closes the question left open earlier the same day about the human
having logged into a Salon session on 2026-08-23. Whatever that was, it was
not a session picked from these files: GDM had never seen them. The
`RequiredComponents=` archaeology stands on its own — the installed copy
really was four days stale and really would not have worked — but it was
never the reason the entry did not appear.

The fix applied is the four files copied into `/usr/share/wayland-sessions/`
and `/usr/share/gnome-session/sessions/`, leaving the units and the binary
under `~/.local`. A full `--prefix=/usr` install is the tidier long-term
answer, but it has a footgun worth knowing about first:
`~/.local/share/systemd/user` sorts *before* `/usr/share/systemd/user` on
systemd's unit path, so a leftover user-prefix `io.github.alexydaher.Salon.service`
silently shadows the system one and keeps pointing `ExecStart=` at a stale
`~/.local/bin/salon`. Remove one before installing the other.

## 2026-08-23 (evening, cont.) — four changes that came from using it

### The pairing code stands in the corner when nothing is connected

`ui/phonepairing.py` is a screen you have to *navigate to*, and the state it
is most needed in is the one where there is nothing to navigate with. No
controller plugged in and no phone talking to us means Salon's only inputs
are a keyboard and a mouse — which is not what is in a living room, and not
what this is for. The way to the remote required the remote.

So `ui/remotehint.py` is a small card in the bottom-right holding the same QR
the full screen holds, on screen for exactly as long as `gamepad count == 0
and not pairing.connected`. Plug a pad in or scan the code and it is gone.

Three things had to be true for it to work:

* **libmanette had to be asked about unplugging.** `GamepadSource` connected
  `device-connected` and not `device-disconnected`, so nothing in Salon had
  ever noticed a pad leave. It now keeps the device set and reports its size,
  and the disconnect handler also drops that device's latched axis state —
  a pad unplugged mid-direction would otherwise stay latched forever, since
  the release event that clears it can only come from the device that is gone.
* **The server has to be running to have a code**, so the card takes its own
  holder on `PairingServer`. Separate from `_REMOTE_HOLDER` deliberately: the
  Settings toggle means "keep the remote on", the card means "there is nothing
  to press with", and those are different claims that must not be able to stop
  each other's server.
* **The hold is dropped a beat late.** `release()` stops the server outright
  once the last holder lets go. Releasing the instant a phone connects would
  tear down the session that phone had just opened. The card hides
  immediately; the hold goes when there is no longer a phone to lose.

The card does *not* take the RemoteDesktop grant when it starts the server.
That grant puts a permission dialog on screen the first time, which is fair
when the user has just switched the remote on and unreasonable when Salon
started it by itself because nothing was plugged in. It is taken when a phone
actually answers the card instead — a moment the user caused.

### Status left, actions right

The top bar was one right-aligned strip: network, battery, date, clock, then
five buttons. Splitting it puts the state where every television, phone and
set-top box already puts it, and stops the only *pressable* part of the bar
from being crowded by five glyphs that are not.

Two overlay children rather than one full-width bar, which is not a style
choice: a `Gtk.Box` spanning the screen is picked for pointer events across
its whole width, and the tile rows scroll under that strip. `set_can_target`
is no help — turning it off on the box takes the buttons with it.

### A value is chosen from a list, not stepped into

Settings' horizontal axis has now been through three designs. LEFT/RIGHT
changing a value in place made the button that means "back" everywhere else
silently edit a setting (fixed 2026-08-19 by the *engage* mode: RIGHT steps
into a row, then LEFT/RIGHT walk its values, OK or BACK leaves).

Engaging fixed the ambiguity and kept the part nobody liked. A direction key
was still what changed the setting; the values went past one at a time with
no way to see the set; and how many presses a change cost depended on where
in the list the current value happened to sit. "Theme" has four values and
you could only ever see one of them.

`ui/settings/popup.py` raises them as a list instead — anchored on the row's
own value so it opens where the setting is written, UP/DOWN to walk it with
every alternative on screen, OK to pick, BACK or LEFT to leave it alone. It
is what a console does, and the reason a console does it is that it is the
only arrangement where the alternatives are visible before one is chosen.

Ranges are enumerated into that same list rather than kept as steppers. Every
range here is a set of coarse, deliberately chosen steps — 5% of a scale,
50ms of a repeat delay — and the longest is 41 entries in a list that
scrolls, which beats pressing RIGHT forty times. Their keys are indices, not
values, because two neighbouring steps can format identically ("Off" and
"0 s") and the key has to be the one thing that is unique.

Toggles are the exception and stay a direct switch. A popup offering two
items, one of which is what the row already says, is two presses and a panel
to do what one press already does — and unlike a palette or a range there is
nothing to *see* in the set of alternatives.

`set_autohide(False)` on the popover, for the same reason Salon has no other
modal GTK anything: an autohiding popover takes a GTK input grab, and none of
Salon's input arrives through GTK focus. A grab would silently take the
gamepad, the phone and the CEC remote away from the screen underneath.

### Log out

`services/power.py` was logind-only, and logging out is the one action here
that is not logind's to do first: gnome-session owns the session's lifetime
and knows how to shut its components down in order. So `Logout(1)` on
`org.gnome.SessionManager` first, `Terminate()` on
`/org/freedesktop/login1/session/self` as the fallback — and the fallback is
not decoration, because the Salon (Kiosk) session runs gnome-kiosk instead of
the Shell, and a Salon running as a plain app under some other desktop may
have no session manager on the bus at all.

Mode 1 is "no confirmation dialog". Salon is fullscreen over everything, so a
GNOME confirmation prompt would be a dialog the user can neither see nor
answer with a remote. The menu row is a deliberate press on a screen the user
is looking at; that is the confirmation.

It sits between Suspend and Restart in the menu, and it is a different thing
from "Exit Salon" below it: under the session unit's `Restart=always`,
exiting Salon gets you Salon again, and only logging out gets you somewhere
else.

## 2026-08-23 (evening, cont.) — the rows stop at the bars instead of fading under them

The top bar and the detail strip are the two things on the home screen that
*report* rather than act: the time, the network and the battery above; what
the cursor is on and what OK will do with it below. Artwork sliding under
either one is unreadable in both directions — the text loses its background
and the tile loses its top.

That was already known, and the answer was a fade: `_LayoutViewport` spanned
the whole window and masked its content out over exactly the two bands the
bars occupy. It kept the clock legible. It also meant there were always
half-transparent tiles behind the clock, which is a different thing from
there being nothing behind it.

The band is now inset instead. `_viewport_host` takes real top and bottom
margins, so `Gtk.Overflow.HIDDEN` on the viewport clips at the bars' edges
and no tile pixel is drawn in either strip. Both margins are *measured* —
`_top_inset()` is the taller of the two status widgets' natural heights,
`_bottom_inset()` was already measuring the detail strip — because both
carry their own safe-area margin and both move with the du scale, and
`STATUS_BAR_HEIGHT_DU` is a design figure rather than what the widgets ask
for. (`_bottom_inset` learned this lesson already: a guessed constant was
104px against a real 165.)

`_row_anchor_y()` moves into band coordinates, where 0 is the top of the gap.
The anchor line stays measured on the *window* — 38% of a television is a
claim about where a human looks, not about where this widget starts — so it
is converted with a `- top_inset`. Worked through, every term shifts by
exactly that inset and the scroll behaviour is unchanged in screen terms:
the same content rests in the same place. Only the clipping is different,
which is the point.

The fade stays, at 40du rather than the height of a bar. It is no longer
keeping anything legible — the clip does that — and is only there because a
tile cut by a hard edge reads as a rendering fault and a tile's bloom needs
somewhere to go.

Setting margins from `_layout_rows`, which runs from inside an allocation,
is safe because GTK's margin setters return early on an unchanged value: the
steady state assigns nothing and there is no resize loop.

This applies to the home screen only. The all-apps grid and search are
full-bleed overlays that cover both bars and carry their own title and
legend, so there is nothing there to scroll underneath.

## 2026-08-23 (evening, cont.) — the inset was real, the band was not

The previous entry made the row band stop at the two bars instead of fading
under them. It set the margins correctly and they did nothing: tiles were
still drawn straight across the detail strip, and a screenshot of the home
screen with something playing has the now-playing readout with a tile behind
each line of it.

The margins were being applied to a widget that then overhung the screen
anyway. `_viewport_host` is a `SizeReporter`, and it was built without
`propagate_minimum=False` — so it forwarded the `Gtk.Fixed`'s minimum, which
is whatever its children add up to, which for four rows of tiles is about
1540px against a 1101px gap. An overlay child asking for more than the
overlay has is given it. The margins held the top of the band where they
said, the bottom simply ran off the screen, and `Gtk.Overflow.HIDDEN`
clipped at a boundary that was below the window's own.

This is the same trap the all-apps grid, the search results and both
settings lists were each fixed for. The home screen — the one that had it
first and worst — was the one place still missing the flag.

Two other symptoms turn out to have been the same fault, which is why it is
worth writing down rather than just fixing:

- **The home screen had stopped scrolling.** `_on_viewport_resized` reported
  the *content's* height as the band height, so `_row_anchor_y`'s
  `content_height <= band_height` was true by construction and it returned 0
  every time. Every row after the first screenful was unreachable with the
  cursor still moving onto it — the failure mode the `SizeReporter`
  docstring predicts, verbatim.
- **The band's bottom fade was never visible.** It was painted at the bottom
  of a viewport that ended below the screen.

Two consequences had to be dealt with once the clip was real.

**The last row's focused tile was sliced.** `_content_height_px` measured to
the last card's bottom edge, so the scroll limit put the focus growth
(`FOCUS_SCALE_FOCUSED` is 1.09) and the whole bloom past the end of the
band, and the clip took them. The last row's `bleed` now counts as content:
it exists precisely to hold those two things, and every row's viewport is
already positioned to span it.

**The edge fades are a function of overflow, not a constant.** A permanent
40du ramp at the top of the band is wrong at rest, because the top of the
band is exactly where the first row's heading sits when nothing is scrolled
— "Favourites" was dimmed for the entire life of the screen, on top of the
0.45 that already applies to a heading whose row isn't current, with no row
passing under it to justify the softening. Each end now fades by
`min(overflow, 40du)`: nothing when the content ends inside the band,
ramping in over the first pixels of travel, at full strength once a row is
genuinely leaving. That needed the anchor spring to report every frame
rather than only its target, or the fade would snap to full while the rows
were still moving; `_AxisSpring` takes an `on_value` callback for it.

The general lesson is the one the reachability pass keeps producing: a
layout constant that is *computed* from a widget's allocation is only as
true as the allocation, and an overlay will hand a child any size it asks
for. `_viewport_height` was wrong by 40% and nothing anywhere said so —
not a gate, not a warning, not a visibly broken frame, because the two
things it broke both looked like deliberate design.

## 2026-08-23 (night, cont.) — the consent dialog nobody could click

**Salon asks mutter for input injection directly, and only falls back to
the portal.** The symptom is a deadlock, not a nuisance. A ten-foot
appliance's *first* input device is the phone it has not paired yet: fresh
machine, no controller, no keyboard, no mouse. The phone's D-pad works
immediately — those presses arrive over HTTP into Salon's own process and
need no grant at all — but the trackpad and `/type` need to move the system
cursor, so `PointerInjector` asks
`org.freedesktop.portal.RemoteDesktop`, and xdg-desktop-portal-gnome puts
"Allow remote interaction" on the television with a Share button and a
Cancel button. **The only device that can dismiss that dialog is the
pointer the dialog is gating.** `persist_mode=2` and the restore token,
which this project already had, skip the second dialog and every one after
it; they can never skip the first. The machine is unusable on the exact
run where it matters.

The fix is not to automate the dialog — it cannot be, and should not be.
It is to stop asking that question of that answerer.
`org.gnome.Mutter.RemoteDesktop` is on the session bus, owned by
gnome-shell, and the dialog belongs to *the portal backend*, which is a
client of this interface rather than a layer beneath it. Measured here:
`CreateSession` + `Start` is two synchronous calls, about 4 ms, no dialog,
and the session object carries a method set that maps 1:1 onto the portal's
— `NotifyPointerMotionRelative`, `NotifyPointerButton`, the *continuous*
`NotifyPointerAxis` the trackpad needs (with `finish` as a flag bit where
the portal spells it as an `a{sv}` option), and `NotifyKeyboardKeysym`.
This is the same door gnome-remote-desktop goes through. Verified through
the real `PointerInjector` against a live GTK window: 22 motion events, one
click, the scrolled window's adjustment moved 0 → 360, and exactly
`s a l o n Return` arrived. The portal path, kept intact underneath, was
re-measured the same way and still works — 7.3 s to ready against mutter's
4 ms, most of it the portal's three round trips.

Rejected: **`/dev/uinput` and a virtual evdev device**, which was the
obvious suggestion and is genuinely compositor-agnostic. It is `root:root
0600` here with no udev rule, so it needs a rule, a group and a
provisioning step outside the application before it can ever work — a
larger and more privileged surface than a bus name, injecting *below* the
compositor rather than through it, to solve a problem only GNOME has here.
Worth revisiting only if Salon grows a non-mutter target. Also rejected:
**shipping only the mutter route.** It is a private interface (`Version` 1,
no stability promise), and a compositor that is not mutter has no such
name; the portal stays as the fallback and as the honest answer for anyone
who wants the sandbox boundary back.

**gnome-kiosk gets this for free**, which matters because the kiosk session
is the one with no overview to escape to. The name lives in
`libmutter-18.so.0` and `ldd /usr/bin/gnome-kiosk` links exactly that
library — so the interface is present there by construction. Not yet
measured in a live kiosk login, which remains on the gap list.

**The Flatpak deliberately does not get it.** `--talk-name=` for that name
would hand a sandboxed app system-wide input injection with no prompt and
no revocation, which is the sandbox failing at its one job; Flathub would
be right to reject it. The line is simply absent from the manifest,
`call_sync` fails immediately inside the sandbox, and `auto` falls through
to the portal on its own. The absence *is* the configuration.

**`input-injection` has three values, not two.** `auto` prefers mutter and
falls back; `portal` always takes the sanctioned route; `mutter` refuses to
fall back. The third exists because falling back is the wrong behaviour for
an appliance that was deliberately configured this way — a silent fallback
would put the unanswerable dialog back on the television, which is the
whole thing being avoided. Better to fail loudly and leave the trackpad
dead than to hang the screen on a question nobody can answer.

Two things found while measuring, both worth keeping. **`ready` was True on
the portal path while `backend` was still `""`** — the portal's success
handler set the flag but never the label, so Settings would have reported
"not started yet" over a working session. And the verification harness spent
two runs lying, because `sys.path` had `build/` ahead of the source tree and
it was importing meson's *copy* of the module — the same "installed tree
goes stale silently" trap CLAUDE.md already documents, one directory closer
to home than expected.

## 2026-08-25 — the Flathub build is an application, not the appliance

**The Flatpak gives up three native host integrations instead of requesting
their permissions.** It no longer writes GNOME's screen-lock and shell-OSK
keys through host dconf, and it no longer calls logind for logout, suspend,
restart or shutdown. Those are coherent features of the native Salon login
session, but Flatpak cannot install that session in the first place. Inside
the sandbox the power rows are absent and Y points users to the phone's Type
tab; native and distro installs keep the existing behavior. This removes
three Flathub exception requests without disguising a sandbox escape as a
portal.

**Gamepads get input devices, not every device.** Flatpak 1.16 added the
`input` device class, so the manifest now requires 1.16 and uses
`--device=input` instead of `--device=all`. libmanette still receives evdev
controllers while disks, cameras and unrelated device nodes remain outside
the sandbox.

## 2026-08-25 (later) — the main menu spends its screen on itself

Seven changes to the home screen, all from one question: what is each part
of this screen actually telling the user that no other part already is?

**The tile no longer prints its own subtitle; the strip below it does.**
`ui/detailbar.py` was showing `tile.title` and `tile.subtitle` — the exact
two strings the focused card was showing two hundred pixels above it — plus
one clause that was new ("Opens example.com · full screen"). A strip that
costs a seventh of a 1080p panel cannot spend two thirds of itself on an
echo. The title stays in both places on purpose: the card ellipsizes at
about twenty characters and the strip does not, which is the
"Document Scanner"/"Document Viewer" case the strip was built for. The
subtitle moves down entirely (`show_subtitle=False`, home rows only —
the all-apps grid and the search results have no strip and keep it). The
card gets that height back for artwork.

**The strip is chrome now, not a card.** It had a fill, a border, a radius
and a drop shadow, which read as a dialog somebody had left open in the
corner. The rows are inset out of that band already, so nothing is drawn
behind the text for a scrim to separate it from. Rejected: keeping a faint
fill "for legibility" — the only thing under it is the backdrop's own glow,
and `@text-primary` sits on that perfectly well, which was checked by
sampling the capture rather than by looking at it.

**The button legend moved out to `ui/legend.py` and learned what device it
is talking to.** It was the third line of the strip, so it was rebuilt on
every cursor move to say something that had not changed, and it could only
ever be a fact about the selected tile — it had nothing to say about a
menu, the top bar, or an app covering the screen. It is now keyed on the
mode alone. More importantly it names the *button*: "OPTIONS" is printed on
nothing anybody owns. `core/buttons.py` (pure, tested) maps (action,
source) to a caption, `salon/input/gamepad.py` grew `device_name`, and the
DualSense that is the one controller this project has met says Square and
Cross rather than X and A. Words, not glyphs: `data/fonts/` is empty and a
missing ⓐ is a tofu box.

**The clock is not the brightest thing on a launcher any more.** 44du/700
in `@text-primary` made the time heavier than a row heading and a
competitor to the tile the user is about to open. 32du/600 in
`@text-secondary`. Nothing on this screen outranks the thing OK will
launch.

**A catalogue shorter than the band is centred in it.** This reverses
2026-08-23's rule, and the reversal is the point: that rule was written
when the band was the whole window, where centring really did mean floating
in dead space under a distant clock. The band is now exactly the gap
between the two bars, so centring in it is centring between the two things
that frame it. Measured without the last row's bleed — that padding is
transparent room for the bloom, and counting it as content centres a box
one bleed taller than anything visible.

**Rows fade at whichever end has tiles past it**, which the band has done
vertically since 2026-08-23 and the horizontal axis never did: the last
tile was guillotined mid-word at the screen edge, at whatever position a
television's overscan happens to put it. The ramp is capped at the
safe-area margin, because the focused tile rests exactly one margin from
the left edge and the last tile of a row rests one from the right.

This one was found *wrong on the display after being written correctly*.
`_RowViewport` is a `Gtk.Fixed`, a Gtk.Fixed measures to fit its children,
and its parent is another Gtk.Fixed handing out natural sizes — so a row of
four tiles is allocated 1468 px inside a 1280 px window regardless of its
size request, and the ramp computed from `get_width()` was drawn 188 px
past the screen edge. It faded nothing. The left ramp worked, which is
exactly what made it look implemented. The visible span is passed in from
the layout pass now. That is the third distinct form of the Gtk.Fixed
sizing trap in CLAUDE.md and the first on the horizontal axis.

**MENU is four rows, and power is behind one of them.** It was a flat list
of up to nine — Settings, the phone, Suspend, Log Out, Restart, Shut Down,
About, Exit, Cancel — walked with an accelerating auto-repeat. Two of those
rows are what anyone opens MENU for and four of them end the session.
`SystemMenu` gained `set_items(..., on_back=…)` so BACK there means "up one
level" rather than "closed", and the legend says so. "Cancel" is gone from
both menus: BACK cancels, MENU cancels, a click on the scrim cancels, and a
row that does nothing is one more thing for a held direction to stop on. It
stays in the danger confirmations, where it is first and pre-selected.

**Not done, deliberately: promoting "continue watching" to the first
tile.** It is the biggest single lever a television launcher has, and it
changes what `tiles.json` means — position (0,0) would stop being the
user's choice. That is the owner's call, not a refactor.

## 2026-08-26

**The phone remote's page is twenty-five files, and still has no build
step.** `data/remote/index.html` was 1911 lines: markup, 600 lines of CSS
and 1100 of JavaScript in one document, with the module comment explaining
that keeping it as one file was what made it editable. That stopped being
true. It is now markup only — 300 lines — beside `data/remote/ui/`: four
stylesheets and twenty ES modules, none over 190 lines, served from the same
GResource bundle at `/ui/<name>`. The no-build-step property is untouched,
which is the whole reason it is ES modules and plain CSS rather than a
bundler: a launcher that needs npm to change a button is a launcher nobody
will change a button in. What it costs is twenty-five requests on first
load instead of one, over a LAN, once per pairing — and a new failure mode,
a file on disk that is not in the bundle, which is what
`tests/test_phone_page.py` exists for: it walks the page's own references
and every module's imports, checks both directions against
`salon.gresource.xml`, and fails on an orphan as well as on a missing file.

**`/ui/<name>` is matched against a pattern, not sanitised.** One regular
expression — `^[a-z0-9_-]+\.(css|js)$` — applied before the name is joined
to anything, so there is no traversal to get wrong rather than a traversal
that is handled. libsoup turns out to collapse a literal `..` before it
routes at all and to refuse an encoded separator outright, so the pattern
is the second line of defence and both are asserted. A name that passes the
pattern and is not in the bundle is a 404; only the *page* answers 500 with
"this copy may be installed wrong", because for the page that is true.

**Three things the state already carried and nothing acted on.** All three
were found by reading the page against `core/remote.py` rather than by
using it. `wants_text` had a comment in `RemoteState` saying it existed "so
the phone can open its keyboard without being told to", and the page only
recoloured a hint with it — so the one moment the phone is unambiguously
the right tool was the one moment it waited to be asked. It switches to the
Type tab on the rising edge now, the same one-shot pattern the in-app
transition already used. The Type pane's aim pad was the *last* element in
the pane, under the field, so focusing the field raised the phone's own
keyboard over the control the hint tells you to use first: the documented
order was unreachable in the rendered one. And the way out of a launched
application was duplicated into two panes and absent from the other two, so
browsing Apps with Netflix up left no way back.

**The header carries MENU, Power and "Close *Netflix*".** It was a coloured
dot and the word "Home" — the emptiest strip on a phone — and those three
are exactly the presses whose meaning does not depend on which pane you are
looking at. Power is not a new verb: `Action.POWER` has been as global as
MENU on the television since the reachability pass, and every remote in the
room has that button. With an application in front the MENU icon is hidden
rather than greyed, because there MENU *is* "close the app" and two buttons
doing one thing is two things to work out.

**The D-pad plate is a swipe surface as well as four buttons.** Buttons is
how you drive a launcher while looking at your hand; swiping is how you
drive one while looking at the television, which is what a remote is for.
Both, rather than either: the keys stay labelled, reachable by a screen
reader and answering on the way down like a physical key, and dragging
across the plate emits one step per 38 px on top of them. This is what
`data-on-release` on the middle key is for — a swipe usually starts in the
centre, and an OK that fired on the way down would select something every
time somebody tried to move. OK is also the one key nobody holds, so it is
the one that can afford to wait for the release.

**The trackpad accelerates.** Motion went through at 1:1, which means a
350 px pad driving a 3840 px television needs eleven full swipes to cross
it: the surface worked perfectly and was unusable. Gain is now
`1 + 1.9 × px/ms`, capped at 4.5 — slow movement is still exactly 1:1 so a
button is aimable, and a flick multiplies. Scrolling is deliberately not
accelerated: a scroll is a distance, not a nudge at a target.

**`--on-accent` is computed, not assumed.** Every accented surface — the
primary button, a pressed key, the selected tab, "Close *Netflix*" —
hardcoded `#12151A`, which is right for the default amber and unreadable
the moment somebody picks a deep blue in Settings → Appearance. WCAG
relative luminance, one variable, recomputed when the accent changes.

**Two keyboards pointed at one box now agree what is in it.** `RemoteState`
gained `text`, so the phone's field shows what the television's field holds
and Send computes the *difference* rather than appending — a shared prefix
costs the tail, anything else costs one backspace per character. That is
also how a real bug surfaced: the phone's Backspace and Enter keys send
`\b` and `\n`, which is right for the other end of `/type` (a launched
application, where they become real keysyms) and was being appended
literally into a field Salon was drawing. A control character in the middle
of somebody's query, and Enter doing nothing at all. The rule is
`KeyboardModel.apply_remote_text`, pure and tested, rather than a loop in
the pane.

**Cover art travels by whichever of two routes applies.** A streaming
player publishes an `https://` `mpris:artUrl`; that goes to the phone as it
stands and the phone fetches it, because it has the network and proxying
someone else's CDN through the television buys nothing. A local file
becomes `has_art` and Salon serves it at `/np-art` — with no id in the
request and deliberately no way to add one, since the only thing it will
ever serve is the cover of the player in the state the phone has already
been shown. `has_art` is a string prefix test rather than a stat, because
the snapshot is republished on every cursor movement.

**Landscape existed and had never been drawn.** There was not one media
query in the page, so a phone on its side got a 4.6 rem D-pad and four bars
down a 390 px viewport and the remote became a scrolling document. It is a
row now — pad on the left, the bars beside it as columns, the swipe hint
dropped because in landscape a line of prose costs a button. `align-content:
safe center`, because plain `center` on an overflowing flex container puts
the first line above the scroll origin where nothing can reach it.

**Tile columns are counted at breakpoints, not fitted.** `auto-fill` with a
minimum was tried first and is wrong here: the minimum that keeps two 16:9
cards on a 390 px phone is small enough to put six of them on a tablet, and
a card is a piece of artwork with a size worth reading rather than a cell.

**Verified by rendering it, not by reading it.** The pattern that works for
the television works here too: drive a real `PairingServer` on a GLib loop,
point headless Chromium at it from a worker thread at a phone viewport, and
capture every pane. Six things were wrong on screen after being written
carefully — `auto-fill` giving one column at 390 px, the sheet's buttons
laid out inline because a wrapping div is not a flex container, a cover
`<img>` that never hid itself because `""` was both the sentinel and a real
value, a now-playing screen that bunched against the top when the auto
margins it was spaced with belonged to the element that had just been
hidden, a landscape grid that placed two bars in one cell, and a 500 on
`/icon.svg` in any unbundled run because the icon is an *alias* in the
bundle with nothing at `remote/icon.svg` to fall back to.

**Not done, deliberately: a position bar on the now-playing screen.**
`core/remote.py` already argues that one out — MPRIS reports position as a
value that has to be extrapolated against a clock, and a progress bar that
has to be right to the frame is not worth a poll a second. The screen shows
artwork, which is the part that was missing.

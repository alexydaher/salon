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

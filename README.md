# Salon

A fullscreen launcher for GNOME, built for a television across a room and a
controller in your hand.

Salon does one job: it shows you the things you want to watch and play, and
it starts them. It is not a media player, not a media server, and not a
skin over one. It launches the applications and web apps you already have.

![The home screen](docs/screenshots/home.png)

## What it does

* **Rows of tiles**, laid out and sized for three metres away rather than
  sixty centimetres. Focus is a scale-up, an accent ring and a soft bloom
  cast onto the neighbouring tiles, so where you are is never in question.
* **A controller is the whole interface.** A direction pad, OK and Back run
  everything, including the settings and the tile editor; UP from the first
  row reaches search, all your apps, settings and power. A mouse and a
  phone-as-trackpad are first-class alternatives, not afterthoughts —
  every tile is clickable and hover moves the selection.
* **A way back out.** When something you started is filling the screen,
  START closes it and returns you to Salon. Salon hears the controller even
  when it can't see the screen, which is the only reason this can work at
  all on Wayland — see [DECISIONS.md](DECISIONS.md).
* **Favourites and an all-apps grid.** X over any tile pins it to a row at
  the top; the grid button lists every application on the machine, A–Z.
* **Search across everything**: your tiles and every application installed
  on the machine, at once. Type on the on-screen keyboard, or open the
  address it shows on your phone and type there instead.
* **Your phone is the remote.** MENU → Connect a phone puts a QR code on
  the television; scanning it — nothing to type — opens a page showing your
  rows and their artwork, with a D-pad, a trackpad, volume, a keyboard, and
  controls for whatever is playing. Tap a tile to open it. It follows the
  cursor and the current screen, so you can drive from the phone without
  looking up. It keeps the phone's screen on while it's open, and on an
  iPhone you can Add to Home Screen for a fullscreen icon. Runs only while
  you have it switched on; see the limits below.
* **Launch anything**: desktop entries, Flatpaks, plain commands, and web
  apps opened fullscreen in a browser with their own profile so one
  sign-in can't disturb another's.
* **Edit from the sofa.** Add tiles, group them into rows, set artwork,
  pick accent colours, reorder and delete — all with the controller. The
  catalogue is a plain JSON file you can also edit by hand; it hot-reloads
  either way.
* **See what you're changing.** Accent colour, tile size, row density and
  the safe-area inset are adjusted from a strip along the bottom edge with
  the live home screen behind it, rather than from a list of their names.
* **Providers.** Rows can come from your own Python file dropped in a
  folder. A provider that hangs, crashes, or returns nonsense is isolated
  and reported rather than taking the launcher with it. See
  [docs/providers.md](docs/providers.md).

![Search](docs/screenshots/search.png)

![Settings](docs/screenshots/settings.png)

## About DRM, honestly

**Salon cannot play Netflix, Prime Video, or Disney+ itself, and neither
can any other application on Linux that isn't a browser.** Those services
require Widevine at a security level that is only licensed to browsers and
to certified hardware. There is no library to link against and no API to
call; this is a licensing wall, not a missing feature.

What Salon does instead is honest about it: a tile for one of those
services opens the site in Chrome or Chromium, fullscreen, in its own
browser profile, with the page scaled up so it is readable from a sofa.
That is the same thing you would do by hand, minus the hunting for a
window. Playback quality is whatever the browser is licensed for, which on
Linux is usually 720p — again, not something an application can change.

Anything that isn't DRM-locked — YouTube, your own media, Steam, GeForce
NOW, emulators, any installed app — runs natively and is unaffected.

## Buttons

| | Controller | Keyboard | TV remote (CEC) |
|---|---|---|---|
| Move | D-pad / left stick | Arrows | D-pad |
| Choose | A | Return | OK |
| Back | B | Backspace | Back |
| Search | Y | `/` | — |
| Options for the selected tile | X | F10 or `o` | Contents menu / blue |
| Settings and power | START | Menu | Setup menu |

START is the one button that always means the same thing. On the home
screen it opens the system menu; inside Settings it returns you home; while
a launched app has the screen it closes that app and brings you back.

## Requirements

* GNOME on Wayland. Salon is Wayland-only by design and does not fall back
  to X11.
* GTK 4.16 or newer (for CSS `var()`), libadwaita 1.5+, PyGObject.
* Optional: `libmanette` for gamepads, `wpctl` (PipeWire) for volume,
  `cec-client` for HDMI-CEC, Chrome or Chromium for web tiles.

## Building and running

```sh
meson setup build
meson compile -C build
./bin/salon              # runs uninstalled, out of ./build
```

To install so it shows up in **Show Applications** alongside everything
else — no root needed:

```sh
meson configure build --prefix="$HOME/.local"
meson install -C build
```

That puts `salon` on your `PATH`, the desktop entry in
`~/.local/share/applications`, and the icon in the user icon theme. Re-run
`meson install -C build` after changing anything; the installed copy is a
snapshot, not a link to the source tree. For a system-wide install use
`--prefix=/usr/local` and `sudo meson install -C build` instead.

There is a Flatpak manifest (`io.github.alexydaher.Salon.yaml`). Read the comment at
the top of it first: a launcher's entire purpose is starting other
applications, so the manifest asks for host-spawn access, which is not
meaningfully a sandbox. A distribution package or a Meson install is the
more honest option.

## Running it as the session

Installing puts a session entry in `wayland-sessions`, so **Salon** can be
chosen at the login screen. That session is GNOME Shell, the standard GNOME
session services, and Salon — not the full desktop with a launcher on top.

Salon is started by a systemd user unit with `Restart=always`, so if it ever
exits, it comes straight back: the screen blinks and the television is still
a television. A genuine crash *loop* — five starts in thirty seconds, which
means it is never coming up — gives up and returns you to the login screen
rather than spinning on a black screen forever. Either way the reason is in
`$XDG_STATE_HOME/salon/salon.log`, because the restart is otherwise the only
evidence anything happened.

In this session Salon also switches off GNOME's **idle screen lock** for as
long as it is running, and puts it back on the way out. The screen still
blanks on idle; it just doesn't come back asking for a password, which is a
question a gamepad and a TV remote cannot answer. Salon does not do this
when you start it from Show Applications — a guest in someone's desktop has
no business changing that.

For a gentler version, Settings → System → **Start Salon at login** just
adds an autostart entry to your normal desktop session.

## Configuration

Tiles live in `~/.config/salon/tiles.json`. Everything else is GSettings
under `io.github.alexydaher.Salon`. Both are editable by hand, and both are editable
from the interface; changes made either way take effect immediately.

Artwork can be an explicit path, an `https://` URL that Salon fetches and
caches, or a file dropped into `~/.local/share/salon/artwork/` named after
the tile's id. If there is none, Salon composites the application's own
icon onto a gradient built from that icon's dominant colour.

![The tile editor](docs/screenshots/tile-editor.png)

## Development

```sh
./scripts/check.sh     # ruff, mypy --strict, pytest, meson compile
```

`CLAUDE.md` is the orientation document for the codebase; `DECISIONS.md`
records the reasoning behind judgement calls that aren't obvious from the
code.

Two rules matter more than the rest:

* `salon/core/` must never import `gi`. It is enforced by a test that walks
  the AST, and it is what keeps the model, the focus machine, the launch
  resolution and the provider runner testable without a display.
* Don't unit-test GTK widgets. Test the pure layers; verify the widgets by
  running the app and looking at it.

## Logs

Salon restarts itself when it is running as the session, so a crash is
followed by a restart and, without somewhere to write, no evidence. It logs
to stderr — which the session manager hands to the journal — and to
`$XDG_STATE_HOME/salon/salon.log` (rotated, 512 KiB × 3). `SALON_DEBUG=1`
turns on debug output, including GTK's own.

## What hasn't been tested

Salon is 0.1. The gates are green — ruff, `mypy --strict`, 235 tests, and
the AppStream and desktop-entry validators, on every push — but green tests
are not the same as a verified appliance, and some of this needs hardware
that wasn't attached to the machine it was written on.

* **HDMI-CEC has never touched a CEC adapter.** The keycode table and the
  `cec-client` line parsing are covered by tests; nothing else about it has
  run against a television.
* **One controller.** A DualSense over USB enumerates, and the mapping has
  now been used rather than only reasoned about. No other pad has been
  tried. If yours is wrong, that's a bug worth filing — the mapping is in
  `salon/input/gamepad.py`.
* **A polkit refusal has never been seen.** Suspend, restart and shut down
  have now been invoked and they work. What that cannot exercise is the
  path where logind *says no* and the denial has to arrive back as a
  message on screen rather than vanishing: an account permitted to power
  the machine off never takes it. That path remains untested.
* **No screen reader.** Roles, names and the selected/active-descendant
  relationships are published and were checked by walking the live AT-SPI
  tree, but Orca has never been run against Salon, so whether each tile is
  actually *spoken* on arrival is unknown.
* **Read at a desk, not across a room.** Whether the tile size and the row
  anchor work at three metres, and whether the focus bloom is right on a
  panel with a television's black level, are both still guesses.

### The phone remote is not private

MENU → **Connect a phone** shows a QR code. Scanning it opens a page that is
the whole remote: your rows and their artwork, a D-pad, a trackpad, volume,
a keyboard, and transport controls for whatever is playing. Tapping a tile
opens it on the television.

The trackpad and the keyboard reach *other* applications too — the search
box inside a browser tile is the one text field on a television that Salon
cannot draw for you. That needs the desktop's input permission (Settings →
Input → Gamepad cursor); without it the phone says so rather than going
quiet.

It is plain HTTP on your local network. Two things guard it — a 128-bit
session token, carried in the QR code's URL *fragment* so it never reaches
a server log, and a four-digit code for anyone typing the address by hand,
with a lockout after five wrong guesses. Both stop a stranger *sending*
something to your television. Neither stops anyone already on the same
network from *reading* what you type, because it isn't encrypted. It's a
search box and a remote, so this is usually nothing — but don't type a
password into it.

TLS would mean a self-signed certificate, which means a browser warning,
which would take the one-scan path away for a threat model that is "someone
is already on your Wi-Fi". Instead: requests from outside your own network
are refused outright, the server runs only while something is asking for it
(the search screen, or the remote you switched on), and it shuts itself
down after five idle minutes.

### Keeping the remote on your phone's Home Screen

**On an iPhone**, Share → **Add to Home Screen** gives it its own icon and
opens it fullscreen, with no browser chrome. That works today, on plain
HTTP; Safari asks nothing else of a page to do it.

**On Android**, Chrome will not offer to install it, and this is not
something Salon can fix. Installation requires a service worker, a service
worker requires a secure context, and a secure context means HTTPS — which
on a LAN address means a certificate no public authority will issue, for
the reason in the section above. Chrome's own "Add to Home screen" still
works from the ⋮ menu; it makes a shortcut rather than an installed app,
which in practice looks much the same.

The same rule is why the remote does not use the Screen Wake Lock API to
stop your phone dimming mid-film: `navigator.wakeLock` is gated on a secure
context too, so on a phone it is not refused, it is simply absent. The page
plays a muted one-second black video on a loop instead, which is the
fallback every phone honours. Measured at the LAN address a scanned QR
actually points at, in Chrome at a phone viewport: `isSecureContext` false,
`wakeLock` absent, the clip playing and looping.

### Other known limits

* **Only web tiles can be made fullscreen.** URL tiles pass
  `--start-fullscreen`; native applications decide their own window state,
  and no Wayland client may override another's.
* **English only.** There is no gettext and no `po/`. That's a decision for
  0.1 rather than an oversight, but it is a decision.
* **The backdrop is a pool of accent light, not blurred artwork.**
* **Building the Flatpak may need `--disable-rofiles-fuse`**, on hosts where
  `org.flatpak.Builder` can't spawn `rofiles-fuse`. It only turns off a
  hardlink-protection layer over the build tree.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE); every source file carries an SPDX
identifier.

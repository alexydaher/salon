# Salon

A fullscreen launcher for GNOME, built for a television across a room and a
controller in your hand.

Salon does one job: it shows you the things you want to watch and play, and
it starts them. It is not a media player, not a media server, and not a
skin over one. It launches the applications and web apps you already have.

![The home screen](docs/screenshots/home.png)

## Install

Salon is distributed directly by the project, not through Flathub. The
signed Flatpak repository is the easiest way to install it and receive
updates. A native Debian package is also available for the complete GNOME
session integration.

If `flatpak --version` does not work, follow the setup instructions for your
distribution at [flatpak.org/setup](https://flatpak.org/setup/) first. Salon
requires Flatpak 1.16 or newer.

Install the Flatpak for your user account from Salon's repository:

```sh
flatpak install --user https://alexydaher.github.io/salon/io.github.alexydaher.Salon.flatpakref
```

This adds the signed `salon` remote. Future releases arrive with the normal
`flatpak update` command and appear in software installers that handle
Flatpak updates.

If you prefer a standalone download, open the [latest release][latest-release]
and download the bundle for your computer:

* `Salon-v0.2.11-x86_64.flatpak` for most Intel and AMD PCs.
* `Salon-v0.2.11-aarch64.flatpak` for ARM64 computers.

Open the downloaded file with your software installer, or install it from a
terminal:

```sh
flatpak install --user ~/Downloads/Salon-v0.2.11-x86_64.flatpak
```

Use the `aarch64` filename instead on ARM64. If you are unsure which one you
have, run `uname -m`: it prints either `x86_64` or `aarch64` (sometimes
`arm64`). The app itself is not on Flathub, but its standard GNOME 50 runtime
is; Flatpak may ask permission to download that runtime when you install the
bundle.

Launch **Salon** from your applications screen, or run:

```sh
flatpak run io.github.alexydaher.Salon
```

Standalone bundles do not update automatically. To upgrade one, download the
bundle from the next release and install it over the existing copy:

```sh
flatpak install --user --or-update ~/Downloads/Salon-v0.2.11-x86_64.flatpak
```

Your settings and catalogue are preserved. To uninstall Salon and remove its
remote when no longer needed:

```sh
flatpak uninstall --user io.github.alexydaher.Salon
flatpak remote-delete --user salon
```

Each release also includes `SHA256SUMS` if you want to verify the download.
Run the following from the directory containing both files:

```sh
grep 'Salon-v0.2.11-x86_64.flatpak$' SHA256SUMS | sha256sum --check -
```

Change the filename to the ARM64 bundle when appropriate.

### Native Debian package

The native package enables Salon's login-screen sessions, host power actions,
and the rest of its GNOME integration. Download `salon_0.2.11-1_all.deb` from
the [latest release][latest-release], then install it with APT so dependencies
are resolved automatically:

```sh
sudo apt install ~/Downloads/salon_0.2.11-1_all.deb
```

The package is architecture-independent and works on both AMD64 and ARM64,
provided the distribution supplies Salon's minimum GTK, libadwaita, GLib and
Python versions. Unlike the Flatpak repository, a downloaded Debian package
does not currently update automatically.

| Installation | Best for | Dedicated login session | Host power/settings |
|---|---|---:|---:|
| Signed Flatpak repository | A quick installation with updates | No | No |
| GitHub Flatpak bundle | An offline or one-time installation | No | No |
| Debian package | A native installation with managed dependencies | Yes | Yes |
| Native user install | A normal GNOME desktop | No | Yes |
| Native system install | A television or kiosk machine | Yes | Yes |

[latest-release]: https://github.com/alexydaher/salon/releases/latest

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
* **With nothing connected, the code is already on screen.** If there is no
  controller plugged in and no phone talking to Salon, a small pairing code
  sits in the bottom-right corner and goes away the moment either turns up.
  Reaching the pairing *screen* needs something to press with, which is
  exactly what is missing in that state. Settings › Input turns it off.
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
| Previous / next group | LB / RB | Page Up / Page Down | Channel down / up |
| Settings and power | START | Menu | Setup menu |

START is the one button that always means the same thing. On the home
screen it opens the system menu; inside Settings it returns you home; while
a launched app has the screen it closes that app and brings you back.

Inside Settings, RIGHT opens the highlighted section or control and B is
the only button that goes back. LB and RB move between top-level settings
sections without changing whether the section list or its panel is active.

## Requirements

* GNOME on Wayland for the full experience and native integration. Salon is
  Wayland-only by design and does not fall back to X11.
* Python 3.12+, GTK 4.16.0+ (for CSS `var()`), libadwaita 1.5.0+, GLib/GIO
  2.80.0+, GdkPixbuf 2.42.0+, libsoup 3.0.0+, PyGObject, and libmanette
  0.2.0+. The authoritative values live in
  `build-aux/minimum-versions.ini` and are consumed directly by Meson.
* Optional runtime capabilities: `wpctl` (PipeWire) for volume, `cec-client`
  for HDMI-CEC, Chrome or Chromium for web tiles, GNOME Kiosk for the kiosk
  login session, and Orca for screen-reader use. Missing command-line
  capabilities are reported in Settings; session and accessibility packages
  are administrator-installed features rather than build dependencies.

The Flatpak can also be installed on KDE Plasma Wayland. Salon remains a
GNOME-oriented application, so GNOME-specific session integration is not
available there, but Plasma users can try the launcher, tiles, search,
gamepad input and phone remote normally.

## Build from source

```sh
git clone https://github.com/alexydaher/salon.git
cd salon
meson setup build
meson compile -C build
./bin/salon              # runs uninstalled, out of ./build
```

To install the native build so it shows up in **Show Applications** — no root
needed:

```sh
meson configure build --prefix="$HOME/.local"
meson install -C build
```

That puts `salon` on your `PATH`, the desktop entry in
`~/.local/share/applications`, and the icon in the user icon theme. Re-run
`meson install -C build` after changing anything; the installed copy is a
snapshot, not a link to the source tree.

For a system-wide installation, configure a separate build with `/usr` as
the prefix:

```sh
meson setup build-system --prefix=/usr
meson compile -C build-system
sudo meson install -C build-system
```

This is the installation that makes the **Salon** and **Salon (Kiosk)**
choices available at the login screen.

### Flatpak limits

A launcher's purpose is starting other applications, so Salon's Flatpak asks
for host-spawn access. Treat Salon as a trusted application even though it is
packaged as a Flatpak.

The Flatpak requires Flatpak 1.16 or newer for input-device-only gamepad
access. It deliberately omits direct host dconf and logind access: the
GNOME shell keyboard shortcut and suspend/restart/shut-down actions are not
offered there. Phone typing still uses the RemoteDesktop portal, and native
installs retain all of those host-integration features.

The Flatpak cannot install a login-screen session or turn the machine into a
dedicated kiosk. Use the native system installation for that purpose.

## Running it as the session

A native system installation puts a session entry in `wayland-sessions`, so
**Salon** can be chosen at the login screen. That session is GNOME Shell, the
standard GNOME session services, and Salon — not the full desktop with a
launcher on top.

Salon is started by a systemd user unit with `Restart=always`, so if it ever
exits, it comes straight back: the screen blinks and the television is still
a television. A genuine crash *loop* — five starts in thirty seconds, which
means it is never coming up — gives up and returns you to the login screen
rather than spinning on a black screen forever. Either way the reason is in
`$XDG_STATE_HOME/salon/salon.log`, because the restart is otherwise the only
evidence anything happened.

Salon never changes GNOME's global idle screen-lock preference. Configure
screen locking for the dedicated account before using it as an appliance.
The screen can still blank on idle; disabling password locking for the
dedicated account prevents it returning to a prompt that a gamepad or TV
remote cannot answer.

For a gentler version, Settings → System → **Start Salon at login** just
adds an autostart entry to your normal desktop session.

Your normal desktop session is untouched by any of this. The Salon entries
sit alongside it at the login screen; picking one is a per-login choice, and
nothing about installing them changes the desktop you already have.

**The login screen needs a system-wide install, and a Flatpak cannot give
you one.** GDM's search paths are compiled in and absolute — it reads
`/usr/share/wayland-sessions/` and `/usr/share/gnome-session/sessions/`, and
never a user's home — so `meson install --prefix="$HOME/.local"` puts a
perfectly good Salon on the machine with no entry at the login screen.
Flatpak is the same wall from the other side: it exports only
`applications`, `icons`, `metainfo` and a couple of others out of the
sandbox, and `wayland-sessions`, `gnome-session/sessions` and
`systemd/user` are not on that list. Installing Salon's GitHub Flatpak gets
you the app in your Applications grid; the session is a separate step, and
needs either `--prefix=/usr` or four files copied by hand:

```sh
sudo install -Dm644 build/data/salon.desktop        /usr/share/wayland-sessions/salon.desktop
sudo install -Dm644 build/data/salon-kiosk.desktop  /usr/share/wayland-sessions/salon-kiosk.desktop
sudo install -Dm644 build/data/salon.session        /usr/share/gnome-session/sessions/salon.session
sudo install -Dm644 build/data/salon-kiosk.session  /usr/share/gnome-session/sessions/salon-kiosk.session
```

A session built around a Flatpak would also need its unit's `ExecStart=` to
read `flatpak run io.github.alexydaher.Salon` instead of a path to a binary.

### Salon (Kiosk)

Installing also puts a second entry, **Salon (Kiosk)**, at the login screen.
It is the same session with [GNOME Kiosk][kiosk] underneath instead of GNOME
Shell — a Mutter-based compositor with no panel, dash, dock or overview, so
there is no desktop for a remote to fall into. It needs the `gnome-kiosk`
package, which is not installed by Salon:

```sh
sudo apt install gnome-kiosk      # or your distribution's equivalent
```

The reason to want it: GNOME Kiosk fullscreens every window it is handed. A
Wayland client cannot set another client's window state, which is why only
URL tiles can be launched fullscreen under GNOME Shell — under Kiosk, native
applications go fullscreen too.

The reason it is a second entry and not a replacement: it has far less road
under it. In particular the RemoteDesktop portal — which the phone's
trackpad, the phone's Type tab and gamepad pointer control all depend on —
has not been verified in a Kiosk session. If something is wrong there, log
out and pick **Salon**.

[kiosk]: https://gitlab.gnome.org/GNOME/gnome-kiosk

## Configuration

For a native installation, tiles live in `~/.config/salon/tiles.json`. For
the Flatpak they live in
`~/.var/app/io.github.alexydaher.Salon/config/salon/tiles.json`. Everything
else is GSettings under `io.github.alexydaher.Salon`. Both are editable by
hand and from the interface; changes made either way take effect immediately.

Artwork can be an explicit path, an `https://` URL that Salon fetches and
caches, or a file named after the tile's id dropped into
`~/.local/share/salon/artwork/` for a native installation. The Flatpak uses
`~/.var/app/io.github.alexydaher.Salon/data/salon/artwork/`. If there is no
artwork, Salon composites the application's own icon onto a gradient built
from that icon's dominant colour.

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

### Preparing a Flatpak release

The Flatpak release workflow checks every push and pull request with
`scripts/prepare-flatpak-release.py`. It rejects a change unless the Meson,
Python, AppStream, changelog, screenshot and manifest versions all agree.

Regenerate the four release screenshots from the deterministic local
catalogue after compiling the current tree:

```sh
meson devenv -C build python3 scripts/capture-release-screenshots.py
```

The capture uses a fixed clock, local artwork, isolated settings/cache
directories, and real in-process GTK rendering at 1280×720.

A tag matching that checked version triggers the release build. For example,
after the 0.2.11 changes have been committed and pushed:

```sh
git tag -a v0.2.11 -m "Salon 0.2.11"
git push origin v0.2.11
```

GitHub Actions builds x86-64 and ARM64 Flatpak bundles and a native Debian
package, pins the Salon source to the tag's exact commit, signs and deploys the
Flatpak repository, writes checksums, and creates the GitHub release. Pushing
`main` alone does not publish a release, so choosing and recording the semantic
version stays intentional.

## Logs

Salon restarts itself when it is running as the session, so a crash is
followed by a restart and, without somewhere to write, no evidence. It logs
to stderr — which the session manager hands to the journal — and to
`$XDG_STATE_HOME/salon/salon.log` (rotated, 512 KiB × 3). `SALON_DEBUG=1`
turns on debug output, including GTK's own.

For the Flatpak, that log is normally at
`~/.var/app/io.github.alexydaher.Salon/.local/state/salon/salon.log`.

## What hasn't been tested

Salon is 0.2. The gates are green — ruff, `mypy --strict`, 486 tests, and
the AppStream and desktop-entry validators, on every push — but green tests
are not the same as a verified appliance, and some of this needs hardware
that wasn't attached to the machine it was written on.

* **HDMI-CEC has never touched a CEC adapter.** The keycode table and the
  `cec-client` line parsing are covered by tests; nothing else about it has
  run against a television.
* **One controller, partially.** A DualSense over USB enumerates and a live
  libmanette sample receives its button/axis events. The full in-app action
  pass and every other pad remain release-checklist work. If yours is wrong,
  that's a bug worth filing — the mapping is in `salon/input/gamepad.py`.
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

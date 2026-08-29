# Salon

A fullscreen launcher for GNOME, built for a television across a room and a
controller in your hand.

Salon does one job: it shows you the things you want to watch and play, and
it starts them. Rows of large tiles sized to be read from three metres, driven
entirely by a D-pad, OK and Back — or by a mouse, a TV remote over HDMI-CEC,
or your phone. It is not a media player and not a media server; it launches
the applications and web apps you already have.

![The home screen](docs/screenshots/home.png)

## Install

**Flatpak — easiest, and updates itself.** Needs Flatpak 1.16+; see
[flatpak.org/setup](https://flatpak.org/setup/) if `flatpak --version` fails.

```sh
flatpak install --user https://alexydaher.github.io/salon/io.github.alexydaher.Salon.flatpakref
```

Then launch **Salon** from your applications screen, or
`flatpak run io.github.alexydaher.Salon`.

**Debian package — adds the login-screen sessions.** Download
`salon_0.3.7-1_all.deb` from the [latest release][latest-release] and let APT
resolve the dependencies:

```sh
sudo apt install ~/Downloads/salon_0.3.7-1_all.deb
```

It is `Architecture: all` and works on both AMD64 and ARM64.

**Offline Flatpak bundle.** `Salon-v0.3.7-x86_64.flatpak` or
`-aarch64.flatpak` from the [latest release][latest-release] — run `uname -m`
if you are unsure which:

```sh
flatpak install --user ~/Downloads/<file>
```

**From source.**

```sh
git clone https://github.com/alexydaher/salon.git && cd salon
meson setup build
./bin/salon                              # runs uninstalled, out of ./build
```

`sudo meson install -C build` installs it; use `--prefix=/usr` if you want the
login-screen sessions, since GDM's search paths are compiled in and absolute.

This route is the only one that asks anything of you: GNOME on Wayland, with
Python 3.12+, GTK 4.16.0+, libadwaita 1.5.0+, GLib 2.80.0+, GdkPixbuf 2.42.0+,
libsoup 3.0.0+, PyGObject and libmanette 0.2.0+. The authoritative values live
in `build-aux/minimum-versions.ini`, which Meson reads directly, so a missing
one is named at `meson setup` rather than at startup. The other three routes
carry or resolve their own dependencies.

[latest-release]: https://github.com/alexydaher/salon/releases/latest

## The kiosk session

**Salon (Kiosk)** is a login-screen session that runs Salon on
[GNOME Kiosk][kiosk] instead of GNOME Shell — a compositor with no panel,
dash, dock or overview. The reason to want it: GNOME Kiosk fullscreens every
window it is handed, so native applications go fullscreen too, and not just
web tiles.

**1. Install Salon system-wide**, which is what puts the session entries in
`/usr/share/wayland-sessions/`. The Debian package does this; so does a source
build with `--prefix=/usr`. The Flatpak *cannot* — Flatpak does not export
`wayland-sessions` or `gnome-session/sessions` out of the sandbox.

**2. Install the compositor.** Salon does not pull it in — on a machine that
already has GNOME Shell, the Debian package's dependency is satisfied without
it:

```sh
sudo apt install gnome-kiosk      # or your distribution's equivalent
```

Then log out. **Salon (Kiosk)** is in the gear menu on the login screen,
beside **Salon** (the same thing on GNOME Shell) and your normal desktop;
picking one is a per-login choice and changes nothing else. If something
misbehaves under Kiosk, log out and pick **Salon**.

Neither entry replaces your desktop, and neither is needed to *use* Salon —
it runs as an ordinary window otherwise. For a middle ground, Settings →
System → **Start Salon at login** adds an autostart entry to your normal
GNOME session.

[kiosk]: https://gitlab.gnome.org/GNOME/gnome-kiosk

## Update

```sh
flatpak update io.github.alexydaher.Salon
```

The Debian package and the offline bundle do not update themselves — download
the new one from the [latest release][latest-release] and install it the same
way. From source, `git pull && meson install -C build`.

## Uninstall

```sh
flatpak uninstall --user io.github.alexydaher.Salon
flatpak remote-delete --user salon
```

For the Debian package, `sudo apt remove salon`. For a source install,
`sudo ninja -C build uninstall`.

Your tiles and settings are left behind either way. To remove those too:

```sh
rm -rf ~/.config/salon ~/.local/share/salon ~/.cache/salon
rm -rf ~/.var/app/io.github.alexydaher.Salon        # Flatpak
dconf reset -f /io/github/alexydaher/Salon/
```

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).

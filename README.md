# Salon

**A fullscreen GNOME launcher built for the sofa.**

Salon opens your applications, games and websites as large television-friendly
tiles. Control it with a gamepad, keyboard, mouse, HDMI-CEC remote or phone.

![Salon home screen with favourites, recent items and installed apps](.github/readme/home.png)

- Launch installed apps, web apps and commands
- Search and configure everything without leaving the television
- Run as an app or as a dedicated GNOME Kiosk session

<p align="center">
  <img src=".github/readme/settings.png" alt="Salon appearance settings" width="65%">
  <img src=".github/readme/phone-remote.jpg" alt="Salon phone remote" width="17%">
</p>

## Install

### Flatpak — recommended

Requires Flatpak 1.16 or newer. See [flatpak.org/setup] if Flatpak is not yet
installed.

```sh
flatpak install --user https://alexydaher.github.io/salon/io.github.alexydaher.Salon.flatpakref
```

Open **Salon** from the applications screen, or run:

```sh
flatpak run io.github.alexydaher.Salon
```

### Debian — Kiosk-ready

Download the `.deb` from the [latest release], then install it with APT:

```sh
cd ~/Downloads
sudo apt install ./salon_*-1_all.deb
```

The same package works on AMD64 and ARM64.

<details>
<summary>Offline bundle or source install</summary>

For an offline installation, download the Flatpak bundle for your architecture
from the [latest release], then run:

```sh
cd ~/Downloads
flatpak install --user ./Salon-*.flatpak
```

To run Salon from source:

```sh
git clone https://github.com/alexydaher/salon.git
cd salon
meson setup build
./bin/salon
```

Minimums: Python 3.12, GTK 4.16.0, libadwaita 1.5.0, GLib 2.80.0,
GdkPixbuf 2.42.0, libsoup 3.0.0 and libmanette 0.2.0. The source of truth is
[minimum-versions.ini](build-aux/minimum-versions.ini).

See the [development guide](docs/development.md) for the source workflow and
the [session guide] for a system-wide source install.

</details>

## Kiosk

**Salon (Kiosk)** replaces the normal desktop for that login session. There is
no panel, dock or overview, and launched applications are fullscreen.

1. Install the Debian package above, or [install from source system-wide][session guide].
2. Install the compositor: `sudo apt install gnome-kiosk`
3. Log out, open the login-screen gear menu and choose **Salon (Kiosk)**.

This does not replace your normal desktop; the choice applies only to that
login. Flatpak cannot add login-screen sessions. See the [session guide] for
source installation and troubleshooting.

## Update

| Installation | How to update |
|---|---|
| Flatpak | `flatpak update io.github.alexydaher.Salon` |
| Debian or offline bundle | Download the new file from the [latest release] and install it again |
| Source | `git pull` — the next `./bin/salon` launch rebuilds it |

## Uninstall

| Installation | Command |
|---|---|
| Flatpak | `flatpak uninstall --user io.github.alexydaher.Salon` |
| Debian | `sudo apt remove salon` |
| Source | `sudo ninja -C build uninstall` |

After uninstalling the Flatpak, `flatpak remote-delete --user salon` also
removes its update source. Tiles and settings are kept by default.

<details>
<summary>Also delete all tiles and settings</summary>

This cannot be undone.

```sh
rm -rf ~/.config/salon ~/.local/share/salon ~/.cache/salon
rm -rf ~/.var/app/io.github.alexydaher.Salon
dconf reset -f /io/github/alexydaher/Salon/
```

</details>

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).

[flatpak.org/setup]: https://flatpak.org/setup/
[latest release]: https://github.com/alexydaher/salon/releases/latest
[session guide]: docs/sessions.md

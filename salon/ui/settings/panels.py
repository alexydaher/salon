# SPDX-License-Identifier: GPL-3.0-or-later
"""The non-tile settings sections (§6.8): network, appearance, input,
browser, audio, system, about.

Everything Salon owns is read and written straight to GSettings. That's
deliberate: these are scalar preferences, GSettings is typed, atomic and
already the store §5 assigns them to, and a value changed here has to be
visible to the running UI without a save step — `HomeView` and friends
subscribe to the same keys.

Everything Salon does *not* own — Wi-Fi, displays, Bluetooth pairing, the
clock, the keyboard layout, accessibility — is a link into
gnome-control-center, per §1. A television's settings screen still has to
*offer* those, and be honest about where they lead: a launcher that hides
the Wi-Fi picker because it isn't the launcher's job leaves the user with a
device they cannot get online. What Salon adds on this side is the status,
read out where the question is asked, so nobody has to open a control panel
to find out whether they are connected.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib  # noqa: E402

from salon.core import sandbox, tokens  # noqa: E402
from salon.services import audio, launcher, netinfo  # noqa: E402
from salon.ui.settings.context import Panel, SettingsContext  # noqa: E402
from salon.ui.settings.widgets import (  # noqa: E402
    ActionRow,
    ChoiceRow,
    InfoRow,
    RangeRow,
    SettingsRow,
    TextRow,
    ToggleRow,
)

_ACCENTS = [
    ("#E8A33D", "Lamplight amber"),
    ("#D9584B", "Ember"),
    ("#4C9BE8", "Cold blue"),
    ("#5FBF7F", "Green"),
    ("#B77BE8", "Violet"),
]


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


# --- appearance ----------------------------------------------------------


def appearance_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            ChoiceRow(
                "Accent colour",
                _ACCENTS,
                lambda: settings.get_string("accent-color"),
                lambda value: settings.set_string("accent-color", value),
                detail="Used for focus, selection and the tile glow",
                preview=True,
            ),
            RangeRow(
                "Safe area",
                lambda: settings.get_double("safe-area-percent"),
                lambda value: settings.set_double("safe-area-percent", value),
                minimum=tokens.SAFE_AREA_MIN_PERCENT,
                maximum=tokens.SAFE_AREA_MAX_PERCENT,
                step=0.5,
                fmt=lambda v: f"{v:.1f}%",
                detail="Inset from the screen edges. Televisions still overscan.",
                preview=True,
            ),
            RangeRow(
                "Tile size",
                lambda: settings.get_double("tile-scale"),
                lambda value: settings.set_double("tile-scale", value),
                minimum=0.75,
                maximum=1.5,
                step=0.05,
                fmt=_percent,
                detail="How large each tile is drawn",
                preview=True,
            ),
            RangeRow(
                "Row density",
                lambda: settings.get_double("row-spacing-scale"),
                lambda value: settings.set_double("row-spacing-scale", value),
                minimum=0.6,
                maximum=1.6,
                step=0.05,
                fmt=_percent,
                detail="Lower packs more rows onto the screen",
                preview=True,
            ),
            RangeRow(
                "Animation speed",
                lambda: settings.get_double("animation-scale"),
                lambda value: settings.set_double("animation-scale", value),
                minimum=0.0,
                maximum=2.0,
                step=0.25,
                fmt=lambda v: "Off" if v == 0 else _percent(v),
            ),
            ToggleRow(
                "Reduced motion",
                lambda: settings.get_boolean("reduced-motion"),
                lambda value: settings.set_boolean("reduced-motion", value),
                detail="Focus changes instantly; the highlight stays unmistakable",
            ),
        ]

    return Panel(title="Appearance", build=build, icon_name="applications-graphics-symbolic")


# --- network -------------------------------------------------------------


def network_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    """Status Salon reads itself, configuration it hands to GNOME.

    The status arrives asynchronously (NetworkManager is on the system bus),
    so the panel builds with a placeholder and rebuilds once when the answer
    lands — guarded against rebuilding on an unchanged value, because
    context.rebuild() reconstructs every row and an unconditional callback
    would loop.
    """
    status: list[netinfo.NetworkStatus] = []

    def on_status(found: netinfo.NetworkStatus) -> None:
        if status and status[0] == found:
            return
        status[:] = [found]
        context.rebuild()

    def build() -> list[SettingsRow]:
        netinfo.status_async(on_status)
        current = status[0] if status else None
        return [
            InfoRow(
                "Connection",
                current.summary if current else "Checking…",
                detail=current.connectivity if current else "",
                # The same glyph the top bar is showing, so the row and the
                # bar can never disagree about what the connection is.
                icon_name=(current.icon_name if current else "") or "network-wireless-symbolic",
            ),
            ActionRow(
                "Wi-Fi",
                lambda: context.open_control_center("wifi"),
                detail="Choose a network and enter its password, in GNOME Settings",
            ),
            ActionRow(
                "Wired and VPN",
                lambda: context.open_control_center("network"),
                detail="Ethernet, VPN and proxy settings",
            ),
        ]

    return Panel(title="Network", build=build, icon_name="network-wireless-symbolic")


# --- input ---------------------------------------------------------------


def input_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            ActionRow(
                "Pair a remote or controller",
                lambda: context.open_control_center("bluetooth"),
                detail="Bluetooth pairing, in GNOME Settings",
            ),
            ActionRow(
                "Test a controller",
                lambda: context.push(_gamepad_panel(context)),
                detail="Shows what Salon receives, live",
                value="›",
            ),
            RangeRow(
                "Repeat delay",
                lambda: float(settings.get_int("key-repeat-initial-ms")),
                lambda value: settings.set_int("key-repeat-initial-ms", int(value)),
                minimum=150,
                maximum=1000,
                step=50,
                fmt=lambda v: f"{v:.0f} ms",
                detail="How long a direction is held before it repeats",
            ),
            RangeRow(
                "Repeat interval",
                lambda: float(settings.get_int("key-repeat-interval-ms")),
                lambda value: settings.set_int("key-repeat-interval-ms", int(value)),
                minimum=40,
                maximum=400,
                step=10,
                fmt=lambda v: f"{v:.0f} ms",
            ),
            ToggleRow(
                "Gamepad cursor in web tiles",
                lambda: settings.get_boolean("gamepad-pointer"),
                lambda value: settings.set_boolean("gamepad-pointer", value),
                detail=(
                    "Right stick moves the pointer over a web tile. "
                    "The desktop asks for permission once."
                ),
            ),
            ActionRow(
                "Forget remote-control permission",
                lambda: _forget_remote_desktop(context, settings),
                detail=(
                    "Granted — Salon reopens its session silently"
                    if settings.get_string("remote-desktop-restore-token")
                    else "Not granted yet; you'll be asked the next time it's needed"
                ),
            ),
            ToggleRow(
                "HDMI-CEC input",
                lambda: settings.get_boolean("cec-enabled"),
                lambda value: settings.set_boolean("cec-enabled", value),
                detail=(
                    "Use the TV remote over HDMI. Needs cec-client installed."
                    if shutil.which("cec-client")
                    else "Needs cec-client, which isn't installed."
                ),
            ),
        ]

    return Panel(title="Input", build=build, icon_name="input-gaming-symbolic")


def _forget_remote_desktop(context: SettingsContext, settings: Gio.Settings) -> None:
    """Hand the remote-control grant back.

    Salon keeps the portal's restore token so the consent dialog only ever
    appears once; dropping it is how that grant is withdrawn from this side.
    The desktop's own privacy settings can revoke it independently, which is
    why a token that stops working is discarded rather than retried.
    """
    if not settings.get_string("remote-desktop-restore-token"):
        context.toast("There's no remote-control permission to forget.")
        return
    settings.set_string("remote-desktop-restore-token", "")
    context.toast("Forgotten. You'll be asked again the next time it's needed.")
    context.rebuild()


def _gamepad_panel(context: SettingsContext) -> Panel:
    """§6.8's gamepad visualiser: show the `Action` stream as it arrives.

    The value of this is diagnostic — when a controller "doesn't work", this
    is what distinguishes "the pad sends nothing" from "the pad sends
    something Salon doesn't map".
    """

    def build() -> list[SettingsRow]:
        return [
            InfoRow(
                "Press anything on the controller",
                "",
                detail="Recent actions appear below, newest first",
            ),
            *(
                InfoRow(entry, "")
                for entry in (context.notes[:8] or ["Nothing received yet"])
            ),
        ]

    return Panel(title="Controller test", build=build)


# --- browser -------------------------------------------------------------


def browser_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        detected = launcher.detect_browser()
        configured = settings.get_string("browser-command")
        return [
            TextRow(
                "Browser command",
                lambda: configured,
                lambda: _edit_browser(context, settings),
                placeholder="Autodetect",
                detail=(
                    " ".join(detected)
                    if detected
                    else "No browser found. Install Google Chrome to open web services."
                ),
            ),
            InfoRow(
                "Detected",
                " ".join(detected) if detected else "None",
                detail="Chrome, then Chromium, then the Flatpak, in that order",
            ),
            TextRow(
                "Extra flags",
                lambda: " ".join(settings.get_strv("browser-extra-flags")),
                lambda: _edit_flags(context, settings),
                placeholder="None",
                detail="Appended after the flags Salon computes for each tile",
            ),
            InfoRow(
                "Streaming quality",
                "720p maximum",
                detail=(
                    "Chrome on Linux uses software Widevine, so Netflix and "
                    "others cap resolution. This is a licensing limit, not a setting."
                ),
            ),
        ]

    return Panel(title="Browser", build=build, icon_name="web-browser-symbolic")


def _edit_browser(context: SettingsContext, settings: Gio.Settings) -> None:
    def done(value: str | None) -> None:
        if value is None:
            return
        settings.set_string("browser-command", value.strip())
        context.rebuild()

    context.edit_text(
        "Browser command (empty to autodetect)", settings.get_string("browser-command"), done
    )


def _edit_flags(context: SettingsContext, settings: Gio.Settings) -> None:
    def done(value: str | None) -> None:
        if value is None:
            return
        settings.set_strv("browser-extra-flags", value.split())
        context.rebuild()

    context.edit_text(
        "Extra browser flags, space separated",
        " ".join(settings.get_strv("browser-extra-flags")),
        done,
    )


# --- audio ---------------------------------------------------------------


def audio_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    """§8 calls the wrong HDMI sink a top-three real-world failure on an
    HTPC, so the picker is one level deep and shows the current output by
    name rather than hiding it behind a submenu."""
    sinks: list[audio.Sink] = []

    def build() -> list[SettingsRow]:
        audio.list_sinks(_on_sinks)
        current = settings.get_string("audio-sink")
        rows: list[SettingsRow] = [
            InfoRow(
                "Current output",
                next((s.description for s in sinks if s.is_default), current or "System default"),
            ),
            RangeRow(
                "Volume step",
                lambda: float(settings.get_int("volume-step-percent")),
                _set_step,
                minimum=1,
                maximum=25,
                step=1,
                fmt=lambda v: f"{v:.0f}%",
            ),
        ]
        if not sinks:
            rows.append(InfoRow("No outputs found", "", detail="Is PipeWire running?"))
        for sink in sinks:
            rows.append(
                ActionRow(
                    sink.description,
                    lambda s=sink: _select_sink(context, settings, s),
                    value="●" if sink.is_default else "",
                )
            )
        return rows

    def _set_step(value: float) -> None:
        settings.set_int("volume-step-percent", int(value))
        audio.set_volume_step(int(value))

    def _on_sinks(found: list[audio.Sink]) -> None:
        if [s.id for s in found] == [s.id for s in sinks]:
            return
        sinks[:] = found
        context.rebuild()

    return Panel(title="Audio", build=build, icon_name="audio-speakers-symbolic")


def _select_sink(context: SettingsContext, settings: Gio.Settings, sink: audio.Sink) -> None:
    # Persist the description, not the id: WirePlumber node ids are not
    # stable across reboots, so the id is re-resolved on each startup.
    settings.set_string("audio-sink", sink.description)
    audio.set_default_sink(sink.id, lambda: context.rebuild())
    context.toast(f"Output set to {sink.description}")


# --- system --------------------------------------------------------------


def system_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    from salon.services import power

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = [
            ActionRow(
                "Display and resolution",
                lambda: context.open_control_center("display"),
                detail="Resolution, refresh rate and scaling",
            ),
            ActionRow(
                "Date and time",
                lambda: context.open_control_center("datetime"),
                detail="What the clock in the top bar shows",
            ),
            ActionRow(
                "Region and language",
                lambda: context.open_control_center("region"),
            ),
            ActionRow(
                "Accessibility",
                lambda: context.open_control_center("a11y"),
                detail="Larger text, high contrast, screen reader",
            ),
            ActionRow(
                "Power and screen blanking",
                lambda: context.open_control_center("power"),
            ),
            ActionRow(
                "Software updates",
                lambda: _open_updates(context),
                detail=(
                    "Opens GNOME Software"
                    if shutil.which("gnome-software")
                    else "GNOME Software isn't installed"
                ),
            ),
            ToggleRow(
                "Start Salon at login",
                lambda: settings.get_boolean("autostart"),
                lambda value: _set_autostart(context, settings, value),
            ),
            RangeRow(
                "Keep screen awake after launching",
                lambda: float(settings.get_int("idle-inhibit-seconds")),
                lambda value: settings.set_int("idle-inhibit-seconds", int(value)),
                minimum=0,
                maximum=600,
                step=15,
                fmt=lambda v: "Off" if v == 0 else f"{v:.0f} s",
                detail="Covers the gap before the app issues its own inhibit",
            ),
        ]
        # Named in the failure message, because logind refusing to suspend
        # and Salon never having asked look identical from the sofa.
        def fail(what: str) -> Callable[[str], None]:
            return lambda message: context.toast(f"{what} didn't happen: {message}")

        if power.can_suspend():
            rows.append(ActionRow("Suspend", lambda: power.suspend(fail("Suspend"))))
        if power.can_reboot():
            rows.append(
                ActionRow("Restart", lambda: power.reboot(fail("Restart")), danger=True)
            )
        if power.can_power_off():
            rows.append(
                ActionRow("Shut Down", lambda: power.power_off(fail("Shut down")), danger=True)
            )
        rows.append(ActionRow("Exit to desktop", context.quit_app, danger=True))
        return rows

    return Panel(title="System", build=build, icon_name="preferences-system-symbolic")


def _open_updates(context: SettingsContext) -> None:
    if not shutil.which("gnome-software"):
        context.toast("GNOME Software isn't installed, so updates can't be opened from here.")
        return
    try:
        Gio.Subprocess.new(
            ["gnome-software", "--mode=updates"],
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
        )
    except GLib.Error as exc:
        context.toast(f"Couldn't open GNOME Software: {exc.message}")


def _set_autostart(context: SettingsContext, settings: Gio.Settings, enabled: bool) -> None:
    settings.set_boolean("autostart", enabled)
    path = GLib.build_filenamev(
        [GLib.get_user_config_dir(), "autostart", "rocks.salon.Salon.desktop"]
    )
    entry = Gio.File.new_for_path(path)
    if not enabled:
        try:
            entry.delete(None)
        except GLib.Error:
            pass  # already gone, which is the state we wanted
        return
    # Under Flatpak `salon` is not on the host's PATH — the autostart entry
    # runs in the host session, so it has to go back in through flatpak run.
    app_id = sandbox.app_id() or "rocks.salon.Salon"
    exec_line = f"flatpak run {app_id}" if sandbox.in_flatpak() else "salon"
    contents = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Salon\n"
        f"Exec={exec_line}\n"
        "Icon=rocks.salon.Salon\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    try:
        parent = entry.get_parent()
        if parent is not None:
            parent.make_directory_with_parents(None)
    except GLib.Error:
        pass  # the directory already exists
    try:
        entry.replace_contents(
            contents.encode(), None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None
        )
    except GLib.Error as exc:
        context.toast(f"Couldn't write the autostart entry: {exc.message}")


# --- about ---------------------------------------------------------------


def about_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            InfoRow("Version", context.version),
            InfoRow("Tiles", context.config_path, detail="Edit by hand any time; it hot-reloads"),
            InfoRow("Artwork drop folder", _artwork_dir()),
            ActionRow(
                "Open config folder",
                lambda: _open_folder(context),
                detail="Opens in the desktop file manager",
            ),
            InfoRow(
                "Streaming",
                "720p on Linux",
                detail=(
                    "Chrome uses software Widevine here, so Netflix, Prime Video "
                    "and Disney+ cap resolution. No setting changes it."
                ),
            ),
        ]

    return Panel(title="About", build=build, icon_name="help-about-symbolic")


def _artwork_dir() -> str:
    from salon.services.artwork import artwork_drop_dir

    return str(artwork_drop_dir())


def _open_folder(context: SettingsContext) -> None:
    folder = GLib.path_get_dirname(context.config_path)
    try:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(folder).get_uri(), None)
    except GLib.Error as exc:
        context.toast(f"Couldn't open {folder}: {exc.message}")

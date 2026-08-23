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

from salon import config as app_config  # noqa: E402
from salon.core import sandbox, tokens  # noqa: E402
from salon.input.actions import Action  # noqa: E402
from salon.services import artwork, audio, bluetooth, launcher, netinfo, wifi  # noqa: E402
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


_THEMES: tuple[tuple[str, str], ...] = (
    ("midnight", "Midnight"),
    ("graphite", "Graphite"),
    ("ember", "Ember"),
    ("contrast", "High contrast"),
)


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


# --- appearance ----------------------------------------------------------


def appearance_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            ChoiceRow(
                "Theme",
                _THEMES,
                lambda: settings.get_string("theme"),
                lambda value: settings.set_string("theme", value),
                detail="What colour the surfaces and text are. The accent is separate.",
                preview=True,
            ),
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
            RangeRow(
                "Idle screen",
                lambda: float(settings.get_int("screensaver-minutes")),
                lambda value: settings.set_int("screensaver-minutes", int(value)),
                minimum=0,
                maximum=60,
                step=5,
                fmt=lambda v: "Never" if v == 0 else f"After {v:.0f} min",
                detail="Fades to a drifting clock. Salon's session has no screen lock to do it.",
            ),
            ToggleRow(
                "Reduced motion",
                lambda: settings.get_boolean("reduced-motion"),
                lambda value: settings.set_boolean("reduced-motion", value),
                detail="Focus changes instantly; the highlight stays unmistakable",
            ),
            TextRow(
                "Background image",
                lambda: settings.get_string("wallpaper-path") or "None",
                lambda: _edit_wallpaper(context, settings),
                detail="A picture, or a folder of them to rotate. Leave empty for none.",
            ),
            RangeRow(
                "Background dimming",
                lambda: settings.get_double("wallpaper-dim"),
                lambda value: settings.set_double("wallpaper-dim", value),
                minimum=0.0,
                maximum=1.0,
                step=0.04,
                fmt=lambda v: "Hidden" if v >= 0.999 else _percent(v),
                detail="How far the background image is pushed behind the tiles",
                preview=True,
            ),
            ToggleRow(
                "Use each site's own icon",
                lambda: settings.get_boolean("fetch-site-icons"),
                lambda value: settings.set_boolean("fetch-site-icons", value),
                detail="Web tiles ask their own site for its icon, once. Off makes them all alike.",
            ),
            ActionRow(
                "Forget fetched site icons",
                lambda: _forget_site_icons(context),
                detail="Ask every site again the next time its tile is drawn",
            ),
        ]

    return Panel(
        title="Appearance",
        build=build,
        panel_id="appearance",
        icon_name="applications-graphics-symbolic",
    )


# --- network -------------------------------------------------------------


def _edit_wallpaper(context: SettingsContext, settings: Gio.Settings) -> None:
    def done(value: str | None) -> None:
        if value is None:
            return
        settings.set_string("wallpaper-path", value.strip())
        context.rebuild()

    context.edit_text(
        "Path to an image, or a folder of images",
        settings.get_string("wallpaper-path"),
        done,
    )


def _forget_site_icons(context: SettingsContext) -> None:
    """Drop the guessed icons without touching artwork the user chose.

    They live in their own directory precisely so this can be one removal:
    a site that has since changed its logo, or one that was asked before it
    had an icon at all, is otherwise cached for good.
    """
    directory = artwork.site_icon_cache_dir()
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        context.toast("There were no fetched icons to forget.")
        return
    except OSError as error:
        context.toast(f"Couldn't clear the icon cache: {error.strerror or error}")
        return
    context.toast("Fetched site icons cleared. They'll be asked for again.")
    context.rebuild()


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
                "Choose a network",
                lambda: context.push(_wifi_panel(context)),
                detail="Every network in range, and its password if it needs one",
                value="›",
            ),
            ActionRow(
                "Wi-Fi, in detail",
                lambda: context.open_control_center("wifi"),
                detail="Enterprise logins, hidden networks and static addresses",
            ),
            ActionRow(
                "Wired and VPN",
                lambda: context.open_control_center("network"),
                detail="Ethernet, VPN and proxy settings",
            ),
        ]

    return Panel(
        title="Network", build=build, panel_id="network", icon_name="network-wireless-symbolic"
    )


def _wifi_panel(context: SettingsContext) -> Panel:
    """The list of networks in range.

    Rebuilt from a cached scan rather than rescanning on every rebuild: the
    panel rebuilds whenever anything changes, a scan takes seconds, and a
    list that reshuffles itself under the cursor as signal strengths drift
    is unusable with a D-pad.
    """
    service = wifi.WifiService()
    state: dict[str, object] = {"points": [], "error": "", "scanned": False, "asking": False}

    def on_scanned(points: list[wifi.AccessPoint], error: str) -> None:
        state.update(points=points, error=error, scanned=True, asking=False)
        context.rebuild()

    def request() -> None:
        # Guarded: `build` runs on every rebuild, and a rebuild that starts
        # another scan which finishes and rebuilds again is a loop.
        if state["asking"]:
            return
        state["asking"] = True
        service.list_networks(on_scanned)

    def rescan() -> None:
        state["scanned"] = False
        request()
        context.rebuild()

    def build() -> list[SettingsRow]:
        if not state["scanned"]:
            request()
            return [InfoRow("Looking for networks…", "", detail="This takes a few seconds")]
        error = str(state["error"])
        if error:
            return [
                InfoRow("Couldn't look for networks", "", detail=error),
                ActionRow("Try again", rescan),
            ]
        points = list(state["points"])  # type: ignore[arg-type]
        if not points:
            return [
                InfoRow("Nothing in range", "", detail="No wireless networks were found"),
                ActionRow("Look again", rescan),
            ]
        rows: list[SettingsRow] = [
            ActionRow(
                point.ssid,
                lambda p=point: _join(context, service, p),
                value=point.summary,
                icon_name=point.icon_name,
            )
            for point in points
        ]
        rows.append(ActionRow("Look again", rescan, detail="Scan for networks once more"))
        return rows

    return Panel(title="Wi-Fi", build=build)


def _join(context: SettingsContext, service: wifi.WifiService, point: wifi.AccessPoint) -> None:
    """Join one network, asking for the password only if it wants one."""

    def attempt(password: str) -> None:
        context.toast(f"Connecting to {point.ssid}…")
        service.connect(point, password, on_result)

    def on_result(ok: bool, message: str) -> None:
        context.toast(message if ok else f"Couldn't join {point.ssid}: {message}")

    if not point.secured:
        attempt("")
        return

    def got_password(value: str | None) -> None:
        if value is None:
            return
        attempt(value)

    context.edit_text(f"Password for {point.ssid}", "", got_password)


# --- input ---------------------------------------------------------------


def input_panel(context: SettingsContext, settings: Gio.Settings) -> Panel:
    def build() -> list[SettingsRow]:
        return [
            ToggleRow(
                "Use a phone as the remote",
                context.phone_remote_running,
                lambda value: _set_phone_remote(context, value),
                detail=context.phone_remote_hint(),
            ),
            ActionRow(
                "Pair a remote or controller",
                lambda: context.push(_bluetooth_panel(context)),
                detail="Bluetooth, without needing a mouse to do it",
                value="›",
            ),
            ActionRow(
                "Bluetooth, in detail",
                lambda: context.open_control_center("bluetooth"),
                detail="Devices needing a typed PIN, and everything else",
            ),
            ActionRow(
                "Change buttons",
                lambda: context.push(_bindings_panel(context)),
                detail="Bind any button on a controller, keyboard or TV remote",
                value="›",
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

    return Panel(title="Input", build=build, panel_id="input", icon_name="input-gaming-symbolic")


def _set_phone_remote(context: SettingsContext, enabled: bool) -> None:
    """Turn the phone remote on or off, and say what happened.

    The failure worth naming is the port being taken — by another copy of
    Salon, or by something else on 8437. A toggle that flips back with no
    explanation is indistinguishable from a broken toggle.
    """
    if not context.set_phone_remote(enabled):
        context.toast("Couldn't start the phone remote — port 8437 is already in use.")
    context.rebuild()


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


def _bluetooth_panel(context: SettingsContext) -> Panel:
    """Scan, list, pair.

    The chicken-and-egg screen: a wireless controller is how you drive
    Salon, and until this existed the only way to pair the first one was a
    mouse. Discovery starts when the panel opens and stops when it closes,
    because an adapter left scanning costs power and floods the list.
    """
    service = bluetooth.BluetoothService()
    state: dict[str, object] = {"devices": [], "error": "", "scanned": False, "asking": False}

    def on_listed(devices: list[bluetooth.Device], error: str) -> None:
        state.update(devices=devices, error=error, scanned=True, asking=False)
        context.rebuild()

    def request() -> None:
        # Guarded, and deliberately not calling context.rebuild(): `build`
        # runs on every rebuild, so a request that rebuilt would call build
        # again, which would request again. That recursion is not
        # theoretical — it was this panel's first version.
        if state["asking"]:
            return
        state["asking"] = True

        def listed(devices: list[bluetooth.Device], error: str) -> None:
            on_listed(devices, error)
            # Discovery can only start once an adapter has been found, so
            # it is chained behind the listing rather than run beside it.
            if not error:
                service.start_discovery(lambda ok, message: None)

        service.list_devices(listed)

    def rescan() -> None:
        state["scanned"] = False
        request()
        context.rebuild()

    def pair(device: bluetooth.Device) -> None:
        context.toast(f"Pairing {device.name}…")

        def paired(ok: bool, message: str) -> None:
            context.toast(message)
            state["scanned"] = False
            request()

        service.pair(device, paired)

    def build() -> list[SettingsRow]:
        if not state["scanned"]:
            request()
            return [
                InfoRow(
                    "Looking for devices…",
                    "",
                    detail="Put the controller or remote into pairing mode now",
                )
            ]
        error = str(state["error"])
        if error:
            return [
                InfoRow("Couldn't look for devices", "", detail=error),
                ActionRow("Try again", rescan),
            ]
        devices = list(state["devices"])  # type: ignore[arg-type]
        rows: list[SettingsRow] = [
            ActionRow(
                device.name,
                lambda d=device: pair(d),
                value=device.summary,
                detail=device.kind,
            )
            for device in devices
        ]
        if not rows:
            rows.append(
                InfoRow(
                    "Nothing found yet",
                    "",
                    detail="Hold the controller's pairing button until its light flashes",
                )
            )
        rows.append(ActionRow("Look again", rescan, detail="Scan for another few seconds"))
        return rows

    return Panel(title="Pair a device", build=build)


# The actions worth putting on a settings screen. Deliberately not every
# member of the enum: nobody needs to rebind "up", and offering to would
# make the list twice as long and half as useful. The directions come from
# a D-pad, a stick, arrow keys and a CEC pad, all of which agree.
_BINDABLE: tuple[tuple[Action, str], ...] = (
    (Action.OK, "Choose the highlighted thing"),
    (Action.BACK, "Go back one step"),
    (Action.MENU, "System menu, and the way out of an app"),
    (Action.OPTIONS, "The menu for the thing under the cursor"),
    (Action.SEARCH, "Open search"),
    (Action.PLAY_PAUSE, "Pause or resume whatever is playing"),
    (Action.PREV_GROUP, "Jump back a letter or a group"),
    (Action.NEXT_GROUP, "Jump on a letter or a group"),
    (Action.VOLUME_UP, "Louder"),
    (Action.VOLUME_DOWN, "Quieter"),
    (Action.MUTE, "Silence"),
)

_SOURCE_NAMES = {"pad": "Controller", "key": "Keyboard", "cec": "TV remote"}


def _bindings_panel(context: SettingsContext) -> Panel:
    """One row per action, showing what the user has bound to it.

    Shows overrides only, and says so: listing the defaults as well would
    mean printing "Cross / A / the bottom face button" for OK and inviting
    the reader to work out which of those their controller has. What this
    screen answers is "what have I changed", and the row for an action
    nobody has rebound says "Default".
    """

    def described(action: Action) -> str:
        bindings = context.bindings()
        keys = bindings.keys_for(action.value)  # type: ignore[attr-defined]
        if not keys:
            return "Default"
        labels = []
        for key in keys:
            source, _, code = key.partition(":")
            labels.append(f"{_SOURCE_NAMES.get(source, source)} 0x{int(code):X}")
        return ", ".join(labels)

    def build() -> list[SettingsRow]:
        rows: list[SettingsRow] = [
            InfoRow(
                "Press the button you want",
                "",
                detail="Choose an action, then press any button on any remote or controller",
            )
        ]
        rows.extend(
            ActionRow(
                action.value.replace("_", " ").upper(),
                lambda a=action: context.push(_capture_panel(context, a)),
                detail=f"{note} · {described(action)}",
                value="›",
            )
            for action, note in _BINDABLE
        )
        rows.append(
            ActionRow(
                "Use Salon's defaults again",
                lambda: _reset_bindings(context),
                detail="Forgets every button you have changed",
            )
        )
        return rows

    return Panel(title="Change buttons", build=build)


def _capture_panel(context: SettingsContext, action: Action) -> Panel:
    """Waits for one press, binds it, and pops itself.

    A panel rather than a dialog because BACK has to be able to get out of
    it — and BACK is itself a bindable button, so the capture is armed only
    while this panel is on screen and is cancelled on the way out.
    """
    captured: list[str] = []

    def on_captured(source: str, code: int) -> None:
        context.rebind(source, code, action.value)
        captured.append(f"{_SOURCE_NAMES.get(source, source)} 0x{code:X}")
        context.toast(f"{action.value.replace('_', ' ').upper()} is now {captured[-1]}.")
        context.pop()

    def build() -> list[SettingsRow]:
        context.capture_binding(on_captured)
        return [
            InfoRow(
                f"Press the button for {action.value.replace('_', ' ').upper()}",
                "Waiting…",
                detail="Any controller, keyboard or TV remote. LEFT cancels.",
            )
        ]

    return Panel(title="Waiting for a button", build=build)


def _reset_bindings(context: SettingsContext) -> None:
    context.reset_bindings()
    context.toast("Every button is back to Salon's default.")
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

    return Panel(
        title="Browser", build=build, panel_id="browser", icon_name="web-browser-symbolic"
    )


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

    return Panel(
        title="Audio", build=build, panel_id="audio", icon_name="audio-speakers-symbolic"
    )


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

    return Panel(
        title="System", build=build, panel_id="system", icon_name="preferences-system-symbolic"
    )


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
        [GLib.get_user_config_dir(), "autostart", f"{app_config.APP_ID}.desktop"]
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
    app_id = sandbox.app_id() or app_config.APP_ID
    exec_line = f"flatpak run {app_id}" if sandbox.in_flatpak() else "salon"
    contents = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Salon\n"
        f"Exec={exec_line}\n"
        f"Icon={app_config.APP_ID}\n"
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

    return Panel(title="About", build=build, panel_id="about", icon_name="help-about-symbolic")


def _artwork_dir() -> str:
    from salon.services.artwork import artwork_drop_dir

    return str(artwork_drop_dir())


def _open_folder(context: SettingsContext) -> None:
    folder = GLib.path_get_dirname(context.config_path)
    try:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(folder).get_uri(), None)
    except GLib.Error as exc:
        context.toast(f"Couldn't open {folder}: {exc.message}")

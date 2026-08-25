# SPDX-License-Identifier: GPL-3.0-or-later
"""Pointer, click and keyboard injection, by two routes.

Wayland forbids one app from injecting input into another app's window
directly (unlike X11's XTestFakeInput), so this goes through the
compositor. There are two ways to ask, and Salon tries them in this order:

1. **`org.gnome.Mutter.RemoteDesktop`** — mutter's own interface, on the
   session bus, owned by gnome-shell (or gnome-kiosk; both link the same
   libmutter, which is where the name lives). `CreateSession` + `Start` is
   two synchronous calls, about 4 ms, **and no consent dialog at all** —
   the dialog belongs to xdg-desktop-portal-gnome, which is a *client* of
   this interface rather than a layer beneath it. This is the same door
   gnome-remote-desktop goes through.
2. **`org.freedesktop.portal.RemoteDesktop`** — the sandboxed, public
   route, which asks the user for consent.

The order exists because of a deadlock, not a preference. Salon is a
ten-foot interface whose *first* input device is often the phone it has not
paired yet: fresh appliance, no controller, no keyboard, no mouse. The
phone's D-pad arrives over HTTP into Salon's own process and needs no
grant — but the trackpad and `/type` need input injection, so Salon asks
the portal, and the portal puts a two-button dialog on the television that
**can only be dismissed with the pointer the dialog is gating**. The one
device that could answer it is the one being asked about. No amount of
token persistence fixes that: `persist_mode` skips the second dialog and
every one after it, never the first.

So the mutter route is not an optimisation. It is the only route that a
machine with no input devices can complete unattended. The portal remains
the fallback for everything else — a non-mutter compositor, or the Flatpak
build, whose sandbox has no business holding a name that grants
system-wide input injection (see `input-injection` in the schema, which
forces the portal for anyone who wants that boundary back).

**The portal's consent dialog is shown once, ever.** RemoteDesktop portal version 2
added `persist_mode` and `restore_token` (the same mechanism screen-sharing
tools use so they don't re-prompt every call). Salon asks for
`PERSIST_EXPLICITLY_REVOKED`, keeps the token the portal hands back, and
passes it to `SelectDevices` next time; the portal then restores the grant
silently. Without this the dialog appears on *every* browser launch, landing
on top of whatever the user just opened.

The same session carries a keyboard, which is what lets the phone type into
a *launched* application (`type_text`). Salon's own on-screen keyboard fills
in Salon's own fields; the one text box that genuinely cannot be avoided on
a television is a search box inside a browser tile, and that belongs to
another process. The devices were always both requested in `SelectDevices`;
until now only the pointer half was used.

The token is deliberately stored by the caller (GSettings) rather than here:
this class holds no policy, and clearing that key is how the grant is given
back. A token the portal no longer honours is dropped on failure so the next
attempt starts clean rather than retrying a dead grant forever.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, GLib  # noqa: E402

_BUS_NAME = "org.freedesktop.portal.Desktop"
_OBJECT_PATH = "/org/freedesktop/portal/desktop"
_RD_IFACE = "org.freedesktop.portal.RemoteDesktop"
_REQUEST_IFACE = "org.freedesktop.portal.Request"

# mutter's own interface. Version 1, unchanged since it was introduced, and
# load-bearing for gnome-remote-desktop — but private, so it is tried and
# not assumed, and any failure falls through to the portal.
_MUTTER_BUS = "org.gnome.Mutter.RemoteDesktop"
_MUTTER_PATH = "/org/gnome/Mutter/RemoteDesktop"
_MUTTER_IFACE = "org.gnome.Mutter.RemoteDesktop"
_MUTTER_SESSION_IFACE = "org.gnome.Mutter.RemoteDesktop.Session"

# The handshake is two blocking calls on the main loop, so it needs a bound
# that is short enough not to be felt. gnome-shell answers in single-digit
# milliseconds when it is going to answer at all; a shell that is wedged is
# not going to become responsive within a second either.
_MUTTER_TIMEOUT_MS = 2000

# MetaRemoteDesktopSessionAxisFlags. The portal spells this as a `finish`
# option in an a{sv}; mutter spells it as a bit.
_AXIS_FINISH = 1 << 0

# Values of the `input-injection` GSettings key.
BACKEND_AUTO = "auto"
BACKEND_PORTAL = "portal"
BACKEND_MUTTER = "mutter"

_DEVICE_POINTER = 1
_DEVICE_KEYBOARD = 2

# org.freedesktop.portal.RemoteDesktop v2 persist modes.
_PERSIST_NONE = 0
_PERSIST_WHILE_RUNNING = 1
_PERSIST_EXPLICITLY_REVOKED = 2

# persist_mode/restore_token only exist from version 2 of the interface.
# On an older portal both are ignored and the dialog appears every time,
# which is the pre-existing behaviour rather than a failure.
_RD_VERSION_WITH_PERSIST = 2

BTN_LEFT = 0x110
# linux/input-event-codes.h again, and in that header's own order: RIGHT is
# 0x111 and MIDDLE is 0x112. The portal takes evdev button codes directly,
# so these are the same numbers a real mouse reports.
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112

BUTTONS = {"left": BTN_LEFT, "right": BTN_RIGHT, "middle": BTN_MIDDLE}

_PRESSED = 1
_RELEASED = 0

# X11 keysyms for the keys a phone keyboard sends that are not characters.
# Everything else goes through Gdk rather than a rule written out here.
# The rule looks simple — codepoint below U+0100, `0x01000000 + codepoint`
# above — and is wrong in the middle: plenty of characters above Latin-1
# have *legacy named* keysyms that the keymap is indexed by, so the arrow
# in a URL would have been typed as something else. Gdk owns that table and
# xkb agrees with it; restating it here would be a second copy to be wrong.
_KEYSYMS = {
    "\n": 0xFF0D,  # Return
    "\r": 0xFF0D,
    "\t": 0xFF09,  # Tab
    "\b": 0xFF08,  # BackSpace
    "\x7f": 0xFFFF,  # Delete
}

# Between the press and the release of one key, and between one key and the
# next. Zero works against a toolkit reading an event stream and does not
# work against a web page doing its own key handling with a debounce — and
# a search box in a browser is the whole reason this path exists.
_KEY_GAP_MS = 12


def keysym_for(character: str) -> int | None:
    """The X11 keysym for one character, or None if there isn't one."""
    if character in _KEYSYMS:
        return _KEYSYMS[character]
    codepoint = ord(character)
    if codepoint < 0x20:
        # A control character with no named key in the table above. Sending
        # it as a Unicode keysym would type an invisible glyph rather than
        # do nothing, which is worse.
        return None
    keyval = int(Gdk.unicode_to_keyval(codepoint))
    return keyval or None


class PointerInjector:
    """Lazily negotiates a RemoteDesktop portal session, then injects
    relative pointer motion and clicks system-wide.

    start() is idempotent and safe to call repeatedly (e.g. every time
    pointer mode is entered) — it only does the handshake once.
    """

    def __init__(
        self,
        on_ready: Callable[[bool], None] | None = None,
        *,
        load_restore_token: Callable[[], str] | None = None,
        save_restore_token: Callable[[str], None] | None = None,
        backend: str = BACKEND_AUTO,
    ) -> None:
        self._connection: Gio.DBusConnection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._session_handle: str | None = None
        self._started = False
        self._preference = backend
        # "" until something has actually started; then "mutter" or "portal".
        self._backend = ""
        self._mutter_session: str | None = None
        self._closed_sub: int | None = None
        self._parent_window = ""
        self._starting = False
        self._timeout_id: int | None = None
        self._on_ready = on_ready
        self._load_restore_token = load_restore_token
        self._save_restore_token = save_restore_token
        self._used_restore_token = ""

    @property
    def ready(self) -> bool:
        """Whether input can actually be injected *right now*.

        Deliberately not "is there a session handle": the portal hands one
        back at CreateSession, which is three round trips and possibly a
        consent dialog before Start says yes. Taking the handle as the
        answer meant `ready` was True through that whole window — so the
        phone's keyboard tab said "typing goes to whatever is open on the
        television", `/type` answered 200, and mutter dropped every keysym
        on the floor because the session had never been started. A grant
        that is still being asked for is not a grant.
        """
        return self._session_handle is not None and self._started

    @property
    def backend(self) -> str:
        """Which route is actually carrying input: "mutter", "portal", or ""
        for "nothing is running". Settings shows this, because "remote
        control is working" and "the desktop was asked for permission" are
        different facts and only one of them is visible on screen."""
        return self._backend

    def start(self, parent_window: str = "") -> None:
        """Begin the portal handshake. parent_window should be a handle from
        Gdk export_handle (e.g. "wayland:HANDLE") so the consent dialog is
        properly anchored to Salon's window instead of appearing unparented
        — xdg-desktop-portal logs "Failed to associate portal window with
        parent window" and the dialog may not be reliably visible without
        it. Empty string is legal (no parent) but not recommended."""
        if self._session_handle is not None or self._starting:
            return
        self._starting = True
        self._parent_window = parent_window
        if self._preference != BACKEND_PORTAL and self._start_mutter():
            self._starting = False
            self._backend = "mutter"
            self._started = True
            # Worth a line in the journal: which route carried input is
            # invisible from the screen, and the two differ in exactly the
            # thing anyone debugging this cares about — whether a consent
            # dialog is about to appear.
            print("[pointer] Injecting input via mutter directly; no consent dialog needed.")
            if self._on_ready is not None:
                self._on_ready(True)
            return
        if self._preference == BACKEND_MUTTER:
            # Explicitly asked for the one route that just failed. Falling
            # through to the portal here would put the dialog on screen
            # that this setting exists to avoid.
            print("[pointer] input-injection=mutter, but mutter's interface did not answer.")
            self._starting = False
            self._fail()
            return
        self._timeout_id = GLib.timeout_add_seconds(20, self._on_timeout)
        self._create_session()

    # --- mutter's own interface ---------------------------------------

    def _start_mutter(self) -> bool:
        """CreateSession + Start against gnome-shell. True if input can be
        injected when this returns.

        Deliberately synchronous. It is two round trips to a process that
        answers in a few milliseconds, and making it async would mean
        carrying a second half-built-session state through the portal
        fallback for no gain. A compositor that is not mutter simply has no
        such bus name and `call_sync` fails immediately.
        """
        try:
            result = self._connection.call_sync(
                _MUTTER_BUS,
                _MUTTER_PATH,
                _MUTTER_IFACE,
                "CreateSession",
                None,
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE,
                _MUTTER_TIMEOUT_MS,
                None,
            )
            session = str(result.unpack()[0])
            self._connection.call_sync(
                _MUTTER_BUS,
                session,
                _MUTTER_SESSION_IFACE,
                "Start",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                _MUTTER_TIMEOUT_MS,
                None,
            )
        except GLib.Error as error:
            # Not a failure worth a user-facing word: on a non-GNOME
            # compositor this is the expected answer, and the portal is
            # about to be tried.
            print(f"[pointer] mutter's RemoteDesktop is not available ({error.message}).")
            return False
        self._mutter_session = session
        self._session_handle = session
        # A session dies with the compositor. gnome-shell restarting would
        # otherwise leave `ready` True over a session that no longer exists,
        # and every press after that would go nowhere in silence.
        self._closed_sub = self._connection.signal_subscribe(
            _MUTTER_BUS,
            _MUTTER_SESSION_IFACE,
            "Closed",
            session,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_mutter_closed,
        )
        return True

    def _on_mutter_closed(self, *_args: object) -> None:
        print("[pointer] mutter closed the remote-desktop session.")
        self._fail()

    def _mutter_call(self, method: str, args: GLib.Variant | None) -> None:
        if self._mutter_session is None:
            return
        self._connection.call(
            _MUTTER_BUS,
            self._mutter_session,
            _MUTTER_SESSION_IFACE,
            method,
            args,
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )

    def _on_timeout(self) -> bool:
        print(
            "[pointer] RemoteDesktop request timed out after 20s — the consent "
            "dialog was probably left unanswered."
        )
        self._timeout_id = None
        self._fail()
        return GLib.SOURCE_REMOVE

    def _clear_timeout(self) -> None:
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def move(self, dx: float, dy: float) -> None:
        if not self.ready:
            return
        if self._backend == "mutter":
            self._mutter_call("NotifyPointerMotionRelative", GLib.Variant("(dd)", (dx, dy)))
            return
        self._connection.call(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "NotifyPointerMotion",
            GLib.Variant("(oa{sv}dd)", (self._session_handle, {}, dx, dy)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )

    def scroll(self, dx: float, dy: float) -> None:
        """Two fingers on the phone's trackpad, as a scroll wheel.

        `NotifyPointerAxis` and not `NotifyPointerAxisDiscrete`: the
        discrete call moves in whole wheel clicks, which is what a mouse
        does and not what a finger does — a page scrolled that way jumps in
        three-line steps under a gesture that is continuous. The `finish`
        option is what tells the compositor a fling has ended, so kinetic
        scrolling in GTK and in a browser stops when the fingers lift
        rather than drifting on.
        """
        if not self.ready or not (dx or dy):
            return
        if self._backend == "mutter":
            self._mutter_call("NotifyPointerAxis", GLib.Variant("(ddu)", (dx, dy, 0)))
            return
        self._connection.call(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "NotifyPointerAxis",
            GLib.Variant("(oa{sv}dd)", (self._session_handle, {}, dx, dy)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )

    def scroll_finish(self) -> None:
        """Tell the compositor the fingers have left the glass."""
        if not self.ready:
            return
        if self._backend == "mutter":
            self._mutter_call(
                "NotifyPointerAxis", GLib.Variant("(ddu)", (0.0, 0.0, _AXIS_FINISH))
            )
            return
        self._connection.call(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "NotifyPointerAxis",
            GLib.Variant(
                "(oa{sv}dd)",
                (self._session_handle, {"finish": GLib.Variant("b", True)}, 0.0, 0.0),
            ),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )

    def press(self, button: int = BTN_LEFT) -> None:
        """Hold a button down. Pairs with `release`, and exists for the
        drag gestures — a tap that presses and releases 50ms later cannot
        move a window or select a line of text."""
        if not self.ready:
            return
        self._notify_button(button, _PRESSED)

    def release(self, button: int = BTN_LEFT) -> None:
        if not self.ready:
            return
        self._notify_button(button, _RELEASED)

    def type_text(self, text: str) -> bool:
        """Type `text` into whatever currently has keyboard focus.

        Not into Salon — into the *session*. This is how the phone keyboard
        reaches a search box inside a launched browser, which is the one
        place text entry on a television is genuinely unavoidable and the
        one place Salon's own on-screen keyboard cannot help.

        Returns whether there was a session to type into at all. What it
        cannot promise is that every character arrives: the compositor maps
        each keysym onto the *current* keyboard layout, so a character that
        layout cannot produce is dropped by mutter rather than by us. For a
        search box that is nearly always fine and occasionally is not.

        The keys are spaced out over the main loop rather than blasted in
        one go — see `_KEY_GAP_MS`.
        """
        if not self.ready:
            return False
        keysyms = [k for k in (keysym_for(c) for c in text) if k is not None]
        if not keysyms:
            # Nothing to send. An empty string is a success (there was
            # nowhere for it to fail); a string of characters that produced
            # no keysym at all is not, and the phone should be told.
            return not text
        for index, keysym in enumerate(keysyms):
            GLib.timeout_add(index * _KEY_GAP_MS * 2, self._tap_keysym, keysym)
        return True

    def _tap_keysym(self, keysym: int) -> bool:
        self._notify_keysym(keysym, _PRESSED)
        GLib.timeout_add(_KEY_GAP_MS, self._notify_keysym, keysym, _RELEASED)
        return GLib.SOURCE_REMOVE

    def _notify_keysym(self, keysym: int, state: int) -> bool:
        if self._backend == "mutter":
            self._mutter_call(
                "NotifyKeyboardKeysym", GLib.Variant("(ub)", (keysym, bool(state)))
            )
            return GLib.SOURCE_REMOVE
        if self._session_handle is not None:
            self._connection.call(
                _BUS_NAME,
                _OBJECT_PATH,
                _RD_IFACE,
                "NotifyKeyboardKeysym",
                GLib.Variant("(oa{sv}iu)", (self._session_handle, {}, keysym, state)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )
        return GLib.SOURCE_REMOVE

    def click(self, button: int = BTN_LEFT) -> None:
        if not self.ready:
            return
        self._notify_button(button, _PRESSED)
        GLib.timeout_add(50, self._notify_button, button, _RELEASED)

    def _notify_button(self, button: int, state: int) -> bool:
        if self._backend == "mutter":
            self._mutter_call(
                "NotifyPointerButton", GLib.Variant("(ib)", (button, bool(state)))
            )
            return GLib.SOURCE_REMOVE
        if self._session_handle is not None:
            self._connection.call(
                _BUS_NAME,
                _OBJECT_PATH,
                _RD_IFACE,
                "NotifyPointerButton",
                GLib.Variant("(oa{sv}iu)", (self._session_handle, {}, button, state)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )
        return GLib.SOURCE_REMOVE

    # --- portal handshake ---------------------------------------------

    def _sender_token(self) -> str:
        unique = self._connection.get_unique_name()
        return unique.lstrip(":").replace(".", "_")

    def _new_token(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _watch_request(
        self, request_path: str, on_response: Callable[[int, dict[str, object]], None]
    ) -> None:
        sub_id_holder: list[int] = []

        def handler(
            connection: Gio.DBusConnection,
            sender: str,
            path: str,
            iface: str,
            signal: str,
            params: GLib.Variant,
        ) -> None:
            code, results = params.unpack()
            self._connection.signal_unsubscribe(sub_id_holder[0])
            on_response(code, results)

        sub_id = self._connection.signal_subscribe(
            _BUS_NAME,
            _REQUEST_IFACE,
            "Response",
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            handler,
        )
        sub_id_holder.append(sub_id)

    def _create_session(self) -> None:
        session_token = self._new_token("salon_rd")
        handle_token = self._new_token("salon_req")
        request_path = (
            f"/org/freedesktop/portal/desktop/request/{self._sender_token()}/{handle_token}"
        )
        self._watch_request(request_path, self._on_session_response(session_token))
        self._connection.call_sync(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "CreateSession",
            GLib.Variant(
                "(a{sv})",
                (
                    {
                        "session_handle_token": GLib.Variant("s", session_token),
                        "handle_token": GLib.Variant("s", handle_token),
                    },
                ),
            ),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_session_response(
        self, session_token: str
    ) -> Callable[[int, dict[str, object]], None]:
        def handler(code: int, results: dict[str, object]) -> None:
            if code != 0:
                self._fail()
                return
            # params.unpack() (in _watch_request) already deep-unpacks the
            # a{sv} dict, so values here are plain Python objects already —
            # not GLib.Variant, despite the a{sv} signature suggesting it.
            handle = results.get("session_handle")
            self._session_handle = handle if isinstance(handle, str) else session_token
            self._select_devices()

        return handler

    def _portal_version(self) -> int:
        try:
            result = self._connection.call_sync(
                _BUS_NAME,
                _OBJECT_PATH,
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", (_RD_IFACE, "version")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except GLib.Error:
            return 1
        return int(result.unpack()[0])

    def _select_devices(self) -> None:
        assert self._session_handle is not None
        handle_token = self._new_token("salon_req")
        request_path = (
            f"/org/freedesktop/portal/desktop/request/{self._sender_token()}/{handle_token}"
        )
        self._watch_request(request_path, self._on_devices_selected)
        options = {
            "types": GLib.Variant("u", _DEVICE_POINTER | _DEVICE_KEYBOARD),
            "handle_token": GLib.Variant("s", handle_token),
        }
        if self._portal_version() >= _RD_VERSION_WITH_PERSIST:
            options["persist_mode"] = GLib.Variant("u", _PERSIST_EXPLICITLY_REVOKED)
            token = self._load_restore_token() if self._load_restore_token else ""
            self._used_restore_token = token
            if token:
                options["restore_token"] = GLib.Variant("s", token)
        self._connection.call_sync(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "SelectDevices",
            GLib.Variant("(oa{sv})", (self._session_handle, options)),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_devices_selected(self, code: int, results: dict[str, object]) -> None:
        if code != 0:
            print(f"[pointer] SelectDevices was denied or failed (code={code}).")
            self._fail()
            return
        self._start_session()

    def _start_session(self) -> None:
        assert self._session_handle is not None
        handle_token = self._new_token("salon_req")
        request_path = (
            f"/org/freedesktop/portal/desktop/request/{self._sender_token()}/{handle_token}"
        )
        self._watch_request(request_path, self._on_started)
        self._connection.call_sync(
            _BUS_NAME,
            _OBJECT_PATH,
            _RD_IFACE,
            "Start",
            GLib.Variant(
                "(osa{sv})",
                (
                    self._session_handle,
                    self._parent_window,
                    {"handle_token": GLib.Variant("s", handle_token)},
                ),
            ),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _on_started(self, code: int, results: dict[str, object]) -> None:
        self._starting = False
        self._clear_timeout()
        if code != 0:
            print(f"[pointer] Start was denied or failed (code={code}) — consent not granted?")
            # A token the portal has stopped honouring (revoked in system
            # settings, or invalidated by a compositor restart) would
            # otherwise be retried forever, and the retry is silent — the
            # user would just see the pointer never work again.
            self._forget_restore_token()
            self._fail()
            return
        self._started = True
        self._backend = "portal"
        print("[pointer] Injecting input via the desktop portal.")
        self._store_restore_token(results.get("restore_token"))
        if self._on_ready is not None:
            self._on_ready(True)

    def _store_restore_token(self, token: object) -> None:
        if self._save_restore_token is None:
            return
        # The portal issues a *fresh* token each time and the old one stops
        # working, so this has to be written on every successful start, not
        # only the first.
        if isinstance(token, str) and token and token != self._used_restore_token:
            self._save_restore_token(token)

    def _forget_restore_token(self) -> None:
        if self._save_restore_token is not None and self._used_restore_token:
            self._save_restore_token("")
        self._used_restore_token = ""

    def _fail(self) -> None:
        self._clear_timeout()
        self._starting = False
        self._started = False
        self._session_handle = None
        self._backend = ""
        self._release_mutter()
        if self._on_ready is not None:
            self._on_ready(False)

    def _release_mutter(self) -> None:
        if self._closed_sub is not None:
            self._connection.signal_unsubscribe(self._closed_sub)
            self._closed_sub = None
        self._mutter_session = None

    def stop(self) -> None:
        """Give the grant back. Only meaningful for the mutter route — the
        portal session is torn down with the bus connection, and its grant
        is persisted on purpose."""
        if self._backend == "mutter" and self._mutter_session is not None:
            self._mutter_call("Stop", None)
        self._release_mutter()
        self._started = False
        self._session_handle = None
        self._backend = ""


_A11Y_SCHEMA = "org.gnome.desktop.a11y.applications"
_OSK_KEY = "screen-keyboard-enabled"


def _a11y_settings() -> Gio.Settings | None:
    """GNOME's accessibility settings, or None where they aren't installed.

    Worth the detour, because `Gio.Settings.new` on a schema that is not
    there does not raise — it is a `g_error`, which aborts the process. So
    on a desktop without gsettings-desktop-schemas, Salon died on the first
    press of Y in pointer mode instead of doing nothing. `screenlock.py`
    guards its own host key the same way, for the same reason.
    """
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(_A11Y_SCHEMA, True) is None:
        return None
    return Gio.Settings.new(_A11Y_SCHEMA)


def set_onscreen_keyboard_enabled(enabled: bool) -> None:
    """Toggle GNOME's built-in accessibility on-screen keyboard.

    We deliberately don't render our own OSK overlay: Salon can't force
    itself above another app's Wayland window, so a custom overlay
    wouldn't reliably show up over Chrome/Netflix/etc. GNOME's a11y
    keyboard is a shell-level surface and isn't bound by that limit — the
    gamepad-driven cursor from PointerInjector can then click its keys
    like a real mouse.

    This is one of the two host keys the Flatpak needs direct dconf access
    for; see the finish-args note in the manifest.
    """
    settings = _a11y_settings()
    if settings is None:
        print("[pointer] No GNOME a11y schema here; leaving the on-screen keyboard alone.")
        return
    settings.set_boolean(_OSK_KEY, enabled)


def onscreen_keyboard_enabled() -> bool:
    settings = _a11y_settings()
    return bool(settings.get_boolean(_OSK_KEY)) if settings is not None else False

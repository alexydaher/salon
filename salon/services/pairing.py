# SPDX-License-Identifier: GPL-3.0-or-later
"""Phone-as-keyboard over the LAN (§6.12).

Text entry with a D-pad is the worst part of any TV interface, and this is
the escape hatch: the screen shows a URL and a four-digit code, the phone
opens one page with one text field, and what it types arrives in Salon's
focused entry.

Three properties matter and are all load-bearing:

* **On demand only.** The server starts when a text field asks for it and
  stops the moment that field is dismissed. A launcher that quietly runs an
  HTTP server on the LAN for its whole lifetime is not something to ship.
* **The code gates every request**, not just a login step — there are no
  sessions to steal because there is no session, just a shared secret sent
  with each POST.
* **Sessions expire.** Five minutes, enforced server-side, so a forgotten
  pairing page can't type into the TV an hour later.
* **Wrong codes are counted.** Four digits is ten thousand possibilities,
  which a script on the same network exhausts in seconds — `compare_digest`
  defeats a timing oracle but not a loop. After `MAX_ATTEMPTS` wrong codes
  the session is burned: every further request is refused, including one
  bearing the right code, and the only way on is to close the search screen
  and reopen it, which mints a new code. A locked-out session says so on the
  television, because the alternative is a phone that has silently stopped
  working.

This does not solve OAuth inside a spawned Chrome — that happens in another
process, outside Salon's control. It solves catalogue editing, search and
bookmark entry, which is where the typing actually is.
"""

from __future__ import annotations

import json
import secrets
import socket
from collections.abc import Callable

import gi

gi.require_version("Soup", "3.0")

from gi.repository import GLib, Soup  # noqa: E402

DEFAULT_PORT = 8437
SESSION_TIMEOUT_SECONDS = 300

# Wrong codes allowed before the session is burned. Low enough that a brute
# force gets nowhere, high enough to survive a person mistyping four digits
# on a phone keyboard a few times.
MAX_ATTEMPTS = 5

# Soup.Status has no TOO_MANY_REQUESTS member in libsoup 3.
_STATUS_TOO_MANY_REQUESTS = 429

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Salon keyboard</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; padding: 6vw; background: #0E1116; color: #F2EDE4;
         font: 16px/1.5 system-ui, sans-serif; }
  h1 { font-size: 1.4rem; margin: 0 0 1.5rem; }
  label { display: block; margin: 1rem 0 0.35rem; color: #9AA3AE; }
  input { width: 100%; box-sizing: border-box; padding: 0.9rem; font-size: 1.2rem;
          border-radius: 12px; border: 2px solid #1F2630; background: #161B22;
          color: #F2EDE4; }
  input:focus { outline: none; border-color: #E8A33D; }
  button { margin-top: 1.5rem; width: 100%; padding: 1rem; font-size: 1.1rem;
           font-weight: 600; border: 0; border-radius: 12px;
           background: #E8A33D; color: #0E1116; }
  #status { margin-top: 1rem; min-height: 1.5rem; color: #9AA3AE; }
</style>
</head>
<body>
<h1>Type into Salon</h1>
<label for="code">Code shown on the TV</label>
<input id="code" inputmode="numeric" autocomplete="off" maxlength="4">
<label for="text">Text</label>
<input id="text" autocomplete="off" autocapitalize="none" autofocus>
<button id="send">Send to TV</button>
<div id="status"></div>
<script>
  const status = document.getElementById('status');
  async function send() {
    const body = JSON.stringify({
      code: document.getElementById('code').value,
      text: document.getElementById('text').value
    });
    try {
      const response = await fetch('/type', {method: 'POST', body});
      status.textContent = response.ok ? 'Sent.' : await response.text();
      if (response.ok) document.getElementById('text').value = '';
    } catch (error) { status.textContent = 'Could not reach Salon.'; }
  }
  document.getElementById('send').addEventListener('click', send);
  document.getElementById('text').addEventListener('keydown', e => {
    if (e.key === 'Enter') send();
  });
</script>
</body>
</html>
"""


def local_address() -> str | None:
    """The address a phone on the same LAN can actually reach.

    Connecting a UDP socket to an off-link address doesn't send anything;
    it just makes the kernel pick the route it would use, which is the only
    reliable way to find the right interface on a host with several.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed anywhere
        return str(probe.getsockname()[0])
    except OSError:
        return None
    finally:
        probe.close()


class PairingServer:
    """Serves the pairing page and accepts typed text while running."""

    def __init__(
        self,
        on_text: Callable[[str], None],
        port: int = DEFAULT_PORT,
        *,
        on_locked: Callable[[], None] | None = None,
    ) -> None:
        self._on_text = on_text
        self._on_locked = on_locked
        self._port = port
        self._server: Soup.Server | None = None
        self._code = ""
        self._expiry_id: int | None = None
        self._wrong_attempts = 0
        self._locked = False

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def code(self) -> str:
        return self._code

    @property
    def locked(self) -> bool:
        """Too many wrong codes. The server keeps listening — refusing every
        request is the point — but nothing it is sent can be typed any
        more."""
        return self._locked

    @property
    def url(self) -> str | None:
        address = local_address()
        return f"http://{address}:{self._port}" if address else None

    def start(self) -> bool:
        if self._server is not None:
            return True
        self._code = f"{secrets.randbelow(10000):04d}"
        self._wrong_attempts = 0
        self._locked = False
        server = Soup.Server()
        server.add_handler("/", self._handle_page)
        server.add_handler("/type", self._handle_type)
        try:
            server.listen_all(self._port, Soup.ServerListenOptions(0))
        except GLib.Error:
            return False
        self._server = server
        self._expiry_id = GLib.timeout_add_seconds(SESSION_TIMEOUT_SECONDS, self._on_expired)
        return True

    def stop(self) -> None:
        if self._expiry_id is not None:
            GLib.source_remove(self._expiry_id)
            self._expiry_id = None
        if self._server is not None:
            self._server.disconnect()
            self._server = None
        self._code = ""
        self._wrong_attempts = 0
        self._locked = False

    def _on_expired(self) -> bool:
        self._expiry_id = None
        self.stop()
        return GLib.SOURCE_REMOVE

    def _handle_page(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        if message.get_method() != "GET":
            message.set_status(Soup.Status.METHOD_NOT_ALLOWED, None)
            return
        message.set_status(Soup.Status.OK, None)
        message.set_response("text/html; charset=utf-8", Soup.MemoryUse.COPY, _PAGE.encode())

    def _handle_type(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        if message.get_method() != "POST":
            message.set_status(Soup.Status.METHOD_NOT_ALLOWED, None)
            return
        body = message.get_request_body()
        payload = bytes(body.flatten().get_data() or b"")
        try:
            fields = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            fields = None
        if not isinstance(fields, dict):
            message.set_status(Soup.Status.BAD_REQUEST, None)
            message.set_response("text/plain", Soup.MemoryUse.COPY, b"Malformed request.")
            return
        # Checked before the code is even read: once a session is burned it
        # is burned for the right code too, so that guessing it on the last
        # allowed attempt wins nothing.
        if self._locked:
            message.set_status(_STATUS_TOO_MANY_REQUESTS, None)
            message.set_response(
                "text/plain",
                Soup.MemoryUse.COPY,
                b"Too many wrong codes. Close the search screen on the TV and open it again.",
            )
            return

        code = str(fields.get("code", ""))
        text = str(fields.get("text", ""))

        # compare_digest, not ==: the code is short enough that a timing
        # oracle is a real (if unglamorous) way to guess it.
        if not secrets.compare_digest(code, self._code):
            self._wrong_attempts += 1
            if self._wrong_attempts >= MAX_ATTEMPTS:
                self._locked = True
                if self._on_locked is not None:
                    GLib.idle_add(_notify, self._on_locked)
            message.set_status(Soup.Status.FORBIDDEN, None)
            message.set_response("text/plain", Soup.MemoryUse.COPY, b"Wrong code.")
            return

        # A correct code proves whoever is holding the phone was told it, so
        # the earlier fumbles stop counting against them.
        self._wrong_attempts = 0
        GLib.idle_add(lambda: _deliver(self._on_text, text))
        message.set_status(Soup.Status.OK, None)
        message.set_response("text/plain", Soup.MemoryUse.COPY, b"ok")


def _deliver(callback: Callable[[str], None], text: str) -> bool:
    callback(text)
    return GLib.SOURCE_REMOVE


def _notify(callback: Callable[[], None]) -> bool:
    callback()
    return GLib.SOURCE_REMOVE

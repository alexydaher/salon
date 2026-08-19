# SPDX-License-Identifier: GPL-3.0-or-later
"""Where Salon says what happened.

Salon runs from a systemd user unit with `Restart=always` when it is the
session, so when it dies it is started again — the right behaviour for a
television and the worst possible one for diagnosis: the screen blinks, the
launcher is back, and whatever went wrong left no trace. There is no
terminal in the room to have been watching.

So two sinks, deliberately:

* **stderr**, which the session manager hands to the journal, so
  `journalctl --user -u gnome-session` or `-t salon` has it in context with
  everything else that happened at that moment;
* **a file** under `$XDG_STATE_HOME/salon/`, capped and rotated, because the
  journal on a set-top box may be volatile (`Storage=volatile` survives no
  reboots) and "it restarted itself last night" is a question asked the
  next morning.

Python exceptions escaping into a GTK callback print a traceback and are
otherwise swallowed by the main loop, so `install()` also routes
`sys.excepthook`, `threading.excepthook` and GLib's own log domains through
the same place. An unhandled exception is logged with its traceback and the
process is left running: crashing the launcher because an artwork thread
raised would take the whole television down for something the user can't
see.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
import types
from pathlib import Path

_LOG_NAME = "salon"
_MAX_BYTES = 512 * 1024
_BACKUP_COUNT = 2

_installed = False


def state_dir() -> Path:
    """`$XDG_STATE_HOME/salon`, per the XDG base directory spec — state, not
    cache: a log that explains last night's restart must not be something a
    cleaner is entitled to delete."""
    root = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(root) / "salon"


def log_path() -> Path:
    return state_dir() / "salon.log"


def logger() -> logging.Logger:
    return logging.getLogger(_LOG_NAME)


def install(*, debug: bool | None = None) -> logging.Logger:
    """Set up both sinks and the exception hooks. Idempotent.

    `debug` defaults to the `SALON_DEBUG` environment variable, so a
    television that is misbehaving can be restarted with one word in front
    of it rather than an edited file.
    """
    global _installed
    log = logger()
    if _installed:
        return log

    if debug is None:
        debug = bool(os.environ.get("SALON_DEBUG"))
    log.setLevel(logging.DEBUG if debug else logging.INFO)
    log.propagate = False

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    log.addHandler(stream)

    try:
        state_dir().mkdir(parents=True, exist_ok=True)
        rotating = logging.handlers.RotatingFileHandler(
            log_path(), maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        rotating.setFormatter(fmt)
        log.addHandler(rotating)
    except OSError as error:
        # A read-only or full home directory is not a reason to fail to
        # start a launcher. stderr still works.
        log.warning("No log file: %s", error)

    _install_hooks(log)
    _installed = True
    return log


def _install_hooks(log: logging.Logger) -> None:
    previous = sys.excepthook

    def on_exception(
        kind: type[BaseException], value: BaseException, tb: types.TracebackType | None
    ) -> None:
        if issubclass(kind, KeyboardInterrupt):
            previous(kind, value, tb)
            return
        log.critical("Unhandled exception", exc_info=(kind, value, tb))

    sys.excepthook = on_exception

    def on_thread_exception(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, SystemExit):
            return
        log.critical(
            "Unhandled exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = on_thread_exception
    _install_glib_bridge(log)


def _install_glib_bridge(log: logging.Logger) -> None:
    """GLib, GTK and libsoup log through g_log, which by default writes
    straight to stderr and never reaches the file. Route the domains Salon
    actually causes messages in through the same logger."""
    try:
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib
    except (ImportError, ValueError):  # pragma: no cover - gi is always here in the app
        return

    levels = {
        GLib.LogLevelFlags.LEVEL_DEBUG: logging.DEBUG,
        GLib.LogLevelFlags.LEVEL_INFO: logging.INFO,
        GLib.LogLevelFlags.LEVEL_MESSAGE: logging.INFO,
        GLib.LogLevelFlags.LEVEL_WARNING: logging.WARNING,
        GLib.LogLevelFlags.LEVEL_CRITICAL: logging.ERROR,
        GLib.LogLevelFlags.LEVEL_ERROR: logging.CRITICAL,
    }

    def writer(level: int, fields: object, _size: int, _user_data: object) -> int:
        message = ""
        domain = ""
        try:
            entries = GLib.log_writer_format_fields(level, fields, False)
            message = entries or ""
        except Exception:  # noqa: BLE001 - a log path must never raise
            message = "(unformattable log message)"
        for flag, python_level in levels.items():
            if level & flag:
                log.log(python_level, "%s%s", f"{domain} " if domain else "", message)
                break
        return int(GLib.LogWriterOutput.HANDLED)

    GLib.log_set_writer_func(writer, None)

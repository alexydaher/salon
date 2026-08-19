# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: `python3 -m salon.main`."""

from __future__ import annotations

import sys


def main() -> int:
    # Before anything imports gi: the log writer has to be in place to catch
    # what the toolkit says on the way up, and a failure during startup is
    # exactly the one nobody is watching a terminal for.
    from salon import logs

    log = logs.install()

    from salon import config
    from salon.app import SalonApplication

    log.info("Salon %s starting", config.VERSION)
    app = SalonApplication()
    status = app.run(sys.argv)
    log.info("Salon exiting with status %s", status)
    return status


if __name__ == "__main__":
    raise SystemExit(main())

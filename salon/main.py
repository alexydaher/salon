"""Entry point: `python3 -m salon.main`."""

from __future__ import annotations

import sys


def main() -> int:
    from salon.app import SalonApplication

    app = SalonApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())

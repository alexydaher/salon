# Writing a provider

A provider adds rows to Salon's home screen. Drop a `.py` file into
`~/.local/share/salon/providers/` (or `$XDG_DATA_HOME/salon/providers/`) and
restart Salon, or use **Settings → Providers → Reload providers**.

The whole contract is one function called `provider()`, returning an object
that subclasses `salon.core.provider.Provider`:

```python
from salon.core.model import LaunchKind, LaunchSpec, Row, Tile
from salon.core.provider import Provider


class Bookmarks(Provider):
    id = "bookmarks"          # unique; also what Settings toggles
    title = "Bookmarks"       # shown in Settings → Providers
    priority = 30             # lower sorts nearer the top of the screen

    def rows(self, context):
        tile = Tile(
            id="bookmarks-wikipedia",
            title="Wikipedia",
            subtitle=None,
            launch=LaunchSpec(kind=LaunchKind.URL, target="https://wikipedia.org"),
            artwork=None,       # a path, or an https:// URL Salon will cache
            icon_name=None,     # a themed icon name, e.g. "web-browser-symbolic"
            accent=None,        # "#RRGGBB"; otherwise derived from the artwork
        )
        return [
            Row(
                id="bookmarks",
                title="Bookmarks",
                tiles=[tile],
                provider_id=self.id,
                tile_aspect="wide",   # or "square" / "poster"
            )
        ]


def provider():
    return Bookmarks()
```

## What Salon guarantees

* `rows()` runs **off the main thread**, so it may block — on a network
  request, for instance. It gets **3 seconds**; past that its rows are
  discarded and Settings shows "Took longer than 3s and was skipped".
* Raising is safe. The exception is caught, shown against your provider in
  Settings, and every other provider still contributes.
* Returning something that isn't `list[Row]` is treated the same way.
* Providers run concurrently and cannot see each other's rows. Read
  `context.config` (the user's `tiles.json`) if you need the catalogue.
* Row ids are unique across the whole catalogue. If another provider already
  used yours, your row is dropped and Settings says so — pick something
  namespaced.

## What it does not

Loading a provider executes its Python as you, with your permissions. This
is the trust level of a file in `~/.local/bin`, not a sandbox. Only add
providers you would run as a script.

Priorities used by the built-ins: recents `10`, your own tiles `20`,
all-applications `90`. The default for a `Provider` is `100`.

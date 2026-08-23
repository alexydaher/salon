# SPDX-License-Identifier: GPL-3.0-or-later
"""User overrides for what each button does. Pure — no gi.

Salon's button map is a good default and a bad law. The three input sources
each have a vendor problem the default cannot solve:

* **Gamepads disagree about the face buttons.** The Nintendo layout swaps
  the physical positions of the south and east buttons relative to an Xbox
  pad, so "the bottom one is OK" and "A is OK" are different rules and
  every controller obeys one of them.
* **CEC user-control codes are a suggestion.** The 1.4 list says 0x0B is
  "contents menu"; which key on a given television's remote sends it, or
  whether any does, is between that manufacturer and nobody.
* **Programmable IR remotes send whatever they are taught.** A Flirc
  receiver presents as a keyboard, and the whole point of one is that the
  owner chooses the keys.

Flex Launcher, which is the thing Salon is competing with for anyone with a
controller, lets every button be rebound in its config file. Salon has a
settings screen, so it can do it without one — but the machinery has to
exist first, and this is it.

The design is deliberately an *override layer* rather than a replacement
table. Each input source keeps its own default map, because those maps are
written in the vocabulary of their own hardware (`Gdk.KEY_*`, evdev codes,
CEC codes) and moving them here would mean either importing gi into `core`
or reducing them to bare integers nobody can read. What lives here is only
the set of changes a user has made, which is usually empty and never large.

The serialized form is a flat `str -> str` map, because that is what
GSettings can store without inventing a schema: `"pad:304" -> "ok"`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# The source a code belongs to. A raw code is only meaningful alongside one
# — evdev's BTN_SOUTH is 0x130 and CEC's 0x130 is nothing at all.
GAMEPAD = "pad"
KEYBOARD = "key"
CEC = "cec"
SOURCES = (GAMEPAD, KEYBOARD, CEC)

_SEPARATOR = ":"


class BindingError(ValueError):
    """A binding that cannot be stored or would not survive a round trip."""


def make_key(source: str, code: int) -> str:
    """The stored form of one physical button."""
    if source not in SOURCES:
        raise BindingError(f"unknown input source: {source!r}")
    if not isinstance(code, int) or isinstance(code, bool) or code < 0:
        raise BindingError(f"not a hardware code: {code!r}")
    return f"{source}{_SEPARATOR}{code}"


def split_key(key: str) -> tuple[str, int] | None:
    """The inverse, or None for anything that was not written by make_key.

    Lenient rather than raising: this parses whatever is in GSettings,
    which a person may have edited by hand, and one bad entry should cost
    that entry rather than every binding on the machine.
    """
    source, separator, code = key.partition(_SEPARATOR)
    if not separator or source not in SOURCES or not code.isdigit():
        return None
    return source, int(code)


class Bindings:
    """The user's overrides, as a lookup an input source can consult.

    `action_for` returns None when the user has said nothing about a
    button, which is the normal case and means "use your own default". A
    button can also be bound to nothing at all — `UNBOUND` — which is not
    the same thing: it is how somebody silences a key their remote sends by
    accident, and it has to beat the default rather than fall through to it.
    """

    UNBOUND = ""

    def __init__(self, stored: Mapping[str, str] | None = None) -> None:
        self._by_key: dict[str, str] = {}
        for key, action in (stored or {}).items():
            if split_key(key) is not None:
                self._by_key[key] = action

    # --- lookup ----------------------------------------------------------

    def action_for(self, source: str, code: int) -> str | None:
        """The action name this button is bound to, `UNBOUND`, or None to
        mean "no override; use the source's default"."""
        try:
            key = make_key(source, code)
        except BindingError:
            return None
        return self._by_key.get(key)

    def keys_for(self, action: str) -> list[str]:
        """Every button bound to an action, so Settings can show them."""
        return sorted(key for key, value in self._by_key.items() if value == action)

    def is_overridden(self, source: str, code: int) -> bool:
        return self.action_for(source, code) is not None

    # --- editing ---------------------------------------------------------

    def bind(self, source: str, code: int, action: str) -> None:
        """Point one button at one action.

        Any *other* button previously bound to the same action keeps its
        binding: a controller with two buttons that both mean OK is a
        reasonable thing to want, and taking the old one away would make
        rebinding a two-step operation with a broken state in the middle.
        """
        self._by_key[make_key(source, code)] = action

    def unbind(self, source: str, code: int) -> None:
        """Silence a button entirely, beating the source's default."""
        self._by_key[make_key(source, code)] = self.UNBOUND

    def clear(self, source: str, code: int) -> None:
        """Forget the override and let the default apply again."""
        self._by_key.pop(make_key(source, code), None)

    def clear_all(self) -> None:
        self._by_key.clear()

    # --- storage ---------------------------------------------------------

    def to_storage(self) -> dict[str, str]:
        return dict(self._by_key)

    @property
    def empty(self) -> bool:
        return not self._by_key


def describe_keys(keys: Iterable[str], names: Mapping[str, str] | None = None) -> str:
    """A readable summary of what is bound, for a settings row.

    `names` lets a caller supply real button names for the codes it knows —
    "Cross" reads better than "pad:304" for anyone who has ever held a
    controller, and nobody can read a decimal evdev code.
    """
    labels = []
    for key in keys:
        if names and key in names:
            labels.append(names[key])
            continue
        parsed = split_key(key)
        if parsed is None:
            continue
        source, code = parsed
        labels.append(f"{source.upper()} 0x{code:X}")
    return ", ".join(labels)

# SPDX-License-Identifier: GPL-3.0-or-later
"""The `input-injection` setting and the code that reads it must agree.

Three strings decide which route carries pointer and keyboard injection,
and they are written down twice: as `<choice>` elements in the GSettings
schema, and as `BACKEND_*` constants in `services/pointer_injector`. A
mismatch does not raise — `Gio.Settings.get_string` returns whatever the
schema's default is, `start()` compares it against constants that no longer
match, and the result is the portal's consent dialog appearing on a
television that has nothing to dismiss it with. That is the exact failure
this setting exists to prevent, so the two lists are checked against each
other here rather than trusted to stay in step.

The schema is parsed as XML rather than loaded through Gio: the compiled
schema is not installed when the unit tests run, and the question is about
the source of truth anyway.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

_SCHEMA = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "io.github.alexydaher.Salon.gschema.xml"
)


def _key(name: str) -> ElementTree.Element:
    root = ElementTree.parse(_SCHEMA).getroot()
    for key in root.iter("key"):
        if key.get("name") == name:
            return key
    raise AssertionError(f"no <key name={name!r}> in {_SCHEMA.name}")


def test_schema_choices_match_the_constants() -> None:
    pytest.importorskip("gi")
    from salon.services import pointer_injector

    key = _key("input-injection")
    choices = {choice.get("value") for choice in key.iter("choice")}
    assert choices == {
        pointer_injector.BACKEND_AUTO,
        pointer_injector.BACKEND_MUTTER,
        pointer_injector.BACKEND_PORTAL,
    }


def test_default_prefers_the_route_that_needs_no_input_device() -> None:
    """"auto", not "portal".

    A fresh appliance's first input device is the phone it has not paired
    yet. Defaulting to the portal would put a two-button dialog on screen
    that can only be dismissed with the pointer the dialog is gating.
    """
    pytest.importorskip("gi")
    from salon.services import pointer_injector

    default = _key("input-injection").findtext("default", "").strip()
    assert default == f"'{pointer_injector.BACKEND_AUTO}'"


def test_the_backend_labels_are_the_setting_values() -> None:
    """`PointerInjector.backend` reports "mutter"/"portal", and Settings
    compares those against the schema's own words. One vocabulary, not two."""
    pytest.importorskip("gi")
    from salon.services import pointer_injector

    assert pointer_injector.BACKEND_MUTTER == "mutter"
    assert pointer_injector.BACKEND_PORTAL == "portal"

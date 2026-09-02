# SPDX-License-Identifier: GPL-3.0-or-later
"""What the phone is allowed to change, and how it should draw each one.

Pure — no gi. `tests/test_remote_settings.py`.

The television is the display and the phone is the control surface, which
is exactly the arrangement live preview has been reaching for since the
Appearance strip was built: on the television, choosing an accent means
covering the thing you are choosing it *for*. From a phone it does not.

So the phone gets precisely the settings whose effect is visible on the
home screen — the `preview=True` set — and nothing else. That is not a
convenience boundary, it is the whole rule:

* a setting the television cannot show you the result of is one there is no
  advantage to setting from here, and
* an allow-list means the endpoint cannot be talked into writing a key
  nobody meant to expose. `apply` refuses a key that is not in this tuple
  and a value outside the field's own range, so validation lives with the
  description rather than in the request handler.

Ranges carry their own step. A phone could offer a continuous slider and it
would be the wrong control: these are coarse deliberate steps (5% of a
scale, 4% of a dim), the television renders the result, and a value nobody
can name is a value nobody can put back.
"""

from __future__ import annotations

from dataclasses import dataclass

CHOICE = "choice"
RANGE = "range"


@dataclass(frozen=True, slots=True)
class SettingField:
    key: str
    label: str
    kind: str
    detail: str = ""
    # (value, label) for a choice. A value that looks like `#RRGGBB` is
    # drawn as the colour it is, on the phone exactly as on the television.
    options: tuple[tuple[str, str], ...] = ()
    minimum: float = 0.0
    maximum: float = 0.0
    step: float = 1.0
    # How to write the number beside the slider. "percent" is stored 0..1
    # and shown 0..100, which is the difference that made `tile-scale`
    # unreadable as a raw value.
    format: str = "plain"
    unit: str = ""

    def as_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "detail": self.detail,
        }
        if self.kind == CHOICE:
            payload["options"] = [{"value": v, "label": text} for v, text in self.options]
        else:
            payload.update(
                minimum=self.minimum,
                maximum=self.maximum,
                step=self.step,
                format=self.format,
                unit=self.unit,
            )
        return payload

    def clamp(self, value: float) -> float:
        """Snap to the nearest step inside the range.

        The phone's slider is `<input type=range>` with the same step, so
        this normally changes nothing — which is the point: it is here for
        a request that did not come from the slider.
        """
        bounded = min(self.maximum, max(self.minimum, value))
        if self.step <= 0:
            return bounded
        steps = round((bounded - self.minimum) / self.step)
        return min(self.maximum, self.minimum + steps * self.step)

    def accepts(self, value: object) -> bool:
        if self.kind == CHOICE:
            return isinstance(value, str) and value in {v for v, _ in self.options}
        return isinstance(value, (int, float)) and not isinstance(value, bool)


_THEMES = (
    ("midnight", "Midnight"),
    ("graphite", "Graphite"),
    ("ember", "Ember"),
    ("contrast", "High contrast"),
)

_ACCENTS = (
    ("#E8A33D", "Lamplight amber"),
    ("#D9584B", "Ember"),
    ("#4C9BE8", "Cold blue"),
    ("#5FBF7F", "Green"),
    ("#B77BE8", "Violet"),
)

_WALLPAPER_COLOR_TREATMENTS = (
    ("automatic", "Automatic"),
    ("original", "Original colours"),
    ("focus", "Focused tile"),
    ("accent", "Interface accent"),
)

FIELDS: tuple[SettingField, ...] = (
    SettingField(
        key="accent-color",
        label="Accent colour",
        kind=CHOICE,
        options=_ACCENTS,
    ),
    SettingField(
        key="theme",
        label="Theme",
        kind=CHOICE,
        options=_THEMES,
    ),
    SettingField(
        key="tile-scale",
        label="Tile size",
        kind=RANGE,
        minimum=0.5,
        maximum=1.5,
        step=0.05,
        format="percent",
    ),
    SettingField(
        key="row-spacing-scale",
        label="Row density",
        kind=RANGE,
        minimum=0.45,
        maximum=1.6,
        step=0.05,
        format="percent",
    ),
    SettingField(
        key="safe-area-percent",
        label="Safe area",
        kind=RANGE,
        minimum=2.0,
        maximum=8.0,
        step=0.5,
        format="decimal",
        unit="%",
    ),
    SettingField(
        key="wallpaper-color-treatment",
        label="Background colours",
        kind=CHOICE,
        options=_WALLPAPER_COLOR_TREATMENTS,
    ),
    SettingField(
        key="wallpaper-dim",
        label="Background dimming",
        kind=RANGE,
        minimum=0.0,
        maximum=1.0,
        step=0.04,
        format="percent",
    ),
)

_BY_KEY: dict[str, SettingField] = {f.key: f for f in FIELDS}


def field_for(key: object) -> SettingField | None:
    """The field with this key, or None. Everything else is a refusal."""
    return _BY_KEY.get(key) if isinstance(key, str) else None


def describe(values: dict[str, object]) -> dict[str, object]:
    """The payload `GET /tune` answers with: what may change, and what it is.

    Values are sent for the fields that were readable, so a key missing
    from `values` costs that row rather than the screen.
    """
    return {
        "fields": [f.as_json() for f in FIELDS],
        "values": {key: values[key] for key in _BY_KEY if key in values},
    }


def coerce(key: object, value: object) -> tuple[SettingField, object] | None:
    """Validate one write. None means refuse it, and say nothing more.

    Returning the field alongside the value is what lets the caller write
    it with the right GSettings type without a second lookup that could
    disagree with this one.
    """
    setting = field_for(key)
    if setting is None or not setting.accepts(value):
        return None
    if setting.kind == RANGE:
        return setting, setting.clamp(float(value))  # type: ignore[arg-type]
    return setting, value


__all__ = [
    "CHOICE",
    "FIELDS",
    "RANGE",
    "SettingField",
    "coerce",
    "describe",
    "field_for",
]

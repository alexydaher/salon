// SPDX-License-Identifier: GPL-3.0-or-later
//
// The Picture pane: the settings whose effect is on the television.
//
// On the television, choosing an accent colour means covering the thing you
// are choosing it for — which is why Settings collapses to a strip over the
// live home screen. From a phone that problem does not exist: the screen
// showing the result and the screen holding the control are different
// screens, so this is the live preview the strip was an approximation of.
//
// The pane is built from `GET /tune` rather than written out here. The
// television owns which settings may be changed and what each one is
// called (`core/remote_settings.py`); a copy of that list in this file
// would be a second answer that could disagree with the first.

import { $, el, buzz } from "./dom.js";
import { session } from "./session.js";
import { post } from "./transport.js";

// One request per 60ms while a thumb is down, same as the volume slider and
// for the same reason: a range input fires on every pixel, and each of these
// ends in a GSettings write and a re-render on the television.
const THROTTLE_MS = 60;

let loaded = false;
let timers = new Map();

function format(field, value) {
  if (field.format === "percent") return `${Math.round(value * 100)}%`;
  if (field.format === "decimal") return `${value.toFixed(1)}${field.unit || ""}`;
  return `${value}${field.unit || ""}`;
}

function send(key, value) {
  clearTimeout(timers.get(key));
  // `name`, not `key`: `post` puts the session token in `key`.
  timers.set(key, setTimeout(() => post("/tune", { name: key, value }), THROTTLE_MS));
}

function isColour(value) {
  return /^#[0-9a-f]{3,8}$/i.test(value);
}

function choiceField(field, current) {
  const row = el("div", "tune-row");
  row.append(el("div", "tune-label", field.label));
  if (field.detail) row.append(el("div", "tune-detail", field.detail));
  const options = el("div", "tune-options");
  for (const option of field.options) {
    const button = el("button", "tune-option");
    // The colour itself, on the phone exactly as on the television — a
    // list reading "Ember", "Cold blue", "Violet" is a list of words about
    // colours, which is what this pane exists to stop being.
    if (isColour(option.value)) {
      const chip = el("span", "tune-chip");
      chip.style.background = option.value;
      button.append(chip);
    }
    button.append(el("span", "tune-option-text", option.label));
    button.classList.toggle("on", option.value === current);
    button.addEventListener("click", () => {
      buzz(8);
      for (const other of options.children) other.classList.remove("on");
      button.classList.add("on");
      send(field.key, option.value);
    });
    options.append(button);
  }
  row.append(options);
  return row;
}

function rangeField(field, current) {
  const row = el("div", "tune-row");
  const head = el("div", "tune-head");
  head.append(el("div", "tune-label", field.label));
  const readout = el("div", "tune-value", format(field, current));
  head.append(readout);
  row.append(head);
  if (field.detail) row.append(el("div", "tune-detail", field.detail));

  const slider = el("input", "tune-slider");
  slider.type = "range";
  slider.min = field.minimum;
  slider.max = field.maximum;
  slider.step = field.step;
  slider.value = current;
  slider.setAttribute("aria-label", field.label);
  slider.addEventListener("input", () => {
    const value = Number(slider.value);
    // The readout follows the thumb, not the television: the reply is
    // written before the setting is applied, so waiting for confirmation
    // would leave the number a frame behind the finger moving it.
    readout.textContent = format(field, value);
    send(field.key, value);
  });
  row.append(slider);
  return row;
}

function build(payload) {
  const host = $("tune");
  host.replaceChildren();
  for (const field of payload.fields || []) {
    const current = payload.values ? payload.values[field.key] : undefined;
    if (current === undefined) continue;
    host.append(field.kind === "choice" ? choiceField(field, current) : rangeField(field, current));
  }
  if (!host.children.length) {
    host.append(el("div", "tune-empty", "The television isn't offering any picture settings."));
  }
}

export async function loadTune(force = false) {
  if (loaded && !force) return;
  // The token travels in the query string, like every other GET here: a
  // fetch cannot carry a POST body, and the token is what the QR encodes
  // precisely so it can be handled this way.
  const response = await fetch(`/tune?k=${encodeURIComponent(session.key)}`).catch(() => null);
  const payload = response && response.ok ? await response.json().catch(() => null) : null;
  if (!payload) {
    $("tune").replaceChildren(el("div", "tune-empty", "Couldn't read the picture settings."));
    return;
  }
  loaded = true;
  build(payload);
}

export function bindTune() {
  // Re-read every time the drawer is opened rather than once. It is one
  // request for a surface most sessions never open, and the values it
  // wants are the ones at the moment somebody opens it — the television is
  // also being changed from its own Settings screen.
  $("tune-drawer").addEventListener("toggle", () => {
    if ($("tune-drawer").open) loadTune(true);
  });
}

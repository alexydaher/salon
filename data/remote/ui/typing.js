// SPDX-License-Identifier: GPL-3.0-or-later
//
// The Type pane. Two quite different jobs behind one field: filling a text
// box Salon is showing on the television, and typing into whatever a
// launched application has focused. Either way the field syncs as you type
// — Send and Enter are an explicit "push now", not the only way across.

import { $, buzz } from "./dom.js";
import { post } from "./transport.js";
import { pollSoon } from "./feed.js";

// What the far side already holds as a result of what has been sent: the
// television's own field in mirror mode, the launched app's field otherwise.
// Every update is expressed as a diff against this, so typing streams across
// a character at a time instead of resending the whole box.
let farText = "";
let editing = false;
let composing = false;
let openedForRequest = false;
let wantsText = false;
let flushTimer = null;
let inFlight = false;
// The last snapshot's idea of the television's own field: whether one is
// asking for text and what it already holds. Kept so opening the drawer can
// adopt that text straight away instead of waiting for the next render.
let latestText = "";
let latestWantsText = false;

// Long enough that a fast burst of keys is a handful of small requests, not
// one per key; short enough that the television keeps up with the thumb.
const FLUSH_MS = 120;

export function openTypeDrawer({ focus = false } = {}) {
  $("type-drawer").classList.add("on");
  $("type-toggle").setAttribute("aria-expanded", "true");
  // Adopt whatever the television's own field already holds, so opening the
  // keyboard onto a half-typed search starts from that text rather than a
  // blank box whose first edit would be diffed against the wrong thing. Only
  // a field Salon draws itself is readable; otherwise this is "".
  if (latestWantsText) {
    farText = latestText;
    $("text").value = latestText;
  }
  if (focus) $("text").focus();
}

export function closeTypeDrawer() {
  openedForRequest = false;
  clearTimeout(flushTimer);
  flushTimer = null;
  resetField();
  $("type-drawer").classList.remove("on");
  $("type-toggle").setAttribute("aria-expanded", "false");
  $("text").blur();
}

// A clean slate: the field and our idea of the far side go back to empty
// together, so the next thing typed is never diffed against a stale prefix.
function resetField() {
  farText = "";
  $("text").value = "";
}

function sharedPrefix(before, after) {
  let index = 0;
  while (index < before.length && index < after.length && before[index] === after[index]) {
    index += 1;
  }
  return index;
}

// The text sink on the television appends, so "what the field should say"
// has to be expressed as a run of edits. A shared prefix costs only the
// tail; anything else costs one backspace per character that has to go.
function editsTo(target) {
  if (target === farText) return "";
  if (target.startsWith(farText)) return target.slice(farText.length);
  const shared = sharedPrefix(farText, target);
  return "\b".repeat(farText.length - shared) + target.slice(shared);
}

function scheduleFlush() {
  clearTimeout(flushTimer);
  flushTimer = setTimeout(flush, FLUSH_MS);
}

// Send whatever the field has gained or lost since the last acknowledged
// state. One request in flight at a time: two overlapping ones diff against
// the same `farText` and land the tail twice.
async function flush() {
  clearTimeout(flushTimer);
  flushTimer = null;
  if (composing) return;
  if (inFlight) { scheduleFlush(); return; }
  const target = $("text").value;
  const delta = editsTo(target);
  if (!delta) return;
  inFlight = true;
  const result = await post("/type", { text: delta });
  inFlight = false;
  if (!result) return;
  farText = target;
  pollSoon();
  // More was typed while that was on the wire.
  if ($("text").value !== farText) scheduleFlush();
}

export function renderTyping(data) {
  const hint = $("type-hint");
  if (data.wantsText) {
    hint.textContent = "Type below — it appears on the TV as you go.";
  } else if (data.remoteInput) {
    hint.textContent = "Select a field with Pointer, then type here.";
  } else {
    hint.textContent =
      "Salon needs pointer permission to type into other apps.";
  }
  hint.style.color = data.wantsText ? "var(--accent)" : "";

  const mirror = $("mirror-text");
  mirror.classList.toggle("on", Boolean(data.wantsText));
  const text = data.text || "";
  mirror.querySelector("b").textContent = text || "—";
  latestText = text;
  latestWantsText = Boolean(data.wantsText);

  // Switching in or out of "the TV is asking for text" is a change of
  // target. Adopt the new field's contents outright — nothing has been
  // typed against it yet — even if our own field is focused; the guard
  // below is only for later divergence.
  if (Boolean(data.wantsText) !== wantsText) {
    wantsText = Boolean(data.wantsText);
    farText = wantsText ? text : "";
    $("text").value = farText;
  }
  if (data.wantsText && text !== farText) {
    farText = text;
    // Not while a thumb is in the box: writing the television's value back
    // mid-word is the same mistake as moving the volume slider under a
    // finger already holding it.
    if (!editing) $("text").value = text;
  }
  if (!data.wantsText && openedForRequest) closeTypeDrawer();
}

export function focusTypeField(data) {
  // Only when the television is actually asking. Focusing unconditionally
  // raised the phone's keyboard the instant this tab opened, which covered
  // the aim pad the hint tells you to use first.
  if (data && data.wantsText) {
    openedForRequest = true;
    openTypeDrawer({ focus: true });
  }
}

export function bindTyping() {
  const field = $("text");
  $("type-toggle").addEventListener("click", () => {
    if ($("type-drawer").classList.contains("on")) closeTypeDrawer();
    else openTypeDrawer();
  });
  $("type-close").addEventListener("click", closeTypeDrawer);
  $("type-drawer").addEventListener("click", (event) => {
    // The scrim only; a tap on the card is a tap on one of its controls.
    if (event.target === $("type-drawer")) closeTypeDrawer();
  });
  field.addEventListener("focus", () => { editing = true; });
  field.addEventListener("blur", () => { editing = false; flush(); });
  // The stream. `beforeinput`/`input` fire mid-composition on a phone
  // keyboard's predictive text and accents, so hold off until it settles.
  field.addEventListener("compositionstart", () => { composing = true; });
  field.addEventListener("compositionend", () => { composing = false; scheduleFlush(); });
  field.addEventListener("input", () => { if (!composing) scheduleFlush(); });
  // Send and Enter are the same push, just now — and the only ones that
  // buzz, so a live stream is not a continuous vibration.
  $("send").addEventListener("click", () => { buzz(6); flush(); });
  field.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    buzz(6);
    flush();
  });
  // Return, sent as the control character the television maps to it. There
  // is no backspace key here: the phone's own keyboard has one, and editing
  // the field streams the deletion like any other change.
  $("key-enter").addEventListener("click", async () => {
    buzz(8);
    // Anything typed but not yet across goes first, so Return acts on what
    // you can see rather than on whatever was last acknowledged.
    await flush();
    post("/type", { text: "\n" });
    pollSoon();
  });
  // Empty the field at the far end. For a box Salon draws itself that is
  // backspaces over what we know is there; for a launched app it is a
  // select-all-and-delete the server injects, since its contents cannot be
  // read back.
  $("key-clear").addEventListener("click", async () => {
    buzz(8);
    clearTimeout(flushTimer);
    flushTimer = null;
    field.value = "";
    field.focus();
    if (latestWantsText) {
      await flush();
    } else {
      farText = "";
      await post("/type", { clear: true });
      pollSoon();
    }
  });
}

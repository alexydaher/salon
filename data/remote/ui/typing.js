// SPDX-License-Identifier: GPL-3.0-or-later
//
// The Type pane. Two quite different jobs behind one field: filling a text
// box Salon is showing on the television, and typing into whatever a
// launched application has focused.

import { $, buzz } from "./dom.js";
import { post } from "./transport.js";
import { pollSoon } from "./feed.js";

// What the television's own field currently holds. Mirrored so the two
// keyboards pointed at one box agree about what is in it: type "netfli" on
// the television, pick up the phone, and the phone used to show an empty
// field whose Send would append a second copy of everything.
let onScreen = "";
let editing = false;
let openedForRequest = false;

export function openTypeDrawer({ focus = false } = {}) {
  $("type-drawer").classList.add("on");
  $("type-toggle").setAttribute("aria-expanded", "true");
  if (focus) $("text").focus();
}

export function closeTypeDrawer() {
  openedForRequest = false;
  $("type-drawer").classList.remove("on");
  $("type-toggle").setAttribute("aria-expanded", "false");
  $("text").blur();
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
  if (target === onScreen) return "";
  if (target.startsWith(onScreen)) return target.slice(onScreen.length);
  const shared = sharedPrefix(onScreen, target);
  return "\b".repeat(onScreen.length - shared) + target.slice(shared);
}

async function send() {
  const field = $("text");
  const mirroring = Boolean($("mirror-text").classList.contains("on"));
  const text = mirroring ? editsTo(field.value) : field.value;
  if (!text) return;
  const result = await post("/type", { text: text });
  if (!result) return;
  buzz(10);
  if (mirroring) {
    // The field goes on showing what the television now shows, rather than
    // emptying itself: this is one box seen from two places.
    onScreen = field.value;
  } else {
    field.value = "";
  }
  pollSoon();
}

export function renderTyping(data) {
  const hint = $("type-hint");
  if (data.wantsText) {
    hint.textContent = "The television is waiting. Type below.";
  } else if (data.remoteInput) {
    hint.textContent = "Use the pointer to select a field, then type here.";
  } else {
    hint.textContent =
      "Nothing on the television is asking for text, and Salon isn't "
      + "allowed to type into other apps yet.";
  }
  hint.style.color = data.wantsText ? "var(--accent)" : "";

  const mirror = $("mirror-text");
  mirror.classList.toggle("on", Boolean(data.wantsText));
  const text = data.text || "";
  mirror.querySelector("b").textContent = text || "—";
  if (data.wantsText && text !== onScreen) {
    onScreen = text;
    // Not while a thumb is in the box: writing the television's value back
    // mid-word is the same mistake as moving the volume slider under a
    // finger already holding it.
    if (!editing) $("text").value = text;
  }
  if (!data.wantsText) onScreen = "";
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
  field.addEventListener("focus", () => { editing = true; });
  field.addEventListener("blur", () => { editing = false; });
  $("send").addEventListener("click", send);
  field.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    send();
  });
  // Sent as the control characters the television maps to BackSpace and
  // Return, so the whole path is the one /type already takes.
  for (const [id, character] of [["key-back", "\b"], ["key-enter", "\n"]]) {
    $(id).addEventListener("click", async () => {
      buzz(8);
      // Anything typed but not yet sent goes first, so Enter submits what
      // you can see rather than whatever was sent before it.
      if (id === "key-enter" && field.value) await send();
      if (id === "key-back" && onScreen) onScreen = onScreen.slice(0, -1);
      post("/type", { text: character });
      pollSoon();
    });
  }
}

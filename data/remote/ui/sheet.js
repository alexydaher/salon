// SPDX-License-Identifier: GPL-3.0-or-later
//
// The long-press menu: pin, add, edit, remove. The same set `Action.OPTIONS`
// reaches on the television, from the one surface that shows every tile at
// once.

import { $, buzz, toast } from "./dom.js";
import { post } from "./transport.js";
import { pollSoon } from "./feed.js";

let tile = null;

export function openSheet(subject) {
  tile = subject;
  $("sheet-title").textContent = subject.title;
  // The verb, not a state: a button labelled "Pinned" leaves you working
  // out whether that is what it is or what it will do.
  $("sheet-pin").textContent = subject.pinned
    ? "Remove from Favourites"
    : "Pin to Favourites";
  // Recents, Favourites and the apps grid all produce tiles that no row in
  // tiles.json contains. There is nothing to edit or delete for those, and
  // offering it would open an editor for a row that does not exist.
  $("sheet-edit").hidden = !subject.removable;
  $("sheet-remove").hidden = !subject.removable;
  $("sheet-add").hidden = subject.removable;
  $("sheet-confirm-text").textContent =
    `${subject.title} will be taken off the home screen.`;
  $("sheet").classList.remove("confirming");
  $("sheet").classList.add("on");
}

export function closeSheet() {
  $("sheet").classList.remove("on", "confirming");
  tile = null;
}

async function run(what) {
  const subject = tile;
  closeSheet();
  if (!subject) return;
  buzz(10);
  // "pin" on something already pinned is the unpin: the label said so.
  const action = what === "pin" && subject.pinned ? "unpin" : what;
  const result = await post("/tile", { id: subject.id, what: action });
  // The server answers with a sentence, because these are the actions whose
  // consequence is not visible on the phone — "edit" opens a screen on the
  // television, and a button that changes something in another room with no
  // acknowledgement is indistinguishable from a dead one.
  if (result && result.said) toast(result.said);
  pollSoon();
}

export function bindSheet(onOpen) {
  $("sheet").addEventListener("click", (event) => {
    // The scrim only. A tap inside the card is a tap on one of its buttons.
    if (event.target === $("sheet")) closeSheet();
  });
  $("sheet-cancel").addEventListener("click", closeSheet);
  $("sheet-open").addEventListener("click", () => {
    const subject = tile;
    closeSheet();
    if (subject) onOpen(subject);
  });
  for (const [id, what] of [
    ["sheet-pin", "pin"],
    ["sheet-add", "add"],
    ["sheet-edit", "edit"],
  ]) {
    $(id).addEventListener("click", () => run(what));
  }
  // Removal asks first, in the sheet, Cancel-equivalent first — the order
  // the television uses for its own danger confirmations. It used to be
  // `window.confirm`, which on iOS prefixes the page's host name and reads
  // as a different application interrupting.
  $("sheet-remove").addEventListener("click", () => {
    $("sheet").classList.add("confirming");
  });
  $("sheet-no").addEventListener("click", closeSheet);
  $("sheet-yes").addEventListener("click", () => run("remove"));
}

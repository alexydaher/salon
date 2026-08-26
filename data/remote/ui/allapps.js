// SPDX-License-Identifier: GPL-3.0-or-later
//
// Every installed application, A-Z, with an index rail down the edge.
//
// The phone could search the whole system but only *browse* the catalogue,
// so anything not on the home screen was reachable only if you already knew
// its name. This is also the surface to put a long list on: 200 apps at
// five columns is forty rows of D-pad on the television, and a scrollbar
// and an index here.

import { $, el, toast } from "./dom.js";
import { post } from "./transport.js";
import { tileNode } from "./tiles.js";

let loaded = false;
let onLongPress = () => {};

function letterOf(title) {
  const first = (title || "?").trim().charAt(0).toUpperCase();
  return first >= "A" && first <= "Z" ? first : "#";
}

function render(tiles) {
  const host = $("allapps");
  const rail = $("rail");
  host.textContent = "";
  rail.textContent = "";
  if (!tiles.length) {
    const empty = el("div", "", "No applications found on the television.");
    empty.id = "results-empty";
    host.append(empty);
    return;
  }
  let letter = "";
  let grid = null;
  for (const tile of tiles) {
    const next = letterOf(tile.title);
    if (next !== letter) {
      letter = next;
      const heading = el("h2", "row-title", letter);
      heading.id = `az-${letter === "#" ? "hash" : letter}`;
      host.append(heading);
      grid = el("div", "row-tiles square");
      host.append(grid);
      const mark = el("span", "", letter);
      mark.dataset.letter = heading.id;
      rail.append(mark);
    }
    grid.append(tileNode(tile, onLongPress));
  }
}

async function load() {
  if (loaded) return;
  const result = await post("/apps", {});
  if (!result) return;
  loaded = true;
  render(result.apps || []);
  if (!(result.apps || []).length) toast("Salon hasn't finished reading the app list.");
}

export function closeBrowsing() {
  document.body.classList.remove("browsing");
  $("all-apps").classList.remove("on");
  $("all-apps").setAttribute("aria-pressed", "false");
}

// Dragging the rail rather than tapping it: a column of 27 letters on a
// phone is about 14px per target, which is under any reasonable tap size —
// so the gesture that works is sliding a thumb down it, exactly as the
// system contacts app does.
function jumpFrom(event) {
  const found = document.elementFromPoint(event.clientX, event.clientY);
  const target = found && found.dataset && found.dataset.letter;
  if (!target) return;
  for (const mark of $("rail").children) mark.classList.toggle("on", mark === found);
  const heading = $(target);
  if (heading) heading.scrollIntoView({ block: "start" });
}

export function bindAllApps(handler, onCleared) {
  onLongPress = handler;
  $("all-apps").addEventListener("click", () => {
    const browsing = !document.body.classList.contains("browsing");
    if (browsing) {
      onCleared();
      document.body.classList.add("browsing");
      $("all-apps").classList.add("on");
      $("all-apps").setAttribute("aria-pressed", "true");
      load();
      $("pane-apps").scrollTop = 0;
    } else {
      closeBrowsing();
    }
  });
  const rail = $("rail");
  rail.addEventListener("pointerdown", (event) => {
    rail.setPointerCapture(event.pointerId);
    jumpFrom(event);
  });
  rail.addEventListener("pointermove", (event) => {
    if (rail.hasPointerCapture(event.pointerId)) jumpFrom(event);
  });
}

// A restarted remote has a different installed-app list to offer, and the
// ids behind it are only valid for as long as the server remembers having
// offered them.
export function forgetAllApps() {
  loaded = false;
}

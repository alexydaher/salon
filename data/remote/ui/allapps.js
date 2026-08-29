// SPDX-License-Identifier: GPL-3.0-or-later
//
// Every installed application, A-Z, with an index rail down the edge.
//
// The phone could search the whole system but only *browse* the catalogue,
// so anything not on the home screen was reachable only if you already knew
// its name. This is also the surface to put a long list on: 200 apps at
// five columns is forty rows of D-pad on the television, and a scrollbar
// and an index here.

import { $, buzz, el, measureSearchRow } from "./dom.js";
import { post } from "./transport.js";
import { tileNode } from "./tiles.js";

let loaded = false;
let onLongPress = () => {};
// Heading node per letter, in the order they are drawn: what the rail
// scrolls to, and what tells the rail where the list has got to.
let headings = [];
let marks = new Map();
let activeLetter = "";
let scrubbedLetter = "";
let syncing = false;

// "Éditeur de texte" belongs under E and "Übersicht" under U. Unfolded they
// were both greater than "Z", so both fell into "#" — which then appeared
// twice, once for the digits at the top of the list and once for these at
// the bottom, and the two headings were given the same id, so the rail's
// second "#" jumped to the first.
function letterOf(title) {
  const first = (title || "").trim().charAt(0);
  const folded = first.normalize("NFD").replace(/\p{M}/gu, "").toUpperCase();
  return folded >= "A" && folded <= "Z" ? folded : "#";
}

function render(tiles) {
  const host = $("allapps");
  host.textContent = "";
  headings = [];
  document.body.classList.toggle("empty-apps", !tiles.length);
  if (!tiles.length) return;

  // Grouped through a map rather than by watching the letter change down a
  // sorted list: that only works while the television's collation and this
  // page's folding agree exactly, and when they disagree the cost is a
  // second section with the same letter and the same id as the first.
  const groups = new Map();
  for (const tile of tiles) {
    const letter = letterOf(tile.title);
    let grid = groups.get(letter);
    if (!grid) {
      grid = el("div", "row-tiles square");
      groups.set(letter, grid);
    }
    grid.append(tileNode(tile, onLongPress));
  }

  for (const letter of [...groups.keys()].sort()) {
    const group = el("section", "az-group");
    const heading = el("h2", "row-title", letter);
    heading.id = `az-${letter === "#" ? "hash" : letter}`;
    group.append(heading, groups.get(letter));
    host.append(group);
    headings.push({ letter, heading, group });
  }
  buildRail(headings.map((entry) => entry.letter));
}

function say(message) {
  $("allapps-empty").textContent = message;
}

async function load() {
  if (loaded) return;
  say("Reading the list of applications…");
  document.body.classList.add("empty-apps");
  const result = await post("/apps", {});
  if (!result) {
    // `post` has already toasted whatever the television said, and a toast
    // is gone in two seconds — the pane it was about must not be left
    // reading "Reading the list of applications…" underneath it.
    say("Couldn't read the list of applications. Tap All again to retry.");
    return;
  }
  const apps = result.apps || [];
  render(apps);
  if (!apps.length) {
    // Deliberately *not* marked loaded. The television scans its desktop
    // entries on a worker thread when the remote starts, so an empty answer
    // usually means the scan has not landed yet — and marking it loaded
    // made that answer permanent for the life of the page.
    say("Salon hasn't finished reading the list of applications. Tap All again in a moment.");
    return;
  }
  loaded = true;
  placeRail();
  syncRail();
}

export function closeBrowsing() {
  document.body.classList.remove("browsing", "empty-apps");
  hideBubble();
  $("all-apps").classList.remove("on");
  $("all-apps").setAttribute("aria-pressed", "false");
}

// --- the rail -------------------------------------------------------------

function buildRail(letters) {
  const rail = $("rail");
  rail.textContent = "";
  marks = new Map();
  activeLetter = "";
  for (const letter of letters) {
    const mark = el("span", "", letter);
    rail.append(mark);
    marks.set(letter, mark);
  }
}

// The rail is fixed to the viewport but belongs to the list, so its box
// comes from the pane's. Measured rather than expressed in CSS because the
// header, the search row and the tab strip are all different heights in
// landscape, and a rail sized against the viewport ran under one and over
// another.
function placeRail() {
  const rail = $("rail");
  // `offsetParent` is null for a fixed element whatever its state, so it
  // cannot answer this; an undisplayed rail measures zero high and would be
  // centred on half the pane.
  if (!marks.size || !rail.getClientRects().length) return;
  measureSearchRow();
  const pane = $("pane-apps").getBoundingClientRect();
  const search = $("search-row").offsetHeight;
  const inset = 6;
  const top = pane.top + search + inset;
  const room = Math.max(96, pane.bottom - inset - top);
  // Capped, not filled: the plate is as tall as its letters want to be
  // until there are more of them than there is room, and then they shrink.
  rail.style.maxHeight = `${Math.round(room)}px`;
  rail.style.top = `${Math.round(top)}px`;
  rail.style.top = `${Math.round(top + (room - rail.offsetHeight) / 2)}px`;
}

function markActive(letter) {
  if (letter === activeLetter) return;
  activeLetter = letter;
  for (const [name, mark] of marks) mark.classList.toggle("on", name === letter);
}

// Which letter the list has actually reached. The rail used to light up
// only while a thumb was on it, so scrolling the list by hand left the
// index pointing at wherever it was last dragged to.
//
// Not while a thumb *is* on it: the end of the list cannot be scrolled past,
// so dragging into the last few letters would leave the mark under the
// finger dark and a different one lit, which reads as the rail refusing.
function syncRail() {
  if (scrubbedLetter) return;
  if (!document.body.classList.contains("browsing") || !headings.length) return;
  const pane = $("pane-apps").getBoundingClientRect();
  // The line a heading counts as "reached" at is the one a jump lands it on
  // — `.az-group`'s scroll margin — not the search row's exact edge. A
  // couple of pixels tighter and tapping F lit E, because F came to rest six
  // pixels below the row it had just been scrolled under.
  const line = pane.top + $("search-row").offsetHeight + 10;
  let current = headings[0].letter;
  for (const entry of headings) {
    if (entry.heading.getBoundingClientRect().top > line) break;
    current = entry.letter;
  }
  markActive(current);
}

// Where the finger is, worked out from the rail's own box rather than with
// `elementFromPoint`. A column of 27 letters on a phone is about eleven
// pixels a mark: hit-testing them exactly means the gaps between them
// select nothing, which is most of the rail.
function letterAt(y) {
  const list = [...marks.values()];
  if (!list.length) return "";
  const top = list[0].getBoundingClientRect().top;
  const bottom = list[list.length - 1].getBoundingClientRect().bottom;
  const slot = (bottom - top) / list.length;
  const index = Math.floor((y - top) / slot);
  return list[Math.min(list.length - 1, Math.max(0, index))].textContent;
}

function showBubble(letter, y) {
  const bubble = $("rail-bubble");
  bubble.textContent = letter;
  bubble.classList.add("on");
  const rail = $("rail").getBoundingClientRect();
  const half = bubble.offsetHeight / 2;
  const clamped = Math.min(rail.bottom - half, Math.max(rail.top + half, y));
  bubble.style.top = `${Math.round(clamped - half)}px`;
}

function hideBubble() {
  $("rail-bubble").classList.remove("on");
  scrubbedLetter = "";
  // The list may have run out before the letter did; settle onto whichever
  // one it actually stopped at.
  syncRail();
}

function scrub(y) {
  const letter = letterAt(y);
  if (!letter) return;
  showBubble(letter, y);
  if (letter === scrubbedLetter) return;
  scrubbedLetter = letter;
  buzz(4);
  markActive(letter);
  const entry = headings.find((group) => group.letter === letter);
  if (entry) entry.group.scrollIntoView({ block: "start" });
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
      $("pane-apps").scrollTop = 0;
      load();
      placeRail();
      syncRail();
    } else {
      closeBrowsing();
    }
  });

  const rail = $("rail");
  rail.addEventListener("pointerdown", (event) => {
    rail.setPointerCapture(event.pointerId);
    event.preventDefault();
    scrub(event.clientY);
  });
  rail.addEventListener("pointermove", (event) => {
    if (rail.hasPointerCapture(event.pointerId)) scrub(event.clientY);
  });
  for (const name of ["pointerup", "pointercancel"]) {
    rail.addEventListener(name, hideBubble);
  }

  // One read per frame. The handler runs on every scroll event of a list
  // several thousand pixels long, and it measures twenty-seven headings.
  $("pane-apps").addEventListener("scroll", () => {
    if (syncing) return;
    syncing = true;
    requestAnimationFrame(() => {
      syncing = false;
      syncRail();
    });
  }, { passive: true });

  for (const name of ["resize", "orientationchange"]) {
    window.addEventListener(name, () => {
      placeRail();
      syncRail();
    });
  }
}

// A restarted remote has a different installed-app list to offer, and the
// ids behind it are only valid for as long as the server remembers having
// offered them.
export function forgetAllApps() {
  loaded = false;
  render([]);
  buildRail([]);
  say("");
}

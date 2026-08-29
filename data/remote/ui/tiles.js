// SPDX-License-Identifier: GPL-3.0-or-later
//
// One card. Shared by the mirrored catalogue, the search results and the
// A-Z list, so a result and a home-screen tile are the same object with the
// same artwork, the same long press and the same launch path.

import { buzz, el, icon, inkOn, toast } from "./dom.js";
import { session } from "./session.js";
import { post } from "./transport.js";
import { pollSoon } from "./feed.js";

// 450ms with the finger still. The slop matters: this used to cancel on
// any `pointermove` at all, while the trackpad beside it correctly allowed
// twelve pixels — and a thumb on glass always drifts a little, so the sheet
// opened about half the times it was asked for.
const HOLD_MS = 450;
const HOLD_SLOP_PX = 12;

export function artUrl(id) {
  return `/art/${encodeURIComponent(id)}?k=${encodeURIComponent(session.key)}`;
}

// No artwork: the accent as a flat card, which is what the television draws
// too. A broken-image glyph would be strictly worse than a colour.
export function blankArt(tile) {
  const blank = el("div", "art blank");
  blank.style.background =
    `linear-gradient(150deg, ${tile.accent}, ${tile.accent}55)`;
  blank.style.color = inkOn(tile.accent);
  blank.textContent = (tile.title || "?").trim().charAt(0).toUpperCase();
  return blank;
}

export function artNode(tile, className) {
  if (!tile.art) return blankArt(tile);
  const art = document.createElement("img");
  art.className = (tile.fit === "contain" ? `${className} icon` : className).trim();
  if (tile.fit === "contain") {
    art.style.background =
      `linear-gradient(150deg, ${tile.accent}, ${tile.accent}55)`;
  }
  art.loading = "lazy";
  art.alt = "";
  art.src = artUrl(tile.id);
  // A tile whose art fails to load falls back to the same coloured card an
  // artless tile gets, rather than to the browser's broken glyph.
  art.addEventListener("error", () => art.replaceWith(blankArt(tile)));
  return art;
}

export function launchTile(tile, node) {
  buzz(12);
  node.classList.add("pressed");
  post("/launch", { id: tile.id }).then((result) => {
    node.classList.remove("pressed");
    if (result) toast(`Opening ${tile.title}`);
    pollSoon();
  });
}

// Deliberately not a right-click equivalent or a second tap target: a long
// press is the gesture every phone already teaches, and the television
// reaches the same menu with OPTIONS.
function bindLongPress(node, run) {
  let timer = null;
  let origin = null;
  const cancel = () => { clearTimeout(timer); timer = null; };
  node.addEventListener("pointerdown", (event) => {
    cancel();
    origin = { x: event.clientX, y: event.clientY };
    timer = setTimeout(() => {
      timer = null;
      node.dataset.held = "1";
      buzz(18);
      run();
    }, HOLD_MS);
  });
  node.addEventListener("pointermove", (event) => {
    if (timer === null || origin === null) return;
    const travelled =
      Math.abs(event.clientX - origin.x) + Math.abs(event.clientY - origin.y);
    if (travelled > HOLD_SLOP_PX) cancel();
  });
  for (const name of ["pointerup", "pointercancel", "pointerleave"]) {
    node.addEventListener(name, cancel);
  }
}

export function tileNode(tile, onLongPress) {
  const node = el("div", "tile");
  node.dataset.id = tile.id;
  const main = el("button", "tile-main");
  main.setAttribute("aria-label", `Open ${tile.title}`);
  main.append(artNode(tile, "art"));

  const caption = el("div", "caption");
  caption.append(el("div", "name", tile.title));
  if (tile.subtitle) caption.append(el("div", "sub", tile.subtitle));
  main.append(caption);
  node.append(main);

  const more = el("button", "tile-more");
  more.setAttribute("aria-label", `More actions for ${tile.title}`);
  more.append(icon("i-more"));
  more.addEventListener("click", () => {
    buzz(8);
    onLongPress(tile);
  });
  node.append(more);

  main.addEventListener("click", () => {
    // A long press has already opened the sheet and cancelled itself; the
    // click the browser sends afterwards must not also launch the thing.
    if (main.dataset.held === "1") {
      delete main.dataset.held;
      return;
    }
    launchTile(tile, main);
  });
  bindLongPress(main, () => onLongPress(tile));
  return node;
}

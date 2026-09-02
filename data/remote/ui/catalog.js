// SPDX-License-Identifier: GPL-3.0-or-later
//
// The mirrored catalogue, the cursor mirror on top of it, and the card on
// the Buttons pane that says what the cursor is resting on.

import { $, el, inkOn } from "./dom.js";
import { session } from "./session.js";
import { artNode, tileNode } from "./tiles.js";

let renderedSignature = "";
let focusedNode = null;
let onLongPress = () => {};
// Set while the finger is on the list. Following the television's cursor
// with `scrollIntoView` is right when the cursor is being driven from the
// D-pad and wrong the instant somebody is scrolling this list themselves.
let scrolledAt = 0;
const SETTLE_MS = 2500;

export function bindCatalog(handler) {
  onLongPress = handler;
  $("pane-apps").addEventListener(
    "scroll", () => { scrolledAt = Date.now(); }, { passive: true }
  );
}

export function renderRows(rows) {
  const host = $("apps");
  host.textContent = "";
  let count = 0;

  for (const row of rows) {
    if (!row.tiles.length) continue;
    if (row.title) host.append(el("h2", "row-title", row.title));
    const grid = el("div", `row-tiles ${row.aspect}`);
    for (const tile of row.tiles) {
      grid.append(tileNode(tile, onLongPress));
      count += 1;
    }
    host.append(grid);
  }
  $("apps-empty").style.display = count ? "none" : "";
}

// The grid is rebuilt only when the catalogue itself changed. Redrawing two
// hundred tiles once a second because the cursor moved would drop every
// image back to its placeholder and make scrolling impossible.
export function renderCatalog(rows) {
  const signature = JSON.stringify(rows);
  if (signature === renderedSignature) return;
  renderedSignature = signature;
  renderRows(rows);
}

export function focusedTile(data) {
  if (!data || !data.focus) return null;
  const row = data.rows[data.focus[0]];
  return (row && row.tiles[data.focus[1]]) || null;
}

export function renderFocus(data) {
  if (focusedNode) focusedNode.classList.remove("focused");
  focusedNode = null;
  const tile = focusedTile(data);
  if (!tile) return;
  const node = $("apps").querySelector(`[data-id="${CSS.escape(tile.id)}"]`);
  if (!node) return;
  node.classList.add("focused");
  focusedNode = node;
  // The ring used to be the whole of it, so the mirror was invisible
  // whenever the television's cursor was below the fold — which is most of
  // the time on a catalogue of any size.
  if (session.tab === "apps" && Date.now() - scrolledAt > SETTLE_MS) {
    node.scrollIntoView({ block: "nearest" });
  }
}

let mirroredId = "";

// The card at the top of the Buttons pane. The state already carries the
// cursor and /art already serves the picture; the third of a screen above
// a bottom-aligned D-pad was empty. This is the difference between a remote
// and a second screen — you stop looking up to know where you are.
export function renderMirror(data) {
  const card = $("mirror");
  const tile = focusedTile(data);
  const app = data.app || "";
  const identity = app ? `app:${app}` : tile ? `tile:${tile.id}` : "";
  card.classList.toggle("on", Boolean(identity));
  $("mirror-neighbours").classList.remove("on");
  if (identity === mirroredId) return;
  mirroredId = identity;

  const art = $("mirror-art");
  art.textContent = "";
  art.style.background = "";
  if (app) {
    // With an application covering the television there is no cursor to
    // mirror, and saying what *is* up there is the more useful sentence.
    $("mirror-label").textContent = "";
    $("mirror-title").textContent = app;
    $("mirror-sub").textContent = "";
    $("mirror-position").textContent = "Application open";
    $("mirror-prev").textContent = "";
    $("mirror-next").textContent = "";
    art.textContent = app.trim().charAt(0).toUpperCase();
    art.style.background = "var(--s2)";
    return;
  }
  if (!tile) return;
  $("mirror-label").textContent = "";
  $("mirror-title").textContent = tile.title;
  $("mirror-sub").textContent = tile.subtitle || "";
  const [rowIndex, tileIndex] = data.focus;
  const row = data.rows[rowIndex];
  $("mirror-position").textContent =
    `${row.title || "Home"} · ${tileIndex + 1} of ${row.tiles.length}`;
  const previous = row.tiles[tileIndex - 1];
  const next = row.tiles[tileIndex + 1];
  $("mirror-neighbours").classList.toggle("on", Boolean(previous || next));
  $("mirror-prev").textContent = previous ? `← ${previous.title}` : "";
  $("mirror-next").textContent = next ? `${next.title} →` : "";
  if (tile.art) {
    art.append(artNode(tile, ""));
    return;
  }
  art.style.background =
    `linear-gradient(150deg, ${tile.accent}, ${tile.accent}55)`;
  art.style.color = inkOn(tile.accent);
  art.textContent = (tile.title || "?").trim().charAt(0).toUpperCase();
}

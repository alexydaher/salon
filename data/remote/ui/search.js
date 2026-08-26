// SPDX-License-Identifier: GPL-3.0-or-later
//
// Search over the catalogue *and* every installed application, ranked by
// the same `core/ranking.rank_best` the television uses.

import { $, el } from "./dom.js";
import { post } from "./transport.js";
import { tileNode } from "./tiles.js";
import { closeBrowsing } from "./allapps.js";

// Every keystroke is a request, and the television answers them on the
// thread that draws its own interface. 140ms is under the gap between two
// letters typed quickly and over the gap inside one.
const DEBOUNCE_MS = 140;

let timer = null;
let sequence = 0;
let onLongPress = () => {};

function renderResults(results) {
  const host = $("results");
  host.textContent = "";
  if (!results.length) {
    const empty = el("div", "", "Nothing matched. Try fewer letters.");
    empty.id = "results-empty";
    host.append(empty);
    return;
  }
  const grid = el("div", "row-tiles wide");
  for (const tile of results) grid.append(tileNode(tile, onLongPress));
  host.append(grid);
}

async function run() {
  const query = $("q").value.trim();
  if (query) closeBrowsing();
  document.body.classList.toggle("searching", Boolean(query));
  if (!query) {
    $("results").textContent = "";
    return;
  }
  // Answers can overtake each other on a slow link, and a result list for
  // "net" arriving after the one for "netflix" would show the wrong thing
  // with no way to tell.
  const seq = ++sequence;
  const result = await post("/search", { q: query });
  if (!result || seq !== sequence) return;
  renderResults(result.results || []);
}

export function clearSearch() {
  $("q").value = "";
  document.body.classList.remove("searching");
  $("results").textContent = "";
}

export function bindSearch(handler) {
  onLongPress = handler;
  $("q").addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(run, DEBOUNCE_MS);
  });
  $("q").addEventListener("search", run);
  $("q-clear").addEventListener("click", () => {
    clearSearch();
    $("q").blur();
  });
}

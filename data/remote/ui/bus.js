// SPDX-License-Identifier: GPL-3.0-or-later
//
// Twenty lines of publish/subscribe, and it earns them: the state feed has
// to hand a snapshot to the renderer, and the renderer has to be able to
// ask the feed to poll again after a press. Importing each other directly
// makes that a cycle, and a cycle in ES modules is a half-initialised
// module that fails at whichever call site happens to run first.
//
// So: the feed emits, `main.js` wires the emitters to the handlers, and
// nothing below `main.js` imports anything above it.

const handlers = new Map();

export function on(name, handler) {
  const list = handlers.get(name);
  if (list) list.push(handler);
  else handlers.set(name, [handler]);
}

export function emit(name, ...args) {
  for (const handler of handlers.get(name) || []) handler(...args);
}

/**
 * Salon gamepad navigation content script.
 *
 * Runs entirely inside the page — no system permissions, no cross-process
 * input injection, none of the Wayland portal machinery that turned out to
 * be unreliable. Uses the standard Web Gamepad API, which Chrome normalizes
 * across controller vendors (button/axis indices are stable regardless of
 * hardware, unlike the raw evdev codes Salon's own Python side has to
 * reverse-engineer per controller).
 *
 * Controls: right stick = cursor, A = click, D-pad = arrow keys (works with
 * Chrome's --enable-spatial-navigation), Y = on-screen keyboard, B = Escape.
 */
(() => {
  "use strict";

  const DEAD_ZONE = 0.2;
  const CURSOR_SPEED = 16; // px per animation frame at full stick deflection

  const BTN_A = 0;
  const BTN_B = 1;
  const BTN_Y = 3;
  const BTN_DPAD_UP = 12;
  const BTN_DPAD_DOWN = 13;
  const BTN_DPAD_LEFT = 14;
  const BTN_DPAD_RIGHT = 15;

  let cursorX = window.innerWidth / 2;
  let cursorY = window.innerHeight / 2;
  let cursorShown = false;
  const prevButtons = {};

  const cursorEl = document.createElement("div");
  cursorEl.id = "salon-gamepad-cursor";
  document.documentElement.appendChild(cursorEl);

  function showCursor() {
    if (!cursorShown) {
      cursorShown = true;
      cursorEl.classList.add("visible");
    }
  }

  function moveCursorTo(x, y) {
    cursorX = Math.max(0, Math.min(window.innerWidth - 1, x));
    cursorY = Math.max(0, Math.min(window.innerHeight - 1, y));
    cursorEl.style.transform = `translate(${cursorX}px, ${cursorY}px)`;
  }

  function clickAtCursor() {
    const el = document.elementFromPoint(cursorX, cursorY);
    if (!el) return;
    const opts = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: cursorX,
      clientY: cursorY,
    };
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.dispatchEvent(new MouseEvent("click", opts));
    if (typeof el.focus === "function") el.focus();
  }

  function dispatchKey(type, key, keyCode) {
    const el = document.activeElement || document.body;
    el.dispatchEvent(
      new KeyboardEvent(type, { key, keyCode, which: keyCode, bubbles: true, cancelable: true })
    );
  }

  function wasPressed(padIndex, buttonIndex, pressed) {
    const key = `${padIndex}:${buttonIndex}`;
    const was = prevButtons[key] || false;
    prevButtons[key] = pressed;
    return pressed && !was;
  }

  function poll() {
    const pads = navigator.getGamepads();
    for (const pad of pads) {
      if (!pad) continue;

      const rx = pad.axes[2] || 0;
      const ry = pad.axes[3] || 0;
      if (Math.abs(rx) > DEAD_ZONE || Math.abs(ry) > DEAD_ZONE) {
        showCursor();
        moveCursorTo(cursorX + rx * CURSOR_SPEED, cursorY + ry * CURSOR_SPEED);
      }

      if (wasPressed(pad.index, BTN_A, pad.buttons[BTN_A]?.pressed)) {
        if (Salon.osk.visible) {
          Salon.osk.select();
        } else {
          clickAtCursor();
        }
      }
      if (wasPressed(pad.index, BTN_Y, pad.buttons[BTN_Y]?.pressed)) {
        Salon.osk.toggle();
      }
      if (wasPressed(pad.index, BTN_B, pad.buttons[BTN_B]?.pressed)) {
        if (Salon.osk.visible) {
          Salon.osk.toggle();
        } else {
          dispatchKey("keydown", "Escape", 27);
        }
      }

      const dpad = [
        [BTN_DPAD_UP, "up"],
        [BTN_DPAD_DOWN, "down"],
        [BTN_DPAD_LEFT, "left"],
        [BTN_DPAD_RIGHT, "right"],
      ];
      for (const [index, direction] of dpad) {
        if (wasPressed(pad.index, index, pad.buttons[index]?.pressed)) {
          if (Salon.osk.visible) {
            Salon.osk.move(direction);
          } else {
            const keyMap = {
              up: ["ArrowUp", 38],
              down: ["ArrowDown", 40],
              left: ["ArrowLeft", 37],
              right: ["ArrowRight", 39],
            };
            const [key, code] = keyMap[direction];
            dispatchKey("keydown", key, code);
            dispatchKey("keyup", key, code);
          }
        }
      }
    }
    requestAnimationFrame(poll);
  }

  // ---- text entry: works with plain inputs, textareas, contenteditable,
  // and React-controlled inputs (Netflix/Prime are React apps — setting
  // .value directly and dispatching a bare 'input' event doesn't update
  // React's tracked state, since React overrides the instance value setter
  // but not the prototype's; going through the prototype setter is the
  // standard workaround). ----
  function nativeValueSetter(el) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    return Object.getOwnPropertyDescriptor(proto, "value").set;
  }

  function typeChar(ch) {
    const el = document.activeElement;
    if (!el) return;
    if (el.isContentEditable) {
      document.execCommand("insertText", false, ch);
      return;
    }
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      const next = el.value.slice(0, start) + ch + el.value.slice(end);
      nativeValueSetter(el).call(el, next);
      el.selectionStart = el.selectionEnd = start + ch.length;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function backspace() {
    const el = document.activeElement;
    if (!el) return;
    if (el.isContentEditable) {
      document.execCommand("delete", false);
      return;
    }
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      const [from, to] = start === end ? [Math.max(0, start - 1), end] : [start, end];
      const next = el.value.slice(0, from) + el.value.slice(to);
      nativeValueSetter(el).call(el, next);
      el.selectionStart = el.selectionEnd = from;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  // ---- on-screen keyboard: a D-pad-navigable grid rendered into the
  // page's own DOM, so it just works — no Wayland layering issue, since
  // it's not a separate surface at all. ----
  const LAYOUT = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", "⏎"],
    ["z", "x", "c", "v", "b", "n", "m", "⌫", "␣", "✓"],
  ];

  const oskEl = document.createElement("div");
  oskEl.id = "salon-osk";
  const keyElements = [];
  for (let r = 0; r < LAYOUT.length; r++) {
    const rowEl = document.createElement("div");
    rowEl.className = "row";
    const rowKeys = [];
    for (let c = 0; c < LAYOUT[r].length; c++) {
      const keyEl = document.createElement("div");
      keyEl.className = "key";
      keyEl.textContent = LAYOUT[r][c];
      rowEl.appendChild(keyEl);
      rowKeys.push(keyEl);
    }
    oskEl.appendChild(rowEl);
    keyElements.push(rowKeys);
  }
  document.documentElement.appendChild(oskEl);

  let oskRow = 0;
  let oskCol = 0;

  function renderSelection() {
    for (const row of keyElements) {
      for (const key of row) key.classList.remove("selected");
    }
    keyElements[oskRow][oskCol].classList.add("selected");
  }

  const Salon = (window.__salonGamepadNav = window.__salonGamepadNav || {});
  Salon.osk = {
    get visible() {
      return oskEl.classList.contains("visible");
    },
    toggle() {
      oskEl.classList.toggle("visible");
      if (this.visible) renderSelection();
    },
    move(direction) {
      if (direction === "up") oskRow = Math.max(0, oskRow - 1);
      else if (direction === "down") oskRow = Math.min(LAYOUT.length - 1, oskRow + 1);
      else if (direction === "left") oskCol = Math.max(0, oskCol - 1);
      else if (direction === "right") oskCol = Math.min(LAYOUT[oskRow].length - 1, oskCol + 1);
      oskCol = Math.min(oskCol, LAYOUT[oskRow].length - 1);
      renderSelection();
    },
    select() {
      const ch = LAYOUT[oskRow][oskCol];
      if (ch === "⏎") dispatchKey("keydown", "Enter", 13);
      else if (ch === "⌫") backspace();
      else if (ch === "␣") typeChar(" ");
      else if (ch === "✓") this.toggle();
      else typeChar(ch);
    },
  };

  requestAnimationFrame(poll);
})();

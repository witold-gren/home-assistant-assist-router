// The tour of the editor: one part of the editor at a time framed, the rest dimmed, and a bubble that says what it is
// and where it is set. It starts by itself the first time the editor opens in a browser and from ⚙ whenever asked.
// A step whose part is not on the screen (no topic chosen, the right column folded) is left out.
// The lessons (lessons.js) are tours of one task each: their steps first go where the task is (a node of the tree, a
// part of a form) and may wait for the framed button to be clicked, so the task is done while it is learnt.
// The same tour as in the editor of Home Dashboard (standard gpu-studio §5a).

import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { asking } from "./ask.js";
import { readStored, writeStored } from "./stored.js";

export const TOUR_KEY = "assist-router-editor-tour";
export const LESSONS_KEY = "assist-router-editor-lessons";
const BUBBLE_WIDTH = 360;
const GAP = 16;
const PAD = 8;
// A click on a framed button moves on after this, once what it opens is there.
export const CLICK_SETTLE_MS = 400;

// Each step: its key (the texts are tour_<key>_title, _text and, with `where`, _where), the parts it frames (one frame
// round all of them) and the side of the bubble.
export const TOUR_STEPS = [
  { key: "welcome", targets: [] },
  { key: "tree", targets: ["[data-tree]"], side: "right", where: true },
  { key: "add", targets: ["[data-add-topic]", "[data-add-sentences]"], side: "right", where: true },
  { key: "middle", targets: ["[data-middle]"], side: "inside" },
  { key: "tabs", targets: ["[data-tabs]"], side: "below", where: true },
  { key: "side", targets: ["[data-check]", "[data-file-card]", "[data-kind]"], side: "left" },
  { key: "tester", targets: ["[data-tester]"], side: "left", where: true },
  { key: "undo", targets: ["[data-draft-state]", "[data-undo]", "[data-redo]"], side: "below", where: true },
  { key: "save", targets: ["[data-history]", "[data-save]"], side: "below-end" },
  { key: "help", targets: ["[data-docs]", "[data-gear]", "[data-help='tree']"], side: "below-end" },
];

/** The keys of the lessons gone through in this browser. */
export function lessonsDone() {
  try {
    const done = JSON.parse(readStored(LESSONS_KEY) ?? "[]");
    return Array.isArray(done) ? done : [];
  } catch {
    return [];
  }
}

export function markLessonDone(key) {
  const done = lessonsDone();
  if (!done.includes(key)) writeStored(LESSONS_KEY, JSON.stringify([...done, key]));
}

/**
 * Whether the tour has been seen (or skipped) in this browser. Without the storage of the browser (private browsing)
 * it could not remember being skipped and would come back every time, so it counts as seen; ⚙ still opens it.
 */
export function tourSeen() {
  try {
    return window.localStorage.getItem(TOUR_KEY) === "done";
  } catch {
    return true;
  }
}

// The first element for a selector in a root or any shadow root under it.
function deepFind(root, selector) {
  const found = root.querySelector?.(selector);
  if (found) return found;
  for (const element of root.querySelectorAll?.("*") ?? []) {
    if (!element.shadowRoot) continue;
    const inner = deepFind(element.shadowRoot, selector);
    if (inner) return inner;
  }
  return null;
}

/**
 * The element a target names: a selector, or selectors joined by ">>>" for one inside another (each looked for in
 * the last one found and the shadow roots under it).
 */
export function findTarget(root, target) {
  let scope = root;
  for (const selector of target.split(">>>").map((part) => part.trim())) {
    if (!scope) return null;
    const found = deepFind(scope.shadowRoot ?? scope, selector) ?? (scope.shadowRoot ? deepFind(scope, selector) : null);
    scope = found;
  }
  return scope && scope !== root ? scope : null;
}

/** The steps there is something on the screen for. */
export function shownSteps(root, steps = TOUR_STEPS) {
  return steps.filter((step) => !step.targets.length || step.targets.some((target) => findTarget(root, target)));
}

/** One rectangle round the parts of a step that are on the screen, a little larger; null for none. */
export function frameOf(root, targets, width = window.innerWidth, height = window.innerHeight) {
  const boxes = targets
    .map((target) => (root ? findTarget(root, target) : null)?.getBoundingClientRect())
    .filter((box) => box && box.width && box.height);
  if (!boxes.length) return null;
  const left = Math.max(4, Math.min(...boxes.map((box) => box.left)) - PAD);
  const top = Math.max(4, Math.min(...boxes.map((box) => box.top)) - PAD);
  const right = Math.min(width - 4, Math.max(...boxes.map((box) => box.right)) + PAD);
  const bottom = Math.min(height - 4, Math.max(...boxes.map((box) => box.bottom)) + PAD);
  return { left, top, width: right - left, height: bottom - top };
}

/** Where the bubble stands: on the chosen side of the frame, kept inside the window. */
export function bubbleAt(frame, side, size, width = window.innerWidth, height = window.innerHeight) {
  const bubble = { width: Math.min(BUBBLE_WIDTH, width - 2 * GAP), height: size?.height ?? 220 };
  const clampX = (x) => Math.max(GAP, Math.min(width - bubble.width - GAP, x));
  const clampY = (y) => Math.max(GAP, Math.min(height - bubble.height - GAP, y));
  if (!frame) return { left: clampX((width - bubble.width) / 2), top: clampY(height * 0.28), width: bubble.width };
  const below = frame.top + frame.height + GAP;
  const places = {
    right: { left: frame.left + frame.width + GAP, top: frame.top + 40 },
    left: { left: frame.left - bubble.width - GAP, top: frame.top + 40 },
    below: { left: frame.left, top: below },
    above: { left: frame.left, top: frame.top - bubble.height - GAP },
    "below-end": { left: frame.left + frame.width - bubble.width, top: below },
    inside: { left: frame.left + 24, top: frame.top + frame.height - bubble.height - 24 },
  };
  const place = places[side] ?? places.below;
  return { left: clampX(place.left), top: clampY(place.top), width: bubble.width };
}

class AssistRouterEditorTour extends LitElement {
  static properties = {
    // The editor whose parts are framed (its shadow root is searched) and whose state the lessons' steps prepare.
    host: { attribute: false },
    t: { attribute: false },
    // A lesson instead of the tour: { key, steps }.
    lesson: { attribute: false },
    _index: { state: true },
  };

  constructor() {
    super();
    this._index = 0;
    this._onResize = () => this.requestUpdate();
    // A click on the framed part of a step that waits for it moves on, once what it opens is there.
    this._onClick = (event) => {
      const step = this._steps?.[this._index];
      if (step?.advance !== "click" || !this._frame || asking(this._root)) return;
      const { left, top, width, height } = this._frame;
      if (event.clientX < left || event.clientX > left + width || event.clientY < top || event.clientY > top + height) return;
      const at = this._index;
      setTimeout(() => this._index === at && this._go(1, { clicked: true }), CLICK_SETTLE_MS);
    };
    // In the capture phase, so Esc closes the tour and not the window of the editor under it.
    // An open question (ask.js) over the editor has the keys to itself.
    this._onKey = (event) => {
      if (asking(this._root)) return;
      if (event.key === "Escape") this._finish();
      else if (event.key === "ArrowRight" || (event.key === "Enter" && !this._typing(event))) this._go(1);
      else if (event.key === "ArrowLeft" && !this._typing(event)) this._go(-1);
      else return;
      event.preventDefault();
      event.stopPropagation();
    };
  }

  // Enter and the arrows in a field a lesson asks to fill in belong to the field.
  _typing(event) {
    return event.composedPath().some((element) => ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName));
  }

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener("resize", this._onResize);
    window.addEventListener("keydown", this._onKey, true);
    window.addEventListener("click", this._onClick, true);
    // What a step frames can move or appear (a window opening, a part unfolding): the frame follows it.
    this._follow = setInterval(() => this.requestUpdate(), 400);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("resize", this._onResize);
    window.removeEventListener("keydown", this._onKey, true);
    window.removeEventListener("click", this._onClick, true);
    clearInterval(this._follow);
  }

  get _root() {
    return this.host?.renderRoot ?? null;
  }

  willUpdate(changed) {
    // The tour leaves out what is not on the screen; a lesson goes where its steps are, so all of them stay, but the
    // steps only some files need (making a file of commands there is none of yet) are left out of the others.
    if (changed.has("lesson") || !this._steps) {
      this._steps = this.lesson
        ? this.lesson.steps.filter((step) => !step.when || step.when(this.host))
        : shownSteps(this._root);
      this._prepared = null;
    }
    const step = this._steps?.[this._index];
    if (step && this._prepared !== this._index) {
      this._prepared = this._index;
      step.prepare?.(this.host);
    }
  }

  // The bubble's own height is known once it is drawn: it is placed again with it.
  updated() {
    const height = this.renderRoot.querySelector("[data-tour-bubble]")?.offsetHeight;
    if (height && height !== this._height) {
      this._height = height;
      this.requestUpdate();
    }
  }

  _go(by, { clicked = false } = {}) {
    // Next on a step that waits for a click does what the click would (opens the window the next steps frame).
    const step = this._steps?.[this._index];
    if (by > 0 && !clicked && step?.advance === "click") step.act?.(this.host);
    const next = this._index + by;
    if (next < 0) return;
    if (next >= this._steps.length) return this._finish();
    this._index = next;
  }

  _finish() {
    if (this.lesson) {
      // A lesson counts as done once it was gone through to its last step.
      if (this._index === this._steps.length - 1) markLessonDone(this.lesson.key);
    } else writeStored(TOUR_KEY, "done");
    this.dispatchEvent(new CustomEvent("tour-close", { bubbles: true, composed: true }));
  }

  render() {
    const t = this.t ?? ((key) => key);
    const steps = this._steps ?? [];
    const step = steps[this._index];
    if (!step) return nothing;
    // A lesson's step can name its parts from the file (the first topic, whichever it is).
    const targets = typeof step.targets === "function" ? step.targets(this.host) : step.targets;
    // What comes only after an earlier click (a field of a topic just made) is framed by the part it belongs to
    // until then.
    const frame = frameOf(this._root, targets) ?? (step.fallback ? frameOf(this._root, step.fallback) : null);
    this._frame = frame;
    // A part out of sight (a field at the end of a long form, the + of a group scrolled away in the tree: inside the
    // window but cut off by the column that scrolls) is scrolled to, once a step. "nearest" scrolls every column it is
    // in only as much as needed, and not at all when it is in sight.
    if (frame && this._scrolled !== this._index) {
      this._scrolled = this._index;
      targets.map((target) => findTarget(this._root, target)).find(Boolean)?.scrollIntoView({ block: "nearest", inline: "nearest" });
      requestAnimationFrame(() => this.requestUpdate());
    }
    const at = bubbleAt(frame, step.side, { height: this._height });
    const last = this._index === steps.length - 1;
    const base = this.lesson ? `lesson_${this.lesson.key}_${step.key}` : `tour_${step.key}`;
    const waits = step.advance === "click" && frame;
    return html`
      ${waits ? this._renderBlockers(frame) : html`<div class="block" data-tour-block></div>`}
      ${frame
        ? html`<div class="frame" data-tour-frame=${step.key}
            style="left:${frame.left}px;top:${frame.top}px;width:${frame.width}px;height:${frame.height}px"></div>`
        : html`<div class="dim"></div>`}
      <section class="bubble" role="dialog" aria-label=${t(`${base}_title`)} data-tour-bubble=${step.key}
        style="left:${at.left}px;top:${at.top}px;width:${at.width}px">
        <div class="top">
          <span data-tour-count>${this.lesson
            ? t("lesson_step", { name: t(`lesson_${this.lesson.key}_name`), step: this._index + 1, count: steps.length })
            : t("tour_step", { step: this._index + 1, count: steps.length })}</span>
          <button class="close" data-tour-close aria-label=${t("close")} @click=${this._finish}>×</button>
        </div>
        <h3>${t(`${base}_title`)}</h3>
        <p>${t(`${base}_text`)}</p>
        ${step.where ? html`<div class="where"><strong>${t("tour_where")}</strong> ${t(`${base}_where`)}</div>` : nothing}
        ${waits ? html`<p class="try" data-tour-try>${t("lesson_try")}</p>` : nothing}
        <div class="bottom">
          <div class="dots" aria-hidden="true">
            ${steps.map((_, index) => html`<i class=${index === this._index ? "on" : ""}></i>`)}
          </div>
          ${this._index
            ? html`<button class="ghost" data-tour-back @click=${() => this._go(-1)}>${t("tour_back")}</button>`
            : html`<button class="link" data-tour-skip @click=${this._finish}>${t("tour_skip")}</button>`}
          <button class="primary" data-tour-next @click=${() => this._go(1)}>${last ? t("tour_done") : t("tour_next")}</button>
        </div>
      </section>
    `;
  }

  // Around a frame that waits for a click: the rest is blocked, the framed part takes the click.
  _renderBlockers(frame) {
    const right = frame.left + frame.width;
    const bottom = frame.top + frame.height;
    const box = (left, top, width, height) =>
      html`<div class="blocker" style="left:${left}px;top:${top}px;width:${Math.max(0, width)}px;height:${Math.max(0, height)}px"></div>`;
    return html`<div data-tour-block="open">
      ${box(0, 0, window.innerWidth, frame.top)} ${box(0, bottom, window.innerWidth, window.innerHeight - bottom)}
      ${box(0, frame.top, frame.left, frame.height)} ${box(right, frame.top, window.innerWidth - right, frame.height)}
    </div>`;
  }

  static styles = css`
    :host {
      position: fixed;
      inset: 0;
      z-index: 40;
      pointer-events: none;
      font: 14px/1.45 -apple-system, "SF Pro Text", Roboto, system-ui, sans-serif;
    }
    .block,
    .blocker {
      position: absolute;
    }
    .block {
      inset: 0;
    }
    .block,
    .blocker,
    .bubble {
      pointer-events: auto;
    }
    .dim {
      position: absolute;
      inset: 0;
      background: rgba(8, 14, 24, 0.58);
    }
    .frame {
      position: absolute;
      border-radius: 12px;
      pointer-events: none;
      box-shadow:
        0 0 0 3px #fff,
        0 0 0 7px rgba(10, 132, 255, 0.55),
        0 0 0 9999px rgba(8, 14, 24, 0.58);
      transition:
        left 0.25s,
        top 0.25s,
        width 0.25s,
        height 0.25s;
    }
    .bubble {
      position: absolute;
      box-sizing: border-box;
      padding: 16px;
      border-radius: 16px;
      color: #1c2733;
      background: #fff;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
      transition:
        left 0.25s,
        top 0.25s;
    }
    .top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: #66727f;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    h3 {
      margin: 6px 0;
      font-size: 18px;
    }
    p {
      margin: 0 0 10px;
      color: #33404d;
    }
    .where {
      padding: 8px 10px;
      border-radius: 10px;
      color: #0a5ccc;
      background: #eef5ff;
      font-size: 13px;
    }
    .try {
      margin: 10px 0 0;
      color: #0a84ff;
      font-weight: 600;
      font-size: 13px;
    }
    .bottom {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 14px;
    }
    .dots {
      display: flex;
      flex: 1;
      flex-wrap: wrap;
      gap: 4px;
    }
    .dots i {
      width: 6px;
      height: 6px;
      border-radius: 3px;
      background: #c9d2dc;
    }
    .dots i.on {
      width: 18px;
      background: #0a84ff;
    }
    button {
      font: inherit;
      cursor: pointer;
    }
    .close {
      border: 0;
      background: none;
      color: inherit;
      font-size: 20px;
      line-height: 1;
    }
    .ghost {
      padding: 7px 14px;
      border: 1px solid #dde3ea;
      border-radius: 10px;
      color: #1c2733;
      background: #fff;
    }
    .link {
      border: 0;
      background: none;
      color: #66727f;
    }
    .primary {
      padding: 7px 16px;
      border: 0;
      border-radius: 10px;
      color: #fff;
      background: #0a84ff;
      font-weight: 600;
    }
  `;
}

if (!customElements.get("assist-router-editor-tour")) customElements.define("assist-router-editor-tour", AssistRouterEditorTour);
